from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shopping.projects.schemas import (
    SUPPORTED_CURRENCIES,
    _validate_money_string,
    validate_criterion_fields,
)

PreferenceStatus = Literal["active", "revoked"]
CandidateStatus = Literal["pending", "accepted", "dismissed", "stale"]
RequirementOperator = Literal["eq", "gte", "lte", "contains", "one_of"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _validate_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        result = value
    elif isinstance(value, list) and len(value) <= 100:
        result = [_validate_value(item) for item in value]
    elif isinstance(value, dict) and len(value) <= 100:
        result = {str(key): _validate_value(item) for key, item in value.items()}
    else:
        raise ValueError("value must be bounded JSON")
    try:
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("value must be valid JSON") from error
    if len(encoded) > 4000:
        raise ValueError("value must be at most 4000 characters")
    return result


def _normalize_scopes(scopes: list[str]) -> list[str]:
    if not scopes or len(scopes) > 20:
        raise ValueError("choose between 1 and 20 category scopes")
    normalized = list(dict.fromkeys(item.strip().casefold() for item in scopes if item.strip()))
    if not normalized or any(len(item) > 100 for item in normalized):
        raise ValueError("category scopes must contain short non-empty names")
    if "*" in normalized and len(normalized) > 1:
        raise ValueError("the all-categories scope cannot be combined with named categories")
    return normalized


def preference_applies_to_category(scopes: list[str], category: str | None) -> bool:
    normalized = category.casefold() if category else None
    return normalized is not None and ("*" in scopes or normalized in scopes)


def preference_is_suggestible(
    status: str,
    scopes: list[str],
    category: str | None,
    *,
    profile_reuse_enabled: bool,
    project_reuse_enabled: bool,
    already_applied: bool = False,
) -> bool:
    return (
        status == "active"
        and profile_reuse_enabled
        and project_reuse_enabled
        and not already_applied
        and preference_applies_to_category(scopes, category)
    )


def promotable_requirement_kind(kind: str) -> bool:
    return kind == "preference"


class ProfilePatch(StrictModel):
    expected_version: int = Field(ge=1)
    reuse_enabled: bool


class CandidateCreate(StrictModel):
    expected_project_version: int = Field(ge=1)
    expected_profile_version: int = Field(ge=1)
    source_requirement_id: UUID | None = None
    source_project_product_id: UUID | None = None
    label: str = Field(min_length=1, max_length=300)
    key: str = Field(min_length=1, max_length=100)
    operator: RequirementOperator | None = None
    value: Any
    unit: str = Field(default="", max_length=50)
    monetary: bool = False
    category_scopes: list[str] = Field(min_length=1, max_length=20)
    rationale: str = Field(default="", max_length=500)

    @field_validator("label", "key")
    @classmethod
    def required_text_not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("field must contain non-whitespace text")
        return value

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.casefold()

    @field_validator("value")
    @classmethod
    def bounded_json(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("a preference value is required")
        return _validate_value(value)

    @field_validator("category_scopes")
    @classmethod
    def valid_scopes(cls, value: list[str]) -> list[str]:
        return _normalize_scopes(value)

    @model_validator(mode="after")
    def validate_money_scope(self) -> CandidateCreate:
        if (self.source_requirement_id is None) == (self.source_project_product_id is None):
            raise ValueError("choose exactly one project requirement or rejected product judgment")
        self.unit = _validate_money_preference(
            self.monetary, self.key, self.value, self.unit, self.category_scopes
        )
        _validate_preference_criterion(self.key, self.operator, self.value, self.unit)
        return self


class CandidateAction(StrictModel):
    expected_profile_version: int = Field(ge=1)


class PreferenceCandidateRead(StrictModel):
    id: UUID
    source_kind: Literal["requirement", "decision"]
    source_project_id: UUID | None
    source_requirement_id: UUID | None
    source_project_product_id: UUID | None
    source_decision_id: UUID | None
    source_project_revision: int
    source_project_title: str | None
    source_available: bool
    source_stale: bool
    label: str
    key: str
    operator: RequirementOperator | None
    value: Any
    unit: str
    monetary: bool
    category_scopes: list[str]
    rationale: str
    status: CandidateStatus
    created_at: datetime
    resolved_at: datetime | None


class PreferencePatch(StrictModel):
    expected_profile_version: int = Field(ge=1)
    expected_preference_revision: int = Field(ge=1)
    label: str | None = Field(default=None, min_length=1, max_length=300)
    key: str | None = Field(default=None, min_length=1, max_length=100)
    operator: RequirementOperator | None = None
    value: Any = None
    unit: str | None = Field(default=None, max_length=50)
    monetary: bool | None = None
    category_scopes: list[str] | None = Field(default=None, min_length=1, max_length=20)
    status: PreferenceStatus | None = None

    @field_validator("label", "key")
    @classmethod
    def required_text_not_blank(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("field must contain non-whitespace text")
        return value

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str | None) -> str | None:
        return None if value is None else value.casefold()

    @field_validator("value")
    @classmethod
    def bounded_json(cls, value: Any) -> Any:
        return None if value is None else _validate_value(value)

    @field_validator("category_scopes")
    @classmethod
    def valid_scopes(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _normalize_scopes(value)

    @model_validator(mode="after")
    def require_mutation(self) -> PreferencePatch:
        non_nullable = {"label", "key", "value", "unit", "category_scopes", "status", "monetary"}
        if any(getattr(self, name) is None for name in self.model_fields_set & non_nullable):
            raise ValueError("preference fields cannot be null")
        if not (
            self.model_fields_set - {"expected_profile_version", "expected_preference_revision"}
        ):
            raise ValueError("at least one preference field must be supplied")
        return self


def _validate_money_preference(
    monetary: bool, key: str, value: Any, unit: str, category_scopes: list[str]
) -> str:
    if not monetary:
        if unit.upper() in SUPPORTED_CURRENCIES:
            raise ValueError("mark currency-denominated preferences as monetary")
        return unit
    if "*" in category_scopes:
        raise ValueError("money preferences must stay category-specific")
    currency = unit.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError("money preferences must retain a supported ISO currency in Unit")
    if key.casefold() != "statement":
        try:
            _validate_money_string(value)
        except ValueError as error:
            raise ValueError(
                "structured money preferences require a decimal-string value"
            ) from error
    return currency


def _validate_preference_criterion(
    key: str, operator: str | None, value: Any = None, unit: str | None = None
) -> None:
    if key.casefold() == "statement" and operator is not None:
        raise ValueError("statement preferences cannot have a structured operator")
    if key.casefold() == "statement" and (not isinstance(value, str) or len(value) > 2000):
        raise ValueError("statement preferences require text of at most 2000 characters")
    if key.casefold() != "statement" and operator is None:
        raise ValueError("structured preferences require an operator")
    if key.casefold() != "statement":
        validate_criterion_fields(key, operator, value, unit)


class PreferenceRead(StrictModel):
    id: UUID
    source_kind: Literal["requirement", "decision"]
    source_candidate_id: UUID | None
    source_project_id: UUID | None
    source_requirement_id: UUID | None
    source_project_product_id: UUID | None
    source_decision_id: UUID | None
    source_project_title: str | None
    source_available: bool
    key: str
    operator: RequirementOperator | None
    value: Any
    unit: str
    monetary: bool
    category_scopes: list[str]
    label: str
    strength: Literal["soft"]
    status: PreferenceStatus
    revision: int
    accepted_at: datetime
    updated_at: datetime


class ProfileRead(StrictModel):
    id: UUID
    revision: int
    reuse_enabled: bool
    preferences: list[PreferenceRead]
    candidates: list[PreferenceCandidateRead]
    updated_at: datetime


class CandidateMutation(StrictModel):
    candidate: PreferenceCandidateRead
    preference: PreferenceRead | None = None
    replayed: bool = False


class PreferenceSuggestionsRead(StrictModel):
    reuse_enabled: bool
    profile_reuse_enabled: bool
    profile_revision: int
    items: list[PreferenceRead]
