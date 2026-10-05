from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from shopping.projects.schemas import StrictModel

DimensionType = Literal["fact", "offer", "evidence", "project_fit", "user_note"]
DisplayMode = Literal["all", "differences"]
CellStatus = Literal["known", "unknown", "conflict", "stale", "incomparable"]


class ComparisonDimensionInput(StrictModel):
    key: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.:-]+$")
    label: str = Field(min_length=1, max_length=100)
    unit: str | None = Field(default=None, max_length=30)
    dimension_type: DimensionType


class ComparisonCreate(StrictModel):
    expected_version: int = Field(ge=1)
    title: str = Field(default="Product comparison", min_length=1, max_length=160)
    project_product_ids: list[UUID] = Field(min_length=2, max_length=6)
    dimensions: list[ComparisonDimensionInput] = Field(min_length=1, max_length=20)
    display_mode: DisplayMode = "all"

    @model_validator(mode="after")
    def unique_members_and_dimensions(self):
        if len(self.project_product_ids) != len(set(self.project_product_ids)):
            raise ValueError("comparison products must be unique")
        keys = [item.key for item in self.dimensions]
        if len(keys) != len(set(keys)):
            raise ValueError("comparison dimension keys must be unique")
        return self

    @field_validator("title", mode="after")
    @classmethod
    def nonblank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must contain non-whitespace characters")
        return value.strip()


class ComparisonPatch(StrictModel):
    expected_version: int = Field(ge=1)
    expected_comparison_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=160)
    project_product_ids: list[UUID] | None = Field(default=None, min_length=2, max_length=6)
    dimensions: list[ComparisonDimensionInput] | None = Field(
        default=None, min_length=1, max_length=20
    )
    display_mode: DisplayMode | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        if not (self.model_fields_set - {"expected_version", "expected_comparison_version"}):
            raise ValueError("at least one comparison field must be supplied")
        if self.project_product_ids and len(self.project_product_ids) != len(
            set(self.project_product_ids)
        ):
            raise ValueError("comparison products must be unique")
        if self.dimensions:
            keys = [item.key for item in self.dimensions]
            if len(keys) != len(set(keys)):
                raise ValueError("comparison dimension keys must be unique")
        return self


class ComparisonRegenerate(StrictModel):
    expected_version: int = Field(ge=1)
    expected_comparison_version: int = Field(ge=1)


class ComparisonCell(StrictModel):
    project_product_id: UUID
    status: CellStatus
    value: Any = None
    unit: str | None = None
    comparison_value: Any = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class ComparisonDimensionRead(StrictModel):
    key: str
    label: str
    unit: str | None
    dimension_type: DimensionType
    cells: list[ComparisonCell]
    equal: bool = False


class ComparisonProductRead(StrictModel):
    project_product_id: UUID
    product_id: UUID
    variant_id: UUID
    canonical_name: str
    brand: str | None
    category: str | None
    variant_name: str
    identity_attributes: dict[str, Any]
    product_revision: int
    variant_revision: int


class ComparisonRead(StrictModel):
    id: UUID
    project_id: UUID
    title: str
    display_mode: DisplayMode
    comparison_revision: int
    project_revision: int
    snapshot_id: UUID
    generated_at: datetime
    stale: bool
    products: list[ComparisonProductRead]
    dimensions: list[ComparisonDimensionRead]
    hidden_equal_dimensions: int = 0


class ComparisonPage(StrictModel):
    items: list[ComparisonRead]
    next_cursor: str | None = None
