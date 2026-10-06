from __future__ import annotations

import json
import math
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ProjectStatus = Literal["active", "completed", "archived"]
RequirementKind = Literal["must_have", "preference", "constraint"]
RequirementOperator = Literal["eq", "gte", "lte", "contains", "one_of"]
SUPPORTED_CURRENCIES = frozenset(
    "USD CAD EUR GBP JPY AUD NZD CHF CNY INR MXN BRL KRW SGD SEK NOK DKK PLN ILS ZAR "
    "TRY THB IDR PHP HKD TWD MYR CZK HUF CLP COP ARS EGP SAR AED UAH RUB BGN RON ISK "
    "PKR VND NGN KES MAD QAR KWD OMR BHD JOD LKR NPR BDT GHS TZS UGX XOF XAF".split()
)
MAX_REQUIREMENTS_PER_PROJECT = 100


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RequirementFields(StrictModel):
    kind: RequirementKind
    label: str = Field(min_length=1, max_length=300)
    detail: str | None = Field(default=None, max_length=2000)
    attribute_key: str | None = Field(default=None, min_length=1, max_length=100)
    operator: RequirementOperator | None = None
    value: Any = None
    unit: str | None = Field(default=None, max_length=50)

    @field_validator("label")
    @classmethod
    def label_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("label must contain non-whitespace text")
        return value

    @field_validator("detail", "unit")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("attribute_key")
    @classmethod
    def normalize_attribute_key(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("value")
    @classmethod
    def value_is_bounded_json(cls, value: Any) -> Any:
        if value is None:
            return value
        _validate_json_value(value, depth=0)
        try:
            serialized = json.dumps(value, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError("value must be valid JSON") from error
        if len(serialized) > 8000:
            raise ValueError("value must be at most 8000 characters when encoded as JSON")
        return value

    @model_validator(mode="after")
    def validate_criterion(self) -> RequirementFields:
        _validate_requirement_criterion(self.attribute_key, self.operator, self.value, self.unit)
        return self


class RequirementCreate(RequirementFields):
    pass


class RequirementPatch(StrictModel):
    expected_version: int = Field(ge=1)
    kind: RequirementKind | None = None
    label: str | None = Field(default=None, min_length=1, max_length=300)
    detail: str | None = Field(default=None, max_length=2000)
    attribute_key: str | None = Field(default=None, min_length=1, max_length=100)
    operator: RequirementOperator | None = None
    value: Any = None
    unit: str | None = Field(default=None, max_length=50)
    position: int | None = Field(default=None, ge=0)

    @field_validator("label")
    @classmethod
    def label_must_not_be_blank(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("label must contain non-whitespace text")
        return value

    @field_validator("detail", "unit")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("attribute_key")
    @classmethod
    def normalize_attribute_key(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("value")
    @classmethod
    def value_is_bounded_json(cls, value: Any) -> Any:
        if value is not None:
            _validate_json_value(value, depth=0)
            try:
                serialized = json.dumps(value, ensure_ascii=False, allow_nan=False)
            except (TypeError, ValueError) as error:
                raise ValueError("value must be valid JSON") from error
            if len(serialized) > 8000:
                raise ValueError("value must be at most 8000 characters when encoded as JSON")
        return value

    @model_validator(mode="after")
    def require_mutation(self) -> RequirementPatch:
        mutable_fields = self.model_fields_set - {"expected_version"}
        if not mutable_fields:
            raise ValueError("at least one requirement field must be supplied")
        return self


class ProjectCreate(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=4000)
    category: str | None = Field(default=None, max_length=100)
    budget_target: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    budget_maximum: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    budget_currency: str | None = Field(default=None, min_length=3, max_length=3)
    notes: str | None = Field(default=None, max_length=10000)
    requirements: list[RequirementCreate] = Field(default_factory=list, max_length=100)

    @field_validator("title", "goal")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("field must contain non-whitespace text")
        return value

    @field_validator("category", "notes")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return value or None

    @field_validator(
        "budget_target",
        "budget_maximum",
        mode="before",
        json_schema_input_type=str | None,
    )
    @classmethod
    def money_must_be_a_decimal_string(cls, value: Any) -> Any:
        return _validate_money_string(value)

    @field_validator("budget_currency")
    @classmethod
    def currency_must_be_supported(cls, value: str | None) -> str | None:
        return _validate_currency(value)

    @model_validator(mode="after")
    def validate_budget_and_requirement_count(self) -> ProjectCreate:
        validate_budget(self.budget_target, self.budget_maximum, self.budget_currency)
        return self


class ProjectPatch(StrictModel):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    goal: str | None = Field(default=None, min_length=1, max_length=4000)
    category: str | None = Field(default=None, max_length=100)
    status: ProjectStatus | None = None
    budget_target: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    budget_maximum: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    budget_currency: str | None = Field(default=None, min_length=3, max_length=3)
    notes: str | None = Field(default=None, max_length=10000)
    reuse_preferences: bool | None = None

    @field_validator("title", "goal")
    @classmethod
    def non_nullable_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("field must contain non-whitespace text")
        return value

    @field_validator("category", "notes")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return value or None

    @field_validator(
        "budget_target",
        "budget_maximum",
        mode="before",
        json_schema_input_type=str | None,
    )
    @classmethod
    def money_must_be_a_decimal_string(cls, value: Any) -> Any:
        return _validate_money_string(value)

    @field_validator("budget_currency")
    @classmethod
    def currency_must_be_supported(cls, value: str | None) -> str | None:
        return _validate_currency(value)

    @model_validator(mode="after")
    def require_mutation(self) -> ProjectPatch:
        if not (self.model_fields_set - {"expected_version"}):
            raise ValueError("at least one project field must be supplied")
        return self


class RequirementRead(StrictModel):
    id: UUID
    project_id: UUID
    kind: RequirementKind
    label: str
    detail: str | None
    attribute_key: str | None
    operator: RequirementOperator | None
    value: Any
    unit: str | None
    position: int
    origin: Literal["user", "ai_confirmed"]
    source_preference_id: UUID | None = None
    source_preference_revision: int | None = None
    source_preference_scope: list[str] | None = None
    created_at: datetime
    updated_at: datetime


class ProjectSummary(StrictModel):
    id: UUID
    title: str
    goal: str
    category: str | None
    status: ProjectStatus
    budget_target: str | None
    budget_maximum: str | None
    budget_currency: str | None
    notes: str | None
    reuse_preferences: bool
    revision: int
    created_at: datetime
    updated_at: datetime


class ProjectRead(ProjectSummary):
    requirements: list[RequirementRead]


class ProjectPage(StrictModel):
    items: list[ProjectSummary]
    next_cursor: str | None


class ApiError(StrictModel):
    code: str
    message: str
    details: Any = None
    request_id: str | None = None


class ApiErrorEnvelope(StrictModel):
    error: ApiError


def validate_budget(
    target: Decimal | None,
    maximum: Decimal | None,
    currency: str | None,
) -> None:
    if (target is not None or maximum is not None) != (currency is not None):
        raise ValueError("currency is required exactly when a budget amount is set")
    if target is not None and maximum is not None and target > maximum:
        raise ValueError("budget_target cannot exceed budget_maximum")


def validate_criterion_fields(
    attribute_key: str | None,
    operator: RequirementOperator | str | None,
    value: Any,
    unit: str | None,
) -> None:
    _validate_requirement_criterion(attribute_key, operator, value, unit)


def _validate_currency(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.upper()
    if normalized not in SUPPORTED_CURRENCIES:
        raise ValueError("currency must be a supported ISO 4217 code")
    return normalized


def _validate_money_string(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("money must be supplied as a decimal string")
    if not value or any(character not in "0123456789." for character in value):
        raise ValueError("money must be a nonnegative decimal string")
    if value.count(".") > 1:
        raise ValueError("money must be a nonnegative decimal string")
    integer, separator, fractional = value.partition(".")
    if not integer or len(fractional) > 2 or (separator and not fractional):
        raise ValueError("money must have at most two fractional digits")
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("money must be a valid decimal string") from error
    if not amount.is_finite() or amount < 0:
        raise ValueError("money must be a finite nonnegative decimal string")
    return value


def _validate_requirement_criterion(
    attribute_key: str | None,
    operator: RequirementOperator | str | None,
    value: Any,
    unit: str | None,
) -> None:
    typed = (attribute_key is not None, operator is not None, value is not None)
    if not any(typed):
        if unit is not None:
            raise ValueError("unit requires a structured criterion")
        return
    if not all(typed):
        raise ValueError("attribute_key, operator, and value must be supplied together")
    if operator in {"gte", "lte"}:
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise ValueError(f"{operator} requires a numeric value")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("numeric values must be finite")
    elif operator == "contains" and not isinstance(value, str):
        raise ValueError("contains requires a string value")
    elif operator == "one_of":
        if not isinstance(value, list) or not 1 <= len(value) <= 20:
            raise ValueError("one_of requires a list with 1 to 20 values")
        if any(isinstance(item, (dict, list)) or item is None for item in value):
            raise ValueError("one_of values must be non-null JSON scalars")


def _validate_json_value(value: Any, depth: int) -> None:
    if depth > 5:
        raise ValueError("value must be no more than five levels deep")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        if len(value) > 2000:
            raise ValueError("JSON string values must be at most 2000 characters")
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return
    if isinstance(value, list):
        if len(value) > 100:
            raise ValueError("JSON arrays may contain at most 100 items")
        for item in value:
            _validate_json_value(item, depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 100:
            raise ValueError("JSON objects may contain at most 100 fields")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 100:
                raise ValueError("JSON object keys must be strings of at most 100 characters")
            _validate_json_value(item, depth + 1)
        return
    raise ValueError("value must contain only JSON data")


def money_string(value: Decimal | None) -> str | None:
    return None if value is None else format(value, ".2f")
