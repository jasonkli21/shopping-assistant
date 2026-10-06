from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopping.catalog.models import (
    CatalogObservation,
    Product,
    ProductIdentifier,
    ProductVariant,
)
from shopping.extraction.schemas import CatalogExtraction


@dataclass(frozen=True)
class ResolutionDecision:
    product: Product | None
    variant: ProductVariant | None
    reason: str
    evidence: list[dict]


def resolve_or_create(
    session: Session,
    owner_id: UUID,
    extraction: CatalogExtraction,
    observation: CatalogObservation | None,
    *,
    allow_create: bool = True,
    mutate: bool = True,
) -> ResolutionDecision:
    identifiers = _prepared_identifiers(extraction)
    matched: list[tuple[ProductIdentifier, ProductVariant, Product]] = []
    for scheme, namespace, _value, normalized in identifiers:
        rows = session.execute(
            select(ProductIdentifier, ProductVariant, Product)
            .join(ProductVariant, ProductVariant.id == ProductIdentifier.variant_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(
                ProductIdentifier.product_id == ProductVariant.product_id,
                Product.owner_id == owner_id,
                ProductIdentifier.scheme == scheme,
                ProductIdentifier.namespace == namespace,
                ProductIdentifier.normalized_value == normalized,
            )
        ).all()
        matched.extend(rows)

    matched_products = {row[2].id for row in matched}
    exact_variant_identifiers = [
        row for row in matched if row[0].scheme in {"gtin", "retailer_sku"}
    ]
    exact_variants = {row[1].id for row in exact_variant_identifiers}
    if len(exact_variants) > 1 or len(matched_products) > 1:
        return ResolutionDecision(
            product=None,
            variant=None,
            reason="conflicting_authoritative_identifiers",
            evidence=_match_evidence(matched),
        )

    if exact_variants:
        variant_id = next(iter(exact_variants))
        row = next(row for row in exact_variant_identifiers if row[1].id == variant_id)
        if _has_conflicting_authoritative_identifier(session, row[1], identifiers):
            return ResolutionDecision(
                product=None,
                variant=None,
                reason="authoritative_identifier_conflict",
                evidence=_match_evidence(matched),
            )
        if not _compatible(row[1], extraction.variant_attributes):
            return ResolutionDecision(
                product=None,
                variant=None,
                reason="authoritative_identifier_variant_conflict",
                evidence=_match_evidence(matched),
            )
        decision = ResolutionDecision(
            product=row[2],
            variant=row[1],
            reason="matched_authoritative_identifier",
            evidence=_match_evidence(matched),
        )
        if mutate:
            assert observation is not None
            _attach_identifiers(session, owner_id, extraction, observation, row[2], row[1])
            _refresh_source_attributes(session, row[1], extraction, observation)
        return decision

    family_products = {row[2].id: row[2] for row in matched}
    if not family_products:
        family_products = _find_exact_model_family(session, owner_id, extraction)
    if len(family_products) > 1:
        return ResolutionDecision(
            product=None,
            variant=None,
            reason="ambiguous_model_family",
            evidence=_match_evidence(matched),
        )

    if family_products:
        product = next(iter(family_products.values()))
        variants = list(
            session.scalars(
                select(ProductVariant)
                .where(ProductVariant.product_id == product.id)
                .order_by(ProductVariant.created_at, ProductVariant.id)
            )
        )
        compatible = []
        conflicts = []
        for variant in variants:
            known_identity = _plain_identity(variant.identity_attributes)
            identifier_conflict = _has_conflicting_authoritative_identifier(
                session, variant, identifiers
            )
            if identifier_conflict:
                conflicts.append(variant)
                continue
            if not extraction.variant_attributes:
                if not known_identity:
                    compatible.append(variant)
            elif _same_identity(variant, extraction.variant_attributes):
                compatible.append(variant)
        if len(compatible) == 1:
            variant = compatible[0]
            if mutate:
                assert observation is not None
                _attach_identifiers(session, owner_id, extraction, observation, product, variant)
                _refresh_source_attributes(session, variant, extraction, observation)
            return ResolutionDecision(
                product=product,
                variant=variant,
                reason="matched_brand_model_variant",
                evidence=_match_evidence(matched),
            )
        if len(compatible) > 1:
            return ResolutionDecision(
                product=None,
                variant=None,
                reason="ambiguous_variant_dimensions",
                evidence=_variant_evidence(compatible),
            )
        if conflicts:
            return ResolutionDecision(
                product=None,
                variant=None,
                reason="authoritative_identifier_conflict",
                evidence=_variant_evidence(conflicts),
            )
        if not extraction.variant_attributes:
            return ResolutionDecision(
                product=None,
                variant=None,
                reason="unknown_variant_dimensions",
                evidence=_variant_evidence(variants),
            )
        if not allow_create:
            return ResolutionDecision(
                product=None,
                variant=None,
                reason="no_compatible_known_variant",
                evidence=_variant_evidence(variants),
            )
        variant = _new_source_variant(session, product, extraction, observation)
        if mutate:
            _attach_identifiers(session, owner_id, extraction, observation, product, variant)
        return ResolutionDecision(
            product=product,
            variant=variant,
            reason="created_distinct_variant_for_known_family",
            evidence=_match_evidence(matched),
        )

    if not allow_create:
        return ResolutionDecision(
            product=None,
            variant=None,
            reason="no_identifier_match",
            evidence=_match_evidence(matched),
        )

    product = Product(
        id=uuid4(),
        owner_id=owner_id,
        canonical_name=extraction.product_name,
        brand=extraction.brand,
        brand_key=normalize_text(extraction.brand) if extraction.brand else None,
        category=normalize_text(extraction.category) if extraction.category else None,
        model_family=extraction.model_family,
        revision=1,
    )
    session.add(product)
    session.flush()
    variant = _new_source_variant(session, product, extraction, observation)
    _attach_identifiers(session, owner_id, extraction, observation, product, variant)
    return ResolutionDecision(
        product=product,
        variant=variant,
        reason="created_from_unmatched_observation",
        evidence=[{"kind": "new_product_observation", "observation_id": str(observation.id)}],
    )


def match_existing_variant(
    session: Session, owner_id: UUID, extraction: CatalogExtraction
) -> ResolutionDecision:
    """Resolve only an existing identity and leave catalog identity fields untouched."""
    return resolve_or_create(session, owner_id, extraction, None, allow_create=False, mutate=False)


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def normalize_identifier(scheme: str, value: str) -> str | None:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if scheme == "gtin":
        if any(character not in "0123456789 -" for character in normalized):
            return None
        digits = "".join(character for character in normalized if character.isdigit())
        if len(digits) not in {8, 12, 13, 14}:
            return None
        total = sum(
            int(digit) * (3 if (len(digits) - index) % 2 == 0 else 1)
            for index, digit in enumerate(digits[:-1])
        )
        return digits if (10 - total % 10) % 10 == int(digits[-1]) else None
    return " ".join(normalized.casefold().split())


def _prepared_identifiers(extraction: CatalogExtraction):
    prepared = []
    for item in extraction.identifiers:
        normalized = normalize_identifier(item.scheme, item.value)
        if normalized is None:
            continue
        if item.scheme == "gtin":
            namespace = "global"
        elif item.scheme == "retailer_sku":
            namespace = item.namespace.casefold().removeprefix("www.").rstrip(".")
        else:
            namespace = normalize_text(item.namespace)
        if not namespace or namespace in {
            "unknown",
            "unbranded",
            "brand:unknown",
            "category:unknown",
        }:
            continue
        if item.scheme == "manufacturer_model" and any(
            part
            in {
                "brand:unknown",
                "brand:unbranded",
                "category:unknown",
                "category:unbranded",
            }
            for part in namespace.split("|")
        ):
            continue
        prepared.append((item.scheme, namespace, item.value, normalized))
    return prepared


def _has_conflicting_authoritative_identifier(
    session: Session,
    variant: ProductVariant,
    candidate_identifiers: list[tuple[str, str, str, str]],
) -> bool:
    candidate_exact: dict[tuple[str, str], set[str]] = {}
    for scheme, namespace, _value, normalized in candidate_identifiers:
        if scheme in {"gtin", "retailer_sku"}:
            candidate_exact.setdefault((scheme, namespace), set()).add(normalized)
    if not candidate_exact:
        return False
    if any(len(values) > 1 for values in candidate_exact.values()):
        return True
    existing = session.execute(
        select(
            ProductIdentifier.scheme,
            ProductIdentifier.namespace,
            ProductIdentifier.normalized_value,
        ).where(
            ProductIdentifier.variant_id == variant.id,
            ProductIdentifier.scheme.in_(["gtin", "retailer_sku"]),
        )
    ).all()
    return any(
        (scheme, namespace) in candidate_exact
        and normalized not in candidate_exact[(scheme, namespace)]
        for scheme, namespace, normalized in existing
    )


def _find_exact_model_family(
    session: Session, owner_id: UUID, extraction: CatalogExtraction
) -> dict[UUID, Product]:
    if not extraction.brand or not extraction.model_family:
        return {}
    from sqlalchemy import func

    statement = select(Product).where(
        Product.owner_id == owner_id,
        Product.brand_key == normalize_text(extraction.brand),
        func.lower(Product.model_family) == normalize_text(extraction.model_family),
    )
    if extraction.category:
        statement = statement.where(Product.category == normalize_text(extraction.category))
    else:
        statement = statement.where(Product.category.is_(None))
    return {product.id: product for product in session.scalars(statement)}


def _compatible(variant: ProductVariant, candidate_attributes: dict) -> bool:
    existing = _plain_identity(variant.identity_attributes)
    for key, value in candidate_attributes.items():
        if key not in existing or normalize_text(str(existing[key])) != normalize_text(str(value)):
            return False
    return True


def _same_identity(variant: ProductVariant, candidate_attributes: dict) -> bool:
    existing = _plain_identity(variant.identity_attributes)
    normalized_existing = {key: normalize_text(str(value)) for key, value in existing.items()}
    normalized_candidate = {
        key: normalize_text(str(value)) for key, value in candidate_attributes.items()
    }
    return normalized_existing == normalized_candidate


def _plain_identity(identity_attributes: dict) -> dict:
    return {
        key: value.get("value") if isinstance(value, dict) and "value" in value else value
        for key, value in identity_attributes.items()
    }


def _identity_key(attributes: dict) -> str:
    if not attributes:
        return "unspecified"
    normalized = {key: normalize_text(str(value)) for key, value in sorted(attributes.items())}
    return "identity:" + json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def _identity_records(attributes: dict, excerpts: dict, observation: CatalogObservation) -> dict:
    return {
        key: {
            "value": value,
            "origin": "source",
            "observation_id": str(observation.id),
            "excerpt": excerpts[key],
        }
        for key, value in attributes.items()
    }


def _new_source_variant(
    session: Session,
    product: Product,
    extraction: CatalogExtraction,
    observation: CatalogObservation,
) -> ProductVariant:
    identity_key = _identity_key(extraction.variant_attributes)
    display_name = (
        "; ".join(
            f"{key.replace('_', ' ').title()}: {value}"
            for key, value in sorted(extraction.variant_attributes.items())
        )
        or "Unspecified"
    )
    variant = ProductVariant(
        id=uuid4(),
        product_id=product.id,
        display_name=display_name[:300],
        identity_key=identity_key[:500],
        identity_attributes=_identity_records(
            extraction.variant_attributes, extraction.variant_attribute_excerpts, observation
        ),
        category_attributes=_category_records(extraction, observation),
        revision=1,
    )
    session.add(variant)
    session.flush()
    return variant


def _category_records(extraction: CatalogExtraction, observation: CatalogObservation) -> dict:
    return {
        item.key: {
            "value": item.value,
            "unit": item.unit,
            "origin": item.origin,
            "observation_id": str(observation.id),
            "excerpt": item.excerpt,
        }
        for item in extraction.attributes
    }


def _refresh_source_attributes(
    session: Session,
    variant: ProductVariant,
    extraction: CatalogExtraction,
    observation: CatalogObservation,
) -> None:
    # Source observations are append-only. Refresh fills missing keys but does not
    # overwrite an existing value or a user correction on an established variant.
    identity = dict(variant.identity_attributes)
    for key, value in extraction.variant_attributes.items():
        if key not in identity:
            identity[key] = _identity_records(
                {key: value}, {key: extraction.variant_attribute_excerpts[key]}, observation
            )[key]
    category = dict(variant.category_attributes)
    for key, item in _category_records(extraction, observation).items():
        if key not in category:
            category[key] = item
    if identity != variant.identity_attributes or category != variant.category_attributes:
        next_key = _identity_key(_plain_identity(identity))
        collision = session.scalar(
            select(ProductVariant.id).where(
                ProductVariant.product_id == variant.product_id,
                ProductVariant.id != variant.id,
                ProductVariant.identity_key == next_key,
            )
        )
        if collision is None:
            variant.identity_key = next_key
        variant.identity_attributes = identity
        variant.category_attributes = category
        variant.revision += 1


def _attach_identifiers(
    session: Session,
    owner_id: UUID,
    extraction: CatalogExtraction,
    observation: CatalogObservation,
    product: Product,
    variant: ProductVariant,
) -> None:
    for scheme, namespace, value, normalized in _prepared_identifiers(extraction):
        found = session.scalar(
            select(ProductIdentifier.id).where(
                ProductIdentifier.variant_id == variant.id,
                ProductIdentifier.scheme == scheme,
                ProductIdentifier.namespace == namespace,
                ProductIdentifier.normalized_value == normalized,
            )
        )
        if found is not None:
            continue
        session.add(
            ProductIdentifier(
                id=uuid4(),
                product_id=product.id,
                variant_id=variant.id,
                scheme=scheme,
                namespace=namespace,
                value=value,
                normalized_value=normalized,
                observation_id=observation.id,
            )
        )


def _match_evidence(matched: list[tuple[ProductIdentifier, ProductVariant, Product]]) -> list[dict]:
    return [
        {
            "scheme": identifier.scheme,
            "namespace": identifier.namespace,
            "normalized_value": identifier.normalized_value,
            "variant_id": str(variant.id),
            "product_id": str(product.id),
        }
        for identifier, variant, product in matched
    ]


def _variant_evidence(variants: list[ProductVariant]) -> list[dict]:
    return [
        {
            "variant_id": str(variant.id),
            "identity_attributes": _plain_identity(variant.identity_attributes),
        }
        for variant in variants
    ]
