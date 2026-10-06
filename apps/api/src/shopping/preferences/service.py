from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shopping.catalog.models import ProjectProduct
from shopping.preferences.models import PreferenceCandidate, ShoppingPreference, ShoppingProfile
from shopping.preferences.schemas import (
    CandidateAction,
    CandidateCreate,
    CandidateMutation,
    PreferenceCandidateRead,
    PreferencePatch,
    PreferenceRead,
    PreferenceSuggestionsRead,
    ProfilePatch,
    ProfileRead,
    _validate_money_preference,
    _validate_preference_criterion,
    preference_applies_to_category,
    preference_is_suggestible,
    promotable_requirement_kind,
)
from shopping.projects.errors import ProjectError
from shopping.projects.models import (
    ProjectProductDecision,
    ProjectRequirement,
    ShoppingProject,
)
from shopping.projects.schemas import ProjectRead, validate_criterion_fields
from shopping.projects.service import _project_read


def get_profile(session: Session, owner_id: UUID) -> ProfileRead:
    profile = _get_or_create_profile(session, owner_id)
    _commit(session)
    return _profile_read(session, profile)


def patch_profile(session: Session, owner_id: UUID, command: ProfilePatch) -> ProfileRead:
    profile = _get_or_create_profile(session, owner_id, lock=True)
    _check_profile_version(profile, command.expected_version)
    if profile.reuse_enabled != command.reuse_enabled:
        profile.reuse_enabled = command.reuse_enabled
        profile.revision += 1
        profile.updated_at = datetime.now(UTC)
    _commit(session)
    return _profile_read(session, profile)


def create_candidate(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    command: CandidateCreate,
) -> CandidateMutation:
    profile = _get_or_create_profile(session, owner_id, lock=True)
    project = session.scalar(
        select(ShoppingProject)
        .where(
            ShoppingProject.id == project_id,
            ShoppingProject.owner_id == owner_id,
            ShoppingProject.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if project is None:
        raise _not_found("Project not found")
    requirement = None
    project_product = None
    decision = None
    if command.source_requirement_id is not None:
        requirement = session.scalar(
            select(ProjectRequirement).where(
                ProjectRequirement.id == command.source_requirement_id,
                ProjectRequirement.project_id == project.id,
            )
        )
        if requirement is None:
            raise _not_found("Project requirement not found")
        if not promotable_requirement_kind(requirement.kind):
            raise _invalid("Only a project preference can be proposed for profile reuse")
        source_kind = "requirement"
        source_reference = requirement.id
    else:
        project_product = session.scalar(
            select(ProjectProduct).where(
                ProjectProduct.id == command.source_project_product_id,
                ProjectProduct.project_id == project.id,
            )
        )
        decision = (
            session.scalar(
                select(ProjectProductDecision).where(
                    ProjectProductDecision.project_product_id == project_product.id,
                    ProjectProductDecision.project_id == project.id,
                    ProjectProductDecision.owner_id == owner_id,
                    ProjectProductDecision.state == "rejected",
                )
            )
            if project_product is not None
            else None
        )
        if project_product is None or decision is None:
            raise _not_found("Rejected product judgment not found")
        source_kind = "decision"
        source_reference = project_product.id
    if project.revision != command.expected_project_version:
        raise _conflict(
            "revision_conflict",
            "The project changed before this preference candidate was saved",
            {"current_version": project.revision},
        )

    scopes = sorted(command.category_scopes)
    proposition = {
        "label": command.label,
        "key": command.key,
        "operator": command.operator,
        "value": command.value,
        "unit": command.unit,
        "monetary": command.monetary,
        "category_scopes": scopes,
    }
    proposition_hash = hashlib.sha256(_canonical(proposition).encode()).hexdigest()
    existing_query = select(PreferenceCandidate).where(
        PreferenceCandidate.owner_id == owner_id,
        PreferenceCandidate.source_kind == source_kind,
        PreferenceCandidate.source_project_revision == project.revision,
        PreferenceCandidate.proposition_hash == proposition_hash,
    )
    existing_query = existing_query.where(
        PreferenceCandidate.source_requirement_id == source_reference
        if source_kind == "requirement"
        else PreferenceCandidate.source_project_product_id == source_reference
    )
    existing = session.scalar(existing_query)
    if existing is not None:
        if existing.status == "dismissed":
            raise _conflict(
                "candidate_dismissed",
                "This proposition was dismissed for the current project version",
            )
        return CandidateMutation(candidate=_candidate_read(session, existing), replayed=True)

    _check_profile_version(profile, command.expected_profile_version)

    pending_count = session.scalar(
        select(func.count(PreferenceCandidate.id)).where(
            PreferenceCandidate.owner_id == owner_id,
            PreferenceCandidate.status == "pending",
        )
    )
    if pending_count is not None and pending_count >= 100:
        raise _invalid("A profile can have at most 100 pending candidates; resolve one first")

    candidate = PreferenceCandidate(
        owner_id=owner_id,
        source_project_id=project.id,
        source_requirement_id=requirement.id if requirement else None,
        source_kind=source_kind,
        source_project_product_id=project_product.id if project_product else None,
        source_decision_id=decision.id if decision else None,
        source_project_revision=project.revision,
        proposition_hash=proposition_hash,
        key=command.key,
        operator=command.operator,
        value=command.value,
        unit=command.unit,
        monetary=command.monetary,
        category_scopes=scopes,
        label=command.label,
        rationale=command.rationale,
        status="pending",
    )
    session.add(candidate)
    profile.revision += 1
    profile.updated_at = datetime.now(UTC)
    _commit(session)
    session.refresh(candidate)
    return CandidateMutation(candidate=_candidate_read(session, candidate))


def accept_candidate(
    session: Session, owner_id: UUID, candidate_id: UUID, command: CandidateAction
) -> CandidateMutation:
    profile = _get_or_create_profile(session, owner_id, lock=True)
    candidate = session.scalar(
        select(PreferenceCandidate)
        .where(
            PreferenceCandidate.id == candidate_id,
            PreferenceCandidate.owner_id == owner_id,
        )
        .with_for_update()
    )
    if candidate is None:
        raise _not_found("Preference candidate not found")
    if candidate.status == "accepted":
        preference = session.scalar(
            select(ShoppingPreference).where(
                ShoppingPreference.source_candidate_id == candidate.id,
                ShoppingPreference.owner_id == owner_id,
            )
        )
        return CandidateMutation(
            candidate=_candidate_read(session, candidate),
            preference=_preference_read(session, preference) if preference else None,
            replayed=True,
        )
    _check_profile_version(profile, command.expected_profile_version)
    if candidate.status != "pending":
        raise _conflict("candidate_resolved", "This preference candidate is no longer pending")

    project = session.scalar(
        select(ShoppingProject)
        .where(
            ShoppingProject.id == candidate.source_project_id,
            ShoppingProject.owner_id == owner_id,
            ShoppingProject.deleted_at.is_(None),
        )
        .with_for_update()
    )
    requirement = (
        session.scalar(
            select(ProjectRequirement).where(
                ProjectRequirement.id == candidate.source_requirement_id,
                ProjectRequirement.project_id == candidate.source_project_id,
            )
        )
        if project is not None
        else None
    )
    source_decision = (
        session.scalar(
            select(ProjectProductDecision).where(
                ProjectProductDecision.id == candidate.source_decision_id,
                ProjectProductDecision.project_id == candidate.source_project_id,
                ProjectProductDecision.project_product_id == candidate.source_project_product_id,
                ProjectProductDecision.owner_id == owner_id,
                ProjectProductDecision.state == "rejected",
            )
        )
        if project is not None and candidate.source_kind == "decision"
        else None
    )
    source_exists = (
        requirement is not None
        if candidate.source_kind == "requirement"
        else source_decision is not None
    )
    if (
        project is None
        or not source_exists
        or project.revision != candidate.source_project_revision
    ):
        candidate.status = "stale"
        candidate.resolved_at = datetime.now(UTC)
        profile.revision += 1
        profile.updated_at = datetime.now(UTC)
        _commit(session)
        raise _conflict(
            "candidate_stale",
            "The source project changed. Review it and create a new candidate before accepting.",
            {"source_project_revision": candidate.source_project_revision},
        )

    preference_count = session.scalar(
        select(func.count(ShoppingPreference.id)).where(
            ShoppingPreference.owner_id == owner_id,
            ShoppingPreference.profile_id == profile.id,
            ShoppingPreference.status == "active",
        )
    )
    if preference_count is not None and preference_count >= 100:
        raise _invalid("A shopping profile can contain at most 100 active preferences")

    now = datetime.now(UTC)
    preference = ShoppingPreference(
        profile_id=profile.id,
        owner_id=owner_id,
        source_candidate_id=candidate.id,
        source_project_id=project.id,
        source_requirement_id=requirement.id if requirement else None,
        source_kind=candidate.source_kind,
        source_project_product_id=candidate.source_project_product_id,
        source_decision_id=candidate.source_decision_id,
        key=candidate.key,
        operator=candidate.operator,
        value=candidate.value,
        unit=candidate.unit,
        monetary=candidate.monetary,
        category_scopes=candidate.category_scopes,
        label=candidate.label,
        strength="soft",
        status="active",
        revision=1,
        accepted_at=now,
        updated_at=now,
    )
    candidate.status = "accepted"
    candidate.resolved_at = now
    profile.revision += 1
    profile.updated_at = now
    session.add(preference)
    _commit(session)
    session.refresh(candidate)
    session.refresh(preference)
    return CandidateMutation(
        candidate=_candidate_read(session, candidate),
        preference=_preference_read(session, preference),
    )


def dismiss_candidate(
    session: Session, owner_id: UUID, candidate_id: UUID, command: CandidateAction
) -> CandidateMutation:
    profile = _get_or_create_profile(session, owner_id, lock=True)
    candidate = session.scalar(
        select(PreferenceCandidate)
        .where(
            PreferenceCandidate.id == candidate_id,
            PreferenceCandidate.owner_id == owner_id,
        )
        .with_for_update()
    )
    if candidate is None:
        raise _not_found("Preference candidate not found")
    if candidate.status == "dismissed":
        return CandidateMutation(candidate=_candidate_read(session, candidate), replayed=True)
    _check_profile_version(profile, command.expected_profile_version)
    if candidate.status != "pending":
        raise _conflict("candidate_resolved", "This preference candidate is no longer pending")
    candidate.status = "dismissed"
    candidate.resolved_at = datetime.now(UTC)
    profile.revision += 1
    profile.updated_at = datetime.now(UTC)
    _commit(session)
    session.refresh(candidate)
    return CandidateMutation(candidate=_candidate_read(session, candidate))


def patch_preference(
    session: Session,
    owner_id: UUID,
    preference_id: UUID,
    command: PreferencePatch,
) -> ProfileRead:
    profile = _get_or_create_profile(session, owner_id, lock=True)
    preference = session.scalar(
        select(ShoppingPreference)
        .where(
            ShoppingPreference.id == preference_id,
            ShoppingPreference.owner_id == owner_id,
            ShoppingPreference.profile_id == profile.id,
        )
        .with_for_update()
    )
    if preference is None:
        raise _not_found("Preference not found")
    _check_profile_version(profile, command.expected_profile_version)
    if preference.revision != command.expected_preference_revision:
        raise _conflict(
            "preference_revision_conflict",
            "This preference changed since it was loaded",
            {"current_preference_revision": preference.revision},
        )
    changes = command.model_dump(
        exclude_unset=True,
        exclude={"expected_profile_version", "expected_preference_revision"},
    )
    if "value" in changes and changes["value"] is None:
        raise _invalid("Preference value cannot be cleared")
    if "operator" in changes and changes["operator"] is None:
        changes["operator"] = None
    if changes.get("status") == "active" and preference.status != "active":
        active_count = session.scalar(
            select(func.count(ShoppingPreference.id)).where(
                ShoppingPreference.owner_id == owner_id,
                ShoppingPreference.profile_id == profile.id,
                ShoppingPreference.status == "active",
            )
        )
        if active_count is not None and active_count >= 100:
            raise _invalid("A shopping profile can contain at most 100 active preferences")
    for field, value in changes.items():
        if field == "category_scopes":
            value = sorted(value)
        if field == "status" and value not in {"active", "revoked"}:
            raise _invalid("Preference status is invalid")
        setattr(preference, field, value)
    try:
        _validate_preference_criterion(
            preference.key, preference.operator, preference.value, preference.unit
        )
        preference.unit = _validate_money_preference(
            preference.monetary,
            preference.key,
            preference.value,
            preference.unit,
            preference.category_scopes,
        )
    except ValueError as error:
        raise _invalid(str(error)) from error
    preference.revision += 1
    preference.updated_at = datetime.now(UTC)
    profile.revision += 1
    profile.updated_at = datetime.now(UTC)
    _commit(session)
    return _profile_read(session, profile)


def revoke_preference(
    session: Session,
    owner_id: UUID,
    preference_id: UUID,
    expected_profile_version: int,
) -> ProfileRead:
    profile = _get_or_create_profile(session, owner_id, lock=True)
    preference = session.scalar(
        select(ShoppingPreference)
        .where(
            ShoppingPreference.id == preference_id,
            ShoppingPreference.owner_id == owner_id,
            ShoppingPreference.profile_id == profile.id,
        )
        .with_for_update()
    )
    if preference is None:
        raise _not_found("Preference not found")
    if preference.status == "revoked":
        return _profile_read(session, profile)
    _check_profile_version(profile, expected_profile_version)
    preference.status = "revoked"
    preference.revision += 1
    preference.updated_at = datetime.now(UTC)
    profile.revision += 1
    profile.updated_at = datetime.now(UTC)
    _commit(session)
    return _profile_read(session, profile)


def preference_suggestions(
    session: Session, owner_id: UUID, project_id: UUID
) -> PreferenceSuggestionsRead:
    project = session.scalar(
        select(ShoppingProject).where(
            ShoppingProject.id == project_id,
            ShoppingProject.owner_id == owner_id,
            ShoppingProject.deleted_at.is_(None),
        )
    )
    if project is None:
        raise _not_found("Project not found")
    profile = _get_or_create_profile(session, owner_id)
    _commit(session)
    eligible = []
    if project.reuse_preferences and profile.reuse_enabled and project.category:
        preferences = session.scalars(
            select(ShoppingPreference)
            .where(
                ShoppingPreference.owner_id == owner_id,
                ShoppingPreference.profile_id == profile.id,
                ShoppingPreference.status == "active",
            )
            .order_by(ShoppingPreference.accepted_at, ShoppingPreference.id)
            .limit(100)
        ).all()
        already_applied = set(
            session.scalars(
                select(ProjectRequirement.source_preference_id).where(
                    ProjectRequirement.project_id == project.id,
                    ProjectRequirement.source_preference_id.is_not(None),
                )
            ).all()
        )
        eligible = [
            _preference_read(session, item)
            for item in preferences
            if preference_is_suggestible(
                item.status,
                item.category_scopes,
                project.category,
                profile_reuse_enabled=profile.reuse_enabled,
                project_reuse_enabled=project.reuse_preferences,
                already_applied=item.id in already_applied,
            )
        ][:20]
    return PreferenceSuggestionsRead(
        reuse_enabled=project.reuse_preferences,
        profile_reuse_enabled=profile.reuse_enabled,
        profile_revision=profile.revision,
        items=eligible,
    )


def apply_preference(
    session: Session,
    owner_id: UUID,
    project_id: UUID,
    preference_id: UUID,
    expected_project_version: int,
    expected_preference_revision: int,
    expected_profile_version: int,
) -> ProjectRead:
    # Profile writers and application share profile -> project -> preference lock order.
    profile = _get_or_create_profile(session, owner_id, lock=True)
    _check_profile_version(profile, expected_profile_version)
    project = session.scalar(
        select(ShoppingProject)
        .where(
            ShoppingProject.id == project_id,
            ShoppingProject.owner_id == owner_id,
            ShoppingProject.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if project is None:
        raise _not_found("Project not found")
    if project.revision != expected_project_version:
        raise _conflict(
            "revision_conflict",
            "The project changed before this preference was applied",
            {"current_version": project.revision},
        )
    if not project.reuse_preferences or not profile.reuse_enabled:
        raise _conflict("preference_reuse_disabled", "Preference reuse is disabled")
    preference = session.scalar(
        select(ShoppingPreference)
        .where(
            ShoppingPreference.id == preference_id,
            ShoppingPreference.owner_id == owner_id,
            ShoppingPreference.profile_id == profile.id,
            ShoppingPreference.status == "active",
        )
        .with_for_update()
    )
    if preference is None:
        raise _not_found("Active preference not found")
    if preference.revision != expected_preference_revision:
        raise _conflict(
            "preference_revision_conflict",
            "This preference changed since suggestions were loaded",
            {"current_preference_revision": preference.revision},
        )
    if not preference_applies_to_category(preference.category_scopes, project.category):
        raise _conflict(
            "preference_scope_mismatch", "This preference does not apply to this category"
        )
    if (
        session.scalar(
            select(ProjectRequirement.id).where(
                ProjectRequirement.project_id == project.id,
                ProjectRequirement.source_preference_id == preference.id,
            )
        )
        is not None
    ):
        raise _conflict("preference_already_applied", "This preference is already applied")
    requirements = list(
        session.scalars(
            select(ProjectRequirement).where(ProjectRequirement.project_id == project.id)
        ).all()
    )
    if len(requirements) >= 100:
        raise _invalid("A project can have at most 100 requirements")
    now = datetime.now(UTC)
    is_typed = preference.key != "statement"
    if is_typed:
        try:
            validate_criterion_fields(
                preference.key, preference.operator, preference.value, preference.unit or None
            )
        except ValueError as error:
            raise _invalid(str(error)) from error
    statement_value = preference.value if not is_typed else None
    statement_detail = (
        statement_value
        if isinstance(statement_value, str)
        else json.dumps(statement_value, ensure_ascii=False, separators=(",", ":"))
        if statement_value is not None
        else ""
    )
    requirement = ProjectRequirement(
        project_id=project.id,
        kind="preference",
        label=preference.label,
        detail=(
            statement_detail
            if not is_typed
            else "Suggested from your shopping profile; edit this project requirement at any time."
        ),
        attribute_key=preference.key if is_typed else None,
        operator=preference.operator if is_typed else None,
        value=preference.value if is_typed else None,
        unit=preference.unit or None,
        position=len(requirements),
        origin="user",
        source_preference_id=preference.id,
        source_preference_revision=preference.revision,
        source_preference_scope=preference.category_scopes,
        created_at=now,
        updated_at=now,
    )
    session.add(requirement)
    project.revision += 1
    project.updated_at = now
    _commit(session)
    session.refresh(project)
    return _project_read(session, project)


def _get_or_create_profile(
    session: Session, owner_id: UUID, *, lock: bool = False
) -> ShoppingProfile:
    statement = select(ShoppingProfile).where(ShoppingProfile.owner_id == owner_id)
    if lock:
        statement = statement.with_for_update()
    profile = session.scalar(statement)
    if profile is None:
        session.execute(
            pg_insert(ShoppingProfile)
            .values(owner_id=owner_id, reuse_enabled=True, revision=1)
            .on_conflict_do_nothing(index_elements=[ShoppingProfile.owner_id])
        )
        statement = select(ShoppingProfile).where(ShoppingProfile.owner_id == owner_id)
        if lock:
            statement = statement.with_for_update()
        profile = session.scalar(statement)
    if profile is None:
        raise RuntimeError("Shopping profile creation did not produce a profile")
    return profile


def _profile_read(session: Session, profile: ShoppingProfile) -> ProfileRead:
    preferences = session.scalars(
        select(ShoppingPreference)
        .where(
            ShoppingPreference.profile_id == profile.id,
            ShoppingPreference.owner_id == profile.owner_id,
        )
        .order_by(
            (ShoppingPreference.status == "active").desc(),
            ShoppingPreference.accepted_at.desc(),
            ShoppingPreference.id,
        )
        .limit(100)
    ).all()
    candidates = session.scalars(
        select(PreferenceCandidate)
        .where(PreferenceCandidate.owner_id == profile.owner_id)
        .order_by(
            (PreferenceCandidate.status == "pending").desc(),
            PreferenceCandidate.created_at.desc(),
            PreferenceCandidate.id,
        )
        .limit(100)
    ).all()
    return ProfileRead(
        id=profile.id,
        revision=profile.revision,
        reuse_enabled=profile.reuse_enabled,
        preferences=[_preference_read(session, item) for item in preferences],
        candidates=[_candidate_read(session, item) for item in candidates],
        updated_at=profile.updated_at,
    )


def _preference_read(session: Session, preference: ShoppingPreference) -> PreferenceRead:
    project = (
        session.get(ShoppingProject, preference.source_project_id)
        if preference.source_project_id
        else None
    )
    requirement = (
        session.get(ProjectRequirement, preference.source_requirement_id)
        if preference.source_requirement_id
        else None
    )
    source_decision = (
        session.get(ProjectProductDecision, preference.source_decision_id)
        if preference.source_decision_id
        else None
    )
    return PreferenceRead(
        id=preference.id,
        source_kind=preference.source_kind,
        source_candidate_id=preference.source_candidate_id,
        source_project_id=preference.source_project_id,
        source_requirement_id=preference.source_requirement_id,
        source_project_product_id=preference.source_project_product_id,
        source_decision_id=preference.source_decision_id,
        source_project_title=project.title if project and project.deleted_at is None else None,
        source_available=bool(
            project
            and project.deleted_at is None
            and (
                requirement
                if preference.source_kind == "requirement"
                else source_decision
                and source_decision.project_id == preference.source_project_id
                and source_decision.project_product_id == preference.source_project_product_id
                and source_decision.state == "rejected"
            )
        ),
        key=preference.key,
        operator=preference.operator,
        value=preference.value,
        unit=preference.unit,
        monetary=preference.monetary,
        category_scopes=preference.category_scopes,
        label=preference.label,
        strength=preference.strength,
        status=preference.status,
        revision=preference.revision,
        accepted_at=preference.accepted_at,
        updated_at=preference.updated_at,
    )


def _candidate_read(session: Session, candidate: PreferenceCandidate) -> PreferenceCandidateRead:
    project = (
        session.get(ShoppingProject, candidate.source_project_id)
        if candidate.source_project_id
        else None
    )
    requirement = (
        session.get(ProjectRequirement, candidate.source_requirement_id)
        if candidate.source_requirement_id
        else None
    )
    source_decision = (
        session.get(ProjectProductDecision, candidate.source_decision_id)
        if candidate.source_decision_id
        else None
    )
    source_available = (
        requirement is not None
        if candidate.source_kind == "requirement"
        else bool(
            candidate.source_project_product_id
            and source_decision
            and source_decision.project_id == candidate.source_project_id
            and source_decision.project_product_id == candidate.source_project_product_id
            and source_decision.state == "rejected"
        )
    )
    available = bool(project and project.deleted_at is None and source_available)
    stale = (
        candidate.status == "stale"
        or not available
        or bool(project and project.revision != candidate.source_project_revision)
    )
    return PreferenceCandidateRead(
        id=candidate.id,
        source_kind=candidate.source_kind,
        source_project_id=candidate.source_project_id,
        source_requirement_id=candidate.source_requirement_id,
        source_project_product_id=candidate.source_project_product_id,
        source_decision_id=candidate.source_decision_id,
        source_project_revision=candidate.source_project_revision,
        source_project_title=project.title if available else None,
        source_available=available,
        source_stale=stale,
        label=candidate.label,
        key=candidate.key,
        operator=candidate.operator,
        value=candidate.value,
        unit=candidate.unit,
        monetary=candidate.monetary,
        category_scopes=candidate.category_scopes,
        rationale=candidate.rationale,
        status=candidate.status,
        created_at=candidate.created_at,
        resolved_at=candidate.resolved_at,
    )


def _check_profile_version(profile: ShoppingProfile, expected_version: int) -> None:
    if profile.revision != expected_version:
        raise _conflict(
            "profile_revision_conflict",
            "The shopping profile changed since it was loaded",
            {"current_version": profile.revision},
        )


def _canonical(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise _invalid("Shopping preference data violates a database constraint") from error


def _not_found(message: str) -> ProjectError:
    return ProjectError(404, "not_found", message)


def _invalid(message: str) -> ProjectError:
    return ProjectError(422, "invalid_request", message)


def _conflict(code: str, message: str, details: dict | None = None) -> ProjectError:
    return ProjectError(409, code, message, details)
