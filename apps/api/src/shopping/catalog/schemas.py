from __future__ import annotations

import json
import math
import unicodedata
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictCatalogModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NormalizeCandidateCommand(StrictCatalogModel):
    request_key: str = Field(min_length=8, max_length=100)
    expected_catalog_version: int = Field(ge=1)
    expected_project_version: int = Field(ge=1)


class CategoryAttributeCorrection(StrictCatalogModel):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    value: str | int | float | bool
    unit: str | None = Field(default=None, max_length=30)

    @field_validator("value")
    @classmethod
    def finite_value(cls, value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("attribute values must be finite")
        if isinstance(value, str) and len(value) > 200:
            raise ValueError("attribute text is too long")
        if isinstance(value, int) and not isinstance(value, bool) and len(str(abs(value))) > 40:
            raise ValueError("numeric attribute value is too large")
        return value

    @model_validator(mode="after")
    def validate_dimension_unit(self):
        if any(
            token in self.key
            for token in ("height", "width", "depth", "length", "clearance", "screen_size")
        ):
            if self.unit is None or self.unit.casefold() not in {
                "mm",
                "cm",
                "m",
                "in",
                "inch",
                "inches",
                "ft",
            }:
                raise ValueError("dimension attributes require a supported unit")
            if not isinstance(self.value, (int, float)) or isinstance(self.value, bool):
                raise ValueError("dimension attributes must be numeric")
        return self


def _validate_identity_attributes(value: dict[str, str | int | float | bool]):
    allowed = {"bundle", "region", "color", "capacity", "generation", "condition", "size"}
    if set(value) - allowed:
        raise ValueError("unsupported variant identity fields")
    for item in value.values():
        if isinstance(item, str) and (not item.strip() or len(item) > 100):
            raise ValueError("variant identity text must contain 1 to 100 characters")
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("variant identity values must be finite")
        if isinstance(item, (int, float)) and not isinstance(item, bool) and item <= 0:
            raise ValueError("numeric variant identity values must be positive")
    normalized = {
        key: " ".join(unicodedata.normalize("NFKC", str(item)).casefold().split())
        for key, item in value.items()
    }
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 450:
        raise ValueError("variant identity dimensions exceed the supported size")
    return value


def _validate_category_list(value: list[CategoryAttributeCorrection]):
    keys = [item.key for item in value]
    if len(keys) != len(set(keys)):
        raise ValueError("category attribute keys must be unique")
    return value


class NewVariantCorrection(StrictCatalogModel):
    product_id: UUID
    display_name: str = Field(min_length=1, max_length=300)
    identity_attributes: dict[str, str | int | float | bool] = Field(
        default_factory=dict, max_length=12
    )
    category_attributes: list[CategoryAttributeCorrection] = Field(
        default_factory=list, max_length=20
    )

    _identity_attributes_valid = field_validator("identity_attributes")(
        _validate_identity_attributes
    )
    _category_attributes_valid = field_validator("category_attributes")(_validate_category_list)


class NewProductCorrection(StrictCatalogModel):
    canonical_name: str = Field(min_length=1, max_length=300)
    brand: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    model_family: str | None = Field(default=None, max_length=200)
    variant_name: str = Field(default="Unspecified", min_length=1, max_length=300)
    identity_attributes: dict[str, str | int | float | bool] = Field(
        default_factory=dict, max_length=12
    )
    category_attributes: list[CategoryAttributeCorrection] = Field(
        default_factory=list, max_length=20
    )

    _identity_attributes_valid = field_validator("identity_attributes")(
        _validate_identity_attributes
    )
    _category_attributes_valid = field_validator("category_attributes")(_validate_category_list)


class CatalogCorrectionCommand(StrictCatalogModel):
    request_key: str = Field(min_length=8, max_length=100)
    expected_catalog_version: int = Field(ge=1)
    expected_project_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)
    target_variant_id: UUID | None = None
    new_variant: NewVariantCorrection | None = None
    new_product: NewProductCorrection | None = None

    @model_validator(mode="after")
    def exactly_one_target(self):
        targets = [
            self.target_variant_id is not None,
            self.new_variant is not None,
            self.new_product is not None,
        ]
        if sum(targets) != 1:
            raise ValueError("choose exactly one existing or new product variant")
        return self


class CatalogCorrectionRevertCommand(StrictCatalogModel):
    request_key: str = Field(min_length=8, max_length=100)
    expected_catalog_version: int = Field(ge=1)
    expected_project_version: int = Field(ge=1)


class OfferRead(StrictCatalogModel):
    id: UUID
    variant_id: UUID
    observation_id: UUID | None
    research_source_attempt_id: UUID | None = None
    retailer_name: str
    retailer_domain: str | None
    url: str
    amount: str | None
    currency: str | None
    availability: Literal["in_stock", "out_of_stock", "preorder", "unknown"]
    condition: Literal["new", "used", "refurbished", "unknown"]
    observed_at: datetime


class ProductIdentifierRead(StrictCatalogModel):
    id: UUID
    scheme: Literal["manufacturer_model", "gtin", "mpn", "retailer_sku"]
    namespace: str
    value: str
    observation_id: UUID | None


class ProductVariantRead(StrictCatalogModel):
    id: UUID
    product_id: UUID
    display_name: str
    identity_attributes: dict[str, Any]
    category_attributes: dict[str, Any]
    revision: int
    identifiers: list[ProductIdentifierRead]
    offers: list[OfferRead]


class ProductRead(StrictCatalogModel):
    id: UUID
    canonical_name: str
    brand: str | None
    category: str | None
    model_family: str | None
    revision: int
    created_at: datetime
    updated_at: datetime
    variants: list[ProductVariantRead]


class CatalogVariantChoice(StrictCatalogModel):
    variant_id: UUID
    product_id: UUID
    canonical_name: str
    brand: str | None
    category: str | None
    model_family: str | None
    variant_name: str
    identity_attributes: dict[str, Any]


class CatalogVariantChoicePage(StrictCatalogModel):
    items: list[CatalogVariantChoice]
    next_cursor: str | None
    catalog_version: int


class ProjectProductRead(StrictCatalogModel):
    id: UUID
    project_id: UUID
    product_id: UUID
    variant_id: UUID
    canonical_name: str
    brand: str | None
    category: str | None
    model_family: str | None
    variant_name: str
    identity_attributes: dict[str, Any]
    category_attributes: dict[str, Any]
    first_candidate_id: UUID | None
    discovery_reason: str
    created_at: datetime
    offers: list[OfferRead]


class ProjectProductPage(StrictCatalogModel):
    items: list[ProjectProductRead]
    next_cursor: str | None
    catalog_version: int
    project_version: int


class OfferPage(StrictCatalogModel):
    items: list[OfferRead]
    next_cursor: str | None
    catalog_version: int


class FavoriteCommand(StrictCatalogModel):
    expected_version: int = Field(ge=0)


class FavoriteRead(StrictCatalogModel):
    variant_id: UUID
    favorite: bool
    version: int
    updated_at: datetime | None = None


class SavedProductRead(FavoriteRead):
    product_id: UUID
    canonical_name: str
    brand: str | None
    category: str | None
    variant_name: str
    identity_attributes: dict[str, Any]
    offers: list[OfferRead]


class SavedProductPage(StrictCatalogModel):
    items: list[SavedProductRead]
    next_cursor: str | None = None


class CatalogNormalizationRead(StrictCatalogModel):
    candidate_id: UUID
    observation_id: UUID
    event_id: UUID
    status: Literal["auto_linked", "unresolved", "failed", "blocked", "unsupported"]
    project_product_id: UUID | None
    product_id: UUID | None
    variant_id: UUID | None
    catalog_version: int
    project_version: int
    reason: str
    failure_code: str | None = None
    warnings: list[str] = Field(default_factory=list)
    observed_at: datetime
    replayed: bool = False


class CatalogCorrectionRead(StrictCatalogModel):
    candidate_id: UUID
    event_id: UUID
    status: Literal["manual_linked", "reverted"]
    previous_project_product_id: UUID | None
    selected_project_product_id: UUID | None
    catalog_version: int
    project_version: int
    reason: str
    replayed: bool = False


class CandidateNormalizationState(StrictCatalogModel):
    candidate_id: UUID
    project_product_id: UUID | None
    product_id: UUID | None
    variant_id: UUID | None
    status: Literal["auto_linked", "manual_linked", "unresolved", "reverted"] | None
    latest_observation_status: Literal["succeeded", "failed", "blocked", "unsupported"] | None
    latest_failure_code: str | None
    catalog_version: int
    project_version: int
    reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    observed_at: datetime | None = None
    can_revert_correction: bool = False


class CandidateNormalizationSummary(StrictCatalogModel):
    candidate_id: UUID
    canonical_mapping_id: UUID | None
    resolution_status: Literal["auto_linked", "manual_linked", "unresolved", "reverted"] | None
    observation_status: Literal["succeeded", "failed", "blocked", "unsupported"] | None
    failure_code: str | None


def request_hash(command: BaseModel) -> str:
    import hashlib

    encoded = json.dumps(command.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def money_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, ".2f")


def attributes_are_bounded(value: dict[str, Any]) -> bool:
    """Reject ORM or extraction JSONB that could grow into an unbounded metadata blob."""
    if len(value) > 20:
        return False
    try:
        encoded = json.dumps(value, allow_nan=False, ensure_ascii=False)
    except (TypeError, ValueError):
        return False
    return len(encoded.encode("utf-8")) <= 12_000
