from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from shopping.catalog.models import (
    CatalogObservation,
    EntityResolutionEvent,
    OwnerCatalogState,
    Product,
    ProductVariant,
    ProjectProduct,
    RetailOffer,
)
from shopping.catalog.resolution import ResolutionDecision, resolve_or_create
from shopping.catalog.schemas import (
    CatalogCorrectionCommand,
    CatalogCorrectionRead,
    CatalogCorrectionRevertCommand,
    CatalogNormalizationRead,
    NormalizeCandidateCommand,
    attributes_are_bounded,
    request_hash,
)
from shopping.extraction.retriever import RetrievedDocument
from shopping.extraction.schemas import CatalogExtraction
from shopping.projects.errors import ProjectError
from shopping.projects.models import ShoppingProject
from shopping.projects.repository import project_by_owner
from shopping.research.models import DiscoveryCandidate


def normalization_preflight(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    candidate_id: UUID,
    command: NormalizeCandidateCommand,
) -> tuple[CatalogNormalizationRead | None, str | None]:
    candidate = _owned_candidate(session, owner_id, project_id, candidate_id)
    event = _event_for_request(
        session, owner_id, project_id, candidate_id, command.request_key, "normalize"
    )
    if event is None:
        project = project_by_owner(session, project_id, owner_id)
        assert project is not None
        _check_project_version(project, command.expected_project_version)
        _check_catalog_version(session, owner_id, command.expected_catalog_version)
        return None, candidate.normalized_url
    if event.request_hash != request_hash(command) or event.observation_id is None:
        raise _conflict("request_key_reused", "This request key belongs to a different command.")
    return _normalization_read(session, event, replayed=True), None


def complete_normalization(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    candidate_id: UUID,
    command: NormalizeCandidateCommand,
    document: RetrievedDocument | None,
    extraction: CatalogExtraction | None,
    failure_code: str | None = None,
    failure_status: str | None = None,
) -> CatalogNormalizationRead:
    candidate = _owned_candidate(session, owner_id, project_id, candidate_id)
    previous_mapping = candidate.canonical_mapping_id
    state = _lock_catalog_state(session, owner_id)
    project = project_by_owner(session, project_id, owner_id, lock=True)
    if project is None:
        raise _not_found("Project not found")

    # Another request with the same key may have completed while retrieval ran.
    event = _event_for_request(
        session, owner_id, project_id, candidate_id, command.request_key, "normalize"
    )
    if event is not None:
        if event.request_hash != request_hash(command) or event.observation_id is None:
            raise _conflict(
                "request_key_reused", "This request key belongs to a different command."
            )
        session.rollback()
        return _normalization_read(session, event, replayed=True)

    _check_project_version(project, command.expected_project_version)
    if state.revision != command.expected_catalog_version:
        raise _catalog_conflict(state.revision)

    now = document.retrieved_at if document else datetime.now(UTC)
    observation_id = uuid4()
    if failure_code is None and extraction is None:
        failure_code = "extraction_failed"
        failure_status = "failed"
    if failure_status not in {None, "failed", "blocked", "unsupported"}:
        failure_status = "failed"
    observation = CatalogObservation(
        id=observation_id,
        owner_id=owner_id,
        project_id=project_id,
        candidate_id=candidate_id,
        run_id=candidate.run_id,
        idempotency_key=command.request_key,
        request_hash=request_hash(command),
        requested_url=candidate.normalized_url,
        final_url=document.final_url if document else candidate.normalized_url,
        retrieved_at=now,
        content_hash=document.content_hash if document else None,
        content_type=document.content_type if document else None,
        status="succeeded" if extraction is not None else (failure_status or "failed"),
        extractor_version="httpx-page-retriever.v1",
        task_version=(extraction.task_version if extraction else "normalize_catalog_candidate.v1"),
        extraction=extraction.model_dump(mode="json") if extraction else {},
        excerpts=_excerpts(extraction) if extraction else [],
        warnings=list(extraction.warnings)
        if extraction
        else ([failure_code] if failure_code else []),
        failure_code=failure_code,
    )
    session.add(observation)
    session.flush()

    decision: ResolutionDecision | None = None
    event_status = "unresolved"
    reason = failure_code or "extraction_unavailable"
    evidence: list[dict] = []
    selected_project_product_id = candidate.canonical_mapping_id
    project_changed = False

    if extraction is not None:
        if _has_owner_correction(session, owner_id, project_id, candidate_id):
            reason = "manual_mapping_preserved"
            evidence = [{"kind": "manual_mapping_preserved"}]
            event_status = "auto_linked" if selected_project_product_id else "unresolved"
        else:
            decision = resolve_or_create(
                session,
                owner_id,
                extraction,
                observation,
                allow_create=selected_project_product_id is None,
                mutate=selected_project_product_id is None,
            )
            evidence = decision.evidence
            reason = decision.reason
            if decision.variant is not None:
                if selected_project_product_id is None:
                    project_product = _project_product_for_variant(
                        session, project, candidate, decision.variant
                    )
                    selected_project_product_id = project_product.id
                    candidate.canonical_mapping_id = project_product.id
                    project_changed = True
                    event_status = "auto_linked"
                    _attach_offer(session, owner_id, observation, extraction, decision.variant.id)
                else:
                    current_variant_id = _project_product_variant_id(
                        session, selected_project_product_id
                    )
                    if current_variant_id == decision.variant.id:
                        event_status = "auto_linked"
                        _attach_offer(
                            session, owner_id, observation, extraction, decision.variant.id
                        )
                    else:
                        reason = "existing_mapping_preserved_after_refresh"
                        event_status = "unresolved"
                        evidence = [
                            {
                                "kind": "existing_mapping_preserved",
                                "selected_variant_id": str(current_variant_id),
                                "observed_variant_id": str(decision.variant.id),
                            },
                            *evidence,
                        ]
            else:
                event_status = "unresolved"
                if selected_project_product_id is not None:
                    reason = "existing_mapping_preserved_after_unresolved_refresh"

    catalog_version = state.revision + 1
    state.revision = catalog_version
    state.updated_at = datetime.now(UTC)
    if project_changed:
        project.revision += 1
        project.updated_at = datetime.now(UTC)

    event = EntityResolutionEvent(
        id=uuid4(),
        owner_id=owner_id,
        project_id=project_id,
        candidate_id=candidate_id,
        observation_id=observation.id,
        request_key=command.request_key,
        command_type="normalize",
        request_hash=request_hash(command),
        catalog_version=catalog_version,
        project_version=project.revision,
        status=event_status,
        actor="system",
        reason=reason[:500],
        evidence=evidence,
        previous_project_product_id=previous_mapping,
        selected_project_product_id=selected_project_product_id,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return _normalization_read(session, event, replayed=False)


def exact_correction_replay(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    candidate_id: UUID,
    command: CatalogCorrectionCommand | CatalogCorrectionRevertCommand,
) -> CatalogCorrectionRead | None:
    _owned_candidate(session, owner_id, project_id, candidate_id)
    command_type = "revert" if isinstance(command, CatalogCorrectionRevertCommand) else "correction"
    event = _event_for_request(
        session, owner_id, project_id, candidate_id, command.request_key, command_type
    )
    if event is None:
        return None
    if event.request_hash != request_hash(command) or event.actor != "owner":
        raise _conflict("request_key_reused", "This request key belongs to a different command.")
    return _correction_read(event, replayed=True)


def correct_candidate(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    candidate_id: UUID,
    command: CatalogCorrectionCommand,
) -> CatalogCorrectionRead:
    candidate = _owned_candidate(session, owner_id, project_id, candidate_id)
    state = _lock_catalog_state(session, owner_id)
    project = project_by_owner(session, project_id, owner_id, lock=True)
    if project is None:
        raise _not_found("Project not found")
    event = _event_for_request(
        session, owner_id, project_id, candidate_id, command.request_key, "correction"
    )
    if event is not None:
        if event.request_hash != request_hash(command) or event.actor != "owner":
            raise _conflict(
                "request_key_reused", "This request key belongs to a different command."
            )
        session.rollback()
        return _correction_read(event, replayed=True)
    _check_project_version(project, command.expected_project_version)
    if state.revision != command.expected_catalog_version:
        raise _catalog_conflict(state.revision)

    previous = candidate.canonical_mapping_id
    event_id = uuid4()
    product: Product
    variant: ProductVariant
    if command.target_variant_id is not None:
        variant = session.scalar(
            select(ProductVariant)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(
                ProductVariant.id == command.target_variant_id,
                Product.owner_id == owner_id,
            )
        )
        if variant is None:
            raise _not_found("Product variant not found")
        product = session.get(Product, variant.product_id)
    elif command.new_variant is not None:
        product = session.scalar(
            select(Product).where(
                Product.id == command.new_variant.product_id,
                Product.owner_id == owner_id,
            )
        )
        if product is None:
            raise _not_found("Product not found")
        variant = _user_variant(
            session,
            product,
            command.new_variant.display_name,
            command.new_variant.identity_attributes,
            command.new_variant.category_attributes,
            event_id,
        )
    else:
        assert command.new_product is not None
        product = Product(
            id=uuid4(),
            owner_id=owner_id,
            canonical_name=command.new_product.canonical_name,
            brand=command.new_product.brand,
            brand_key=_normalize_text(command.new_product.brand),
            category=_normalize_text(command.new_product.category) or None,
            model_family=command.new_product.model_family,
            revision=1,
        )
        session.add(product)
        session.flush()
        variant = _user_variant(
            session,
            product,
            command.new_product.variant_name,
            command.new_product.identity_attributes,
            command.new_product.category_attributes,
            event_id,
        )

    project_product = _project_product_for_variant(session, project, candidate, variant)
    selected = project_product.id
    if selected != previous:
        candidate.canonical_mapping_id = selected
        project.revision += 1
        project.updated_at = datetime.now(UTC)
    next_catalog_version = state.revision + 1
    state.revision = next_catalog_version
    state.updated_at = datetime.now(UTC)
    event = EntityResolutionEvent(
        id=event_id,
        owner_id=owner_id,
        project_id=project_id,
        candidate_id=candidate_id,
        request_key=command.request_key,
        command_type="correction",
        request_hash=request_hash(command),
        catalog_version=next_catalog_version,
        project_version=project.revision,
        status="manual_linked",
        actor="owner",
        reason=command.reason,
        evidence=[{"kind": "manual_variant_assignment", "variant_id": str(variant.id)}],
        previous_project_product_id=previous,
        selected_project_product_id=selected,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return _correction_read(event, replayed=False)


def revert_candidate_correction(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    candidate_id: UUID,
    command: CatalogCorrectionRevertCommand,
) -> CatalogCorrectionRead:
    candidate = _owned_candidate(session, owner_id, project_id, candidate_id)
    state = _lock_catalog_state(session, owner_id)
    project = project_by_owner(session, project_id, owner_id, lock=True)
    if project is None:
        raise _not_found("Project not found")
    event = _event_for_request(
        session, owner_id, project_id, candidate_id, command.request_key, "revert"
    )
    if event is not None:
        if event.request_hash != request_hash(command) or event.actor != "owner":
            raise _conflict(
                "request_key_reused", "This request key belongs to a different command."
            )
        session.rollback()
        return _correction_read(event, replayed=True)
    _check_project_version(project, command.expected_project_version)
    if state.revision != command.expected_catalog_version:
        raise _catalog_conflict(state.revision)

    latest_manual = session.scalar(
        select(EntityResolutionEvent)
        .where(
            EntityResolutionEvent.owner_id == owner_id,
            EntityResolutionEvent.project_id == project_id,
            EntityResolutionEvent.candidate_id == candidate_id,
            EntityResolutionEvent.actor == "owner",
            EntityResolutionEvent.status == "manual_linked",
            EntityResolutionEvent.id.not_in(
                select(EntityResolutionEvent.reversed_event_id).where(
                    EntityResolutionEvent.owner_id == owner_id,
                    EntityResolutionEvent.project_id == project_id,
                    EntityResolutionEvent.candidate_id == candidate_id,
                    EntityResolutionEvent.reversed_event_id.is_not(None),
                )
            ),
        )
        .order_by(EntityResolutionEvent.created_at.desc(), EntityResolutionEvent.id.desc())
    )
    # A correction is already reverted when another event points back to it.
    if latest_manual is None:
        raise _conflict("nothing_to_revert", "There is no active manual correction to revert.")
    if candidate.canonical_mapping_id != latest_manual.selected_project_product_id:
        raise _conflict("mapping_changed", "The candidate mapping changed after that correction.")

    selected = latest_manual.previous_project_product_id
    previous = candidate.canonical_mapping_id
    if selected != previous:
        candidate.canonical_mapping_id = selected
        project.revision += 1
        project.updated_at = datetime.now(UTC)
    next_catalog_version = state.revision + 1
    state.revision = next_catalog_version
    state.updated_at = datetime.now(UTC)
    event = EntityResolutionEvent(
        id=uuid4(),
        owner_id=owner_id,
        project_id=project_id,
        candidate_id=candidate_id,
        request_key=command.request_key,
        command_type="revert",
        request_hash=request_hash(command),
        catalog_version=next_catalog_version,
        project_version=project.revision,
        status="reverted",
        actor="owner",
        reason="Reverted the latest manual candidate assignment.",
        evidence=[{"kind": "manual_correction_reverted", "event_id": str(latest_manual.id)}],
        previous_project_product_id=previous,
        selected_project_product_id=selected,
        reversed_event_id=latest_manual.id,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return _correction_read(event, replayed=False)


def _lock_catalog_state(session: Session, owner_id: UUID) -> OwnerCatalogState:
    session.execute(
        pg_insert(OwnerCatalogState)
        .values(owner_id=owner_id, revision=1)
        .on_conflict_do_nothing(index_elements=[OwnerCatalogState.owner_id])
    )
    state = session.scalar(
        select(OwnerCatalogState).where(OwnerCatalogState.owner_id == owner_id).with_for_update()
    )
    assert state is not None
    return state


def _check_catalog_version(session: Session, owner_id: UUID, expected: int) -> None:
    current = (
        session.scalar(
            select(OwnerCatalogState.revision).where(OwnerCatalogState.owner_id == owner_id)
        )
        or 1
    )
    if current != expected:
        raise _catalog_conflict(current)


def _check_project_version(project: ShoppingProject, expected: int) -> None:
    if project.revision != expected:
        raise ProjectError(
            409,
            "revision_conflict",
            "This project changed since it was loaded. Review the latest version before saving.",
            {"current_version": project.revision},
        )


def _owned_candidate(
    session: Session, owner_id: UUID, project_id: UUID, candidate_id: UUID
) -> DiscoveryCandidate:
    project = project_by_owner(session, project_id, owner_id)
    if project is None:
        raise _not_found("Project not found")
    candidate = session.scalar(
        select(DiscoveryCandidate).where(
            DiscoveryCandidate.id == candidate_id,
            DiscoveryCandidate.project_id == project_id,
        )
    )
    if candidate is None:
        raise _not_found("Candidate not found")
    return candidate


def _event_for_request(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    candidate_id: UUID,
    request_key: str,
    command_type: str,
) -> EntityResolutionEvent | None:
    event = session.scalar(
        select(EntityResolutionEvent).where(
            EntityResolutionEvent.owner_id == owner_id,
            EntityResolutionEvent.project_id == project_id,
            EntityResolutionEvent.command_type == command_type,
            EntityResolutionEvent.request_key == request_key,
        )
    )
    if event is not None and event.candidate_id != candidate_id:
        raise _conflict("request_key_reused", "This request key belongs to a different command.")
    return event


def _has_owner_correction(
    session: Session, owner_id: UUID, project_id: UUID, candidate_id: UUID
) -> bool:
    candidate = _owned_candidate(session, owner_id, project_id, candidate_id)
    reversed_events = select(EntityResolutionEvent.reversed_event_id).where(
        EntityResolutionEvent.owner_id == owner_id,
        EntityResolutionEvent.project_id == project_id,
        EntityResolutionEvent.candidate_id == candidate_id,
        EntityResolutionEvent.reversed_event_id.is_not(None),
    )
    active_correction = session.scalar(
        select(EntityResolutionEvent)
        .where(
            EntityResolutionEvent.owner_id == owner_id,
            EntityResolutionEvent.project_id == project_id,
            EntityResolutionEvent.candidate_id == candidate_id,
            EntityResolutionEvent.actor == "owner",
            EntityResolutionEvent.status == "manual_linked",
            EntityResolutionEvent.id.not_in(reversed_events),
        )
        .order_by(EntityResolutionEvent.created_at.desc(), EntityResolutionEvent.id.desc())
        .limit(1)
    )
    return bool(
        active_correction
        and candidate.canonical_mapping_id == active_correction.selected_project_product_id
    )


def _project_product_for_variant(
    session: Session,
    project: ShoppingProject,
    candidate: DiscoveryCandidate,
    variant: ProductVariant,
) -> ProjectProduct:
    existing = session.scalar(
        select(ProjectProduct).where(
            ProjectProduct.project_id == project.id,
            ProjectProduct.variant_id == variant.id,
        )
    )
    if existing is not None:
        return existing
    project_product = ProjectProduct(
        id=uuid4(),
        project_id=project.id,
        variant_id=variant.id,
        first_candidate_id=candidate.id,
        first_run_id=candidate.run_id,
        discovery_reason=candidate.discovery_reason[:300],
    )
    session.add(project_product)
    session.flush()
    return project_product


def _project_product_variant_id(session: Session, project_product_id: UUID) -> UUID | None:
    return session.scalar(
        select(ProjectProduct.variant_id).where(ProjectProduct.id == project_product_id)
    )


def _attach_offer(
    session: Session,
    owner_id: UUID,
    observation: CatalogObservation,
    extraction: CatalogExtraction,
    variant_id: UUID,
) -> None:
    offer = extraction.offer
    if offer is None:
        return
    from urllib.parse import urlsplit

    parsed = urlsplit(observation.final_url)
    if parsed.username or parsed.password or not parsed.hostname:
        return
    session.add(
        RetailOffer(
            id=uuid4(),
            owner_id=owner_id,
            variant_id=variant_id,
            observation_id=observation.id,
            idempotency_key=f"catalog-observation:{observation.id}",
            retailer_name=offer.retailer_name,
            retailer_domain=parsed.hostname.casefold().removeprefix("www."),
            url=observation.final_url,
            amount=offer.amount,
            currency=offer.currency,
            availability=offer.availability,
            condition=offer.condition,
            observed_at=observation.retrieved_at,
        )
    )


def _user_variant(
    session: Session,
    product: Product,
    display_name: str,
    identity_attributes: dict,
    category_attributes: list,
    event_id: UUID,
) -> ProductVariant:
    from shopping.catalog.resolution import _identity_key

    identity_key = _identity_key(identity_attributes)
    duplicate_id = session.scalar(
        select(ProductVariant.id).where(
            ProductVariant.product_id == product.id,
            ProductVariant.identity_key == identity_key,
        )
    )
    if duplicate_id is not None:
        raise _conflict("variant_identity_exists", "Select the existing variant instead.")

    identity = {
        key: {
            "value": value,
            "origin": "user_correction",
            "correction_event_id": str(event_id),
        }
        for key, value in identity_attributes.items()
    }
    category = {
        item.key: {
            "value": item.value,
            "unit": item.unit,
            "origin": "user_correction",
            "correction_event_id": str(event_id),
        }
        for item in category_attributes
    }
    if not attributes_are_bounded(identity) or not attributes_are_bounded(category):
        raise ProjectError(
            422,
            "attributes_too_large",
            "The correction attributes exceed the supported catalog size.",
        )
    variant = ProductVariant(
        id=uuid4(),
        product_id=product.id,
        display_name=display_name,
        identity_key=identity_key,
        identity_attributes=identity,
        category_attributes=category,
        revision=1,
    )
    session.add(variant)
    session.flush()
    return variant


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    from shopping.catalog.resolution import normalize_text

    return normalize_text(value) or None


def _excerpts(extraction: CatalogExtraction | None) -> list[str]:
    if extraction is None:
        return []
    values = [extraction.product_name_excerpt]
    values.extend(
        value
        for value in (
            extraction.brand_excerpt,
            extraction.category_excerpt,
            extraction.model_family_excerpt,
        )
        if value
    )
    values.extend(item.excerpt for item in extraction.identifiers)
    values.extend(item.excerpt for item in extraction.attributes)
    values.extend(extraction.variant_attribute_excerpts.values())
    if extraction.offer:
        values.append(extraction.offer.excerpt)
    return list(dict.fromkeys(values))[:64]


def _normalization_read(
    session: Session, event: EntityResolutionEvent, *, replayed: bool
) -> CatalogNormalizationRead:
    observation = (
        session.get(CatalogObservation, event.observation_id) if event.observation_id else None
    )
    product_id = variant_id = None
    if event.selected_project_product_id:
        row = session.execute(
            select(ProjectProduct.variant_id, ProductVariant.product_id)
            .join(ProductVariant, ProductVariant.id == ProjectProduct.variant_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(
                ProjectProduct.id == event.selected_project_product_id,
                ProjectProduct.project_id == event.project_id,
                Product.owner_id == event.owner_id,
            )
        ).first()
        if row:
            variant_id, product_id = row
    return CatalogNormalizationRead(
        candidate_id=event.candidate_id,
        observation_id=event.observation_id,
        event_id=event.id,
        status=(
            observation.status
            if observation is not None and observation.status != "succeeded"
            else event.status
        ),
        project_product_id=event.selected_project_product_id,
        product_id=product_id,
        variant_id=variant_id,
        catalog_version=event.catalog_version,
        project_version=event.project_version,
        reason=event.reason,
        failure_code=observation.failure_code if observation else None,
        warnings=observation.warnings if observation else [],
        observed_at=observation.retrieved_at if observation else event.created_at,
        replayed=replayed,
    )


def _correction_read(event: EntityResolutionEvent, *, replayed: bool) -> CatalogCorrectionRead:
    return CatalogCorrectionRead(
        candidate_id=event.candidate_id,
        event_id=event.id,
        status=event.status,
        previous_project_product_id=event.previous_project_product_id,
        selected_project_product_id=event.selected_project_product_id,
        catalog_version=event.catalog_version,
        project_version=event.project_version,
        reason=event.reason,
        replayed=replayed,
    )


def _catalog_conflict(current: int) -> ProjectError:
    return ProjectError(
        409,
        "catalog_revision_conflict",
        "The catalog changed since it was loaded. Refresh the catalog before continuing.",
        {"current_catalog_version": current},
    )


def _not_found(message: str) -> ProjectError:
    return ProjectError(404, "not_found", message)


def _conflict(code: str, message: str) -> ProjectError:
    return ProjectError(409, code, message)
