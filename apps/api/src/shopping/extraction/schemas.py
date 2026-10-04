from __future__ import annotations

import math
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SUPPORTED_CURRENCIES = {
    "AED",
    "AUD",
    "BRL",
    "CAD",
    "CHF",
    "CNY",
    "CZK",
    "DKK",
    "EUR",
    "GBP",
    "HKD",
    "HUF",
    "IDR",
    "ILS",
    "INR",
    "ISK",
    "JPY",
    "KRW",
    "MXN",
    "MYR",
    "NOK",
    "NZD",
    "PHP",
    "PLN",
    "RON",
    "SAR",
    "SEK",
    "SGD",
    "THB",
    "TRY",
    "TWD",
    "USD",
    "ZAR",
}

_LENGTH_BOUNDS = {
    "mm": (Decimal("1"), Decimal("5000")),
    "cm": (Decimal("0.1"), Decimal("500")),
    "m": (Decimal("0.001"), Decimal("5")),
    "in": (Decimal("0.04"), Decimal("200")),
    "inch": (Decimal("0.04"), Decimal("200")),
    "inches": (Decimal("0.04"), Decimal("200")),
    "ft": (Decimal("0.003"), Decimal("20")),
}


class StrictExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class IdentifierExtraction(StrictExtractionModel):
    scheme: Literal["manufacturer_model", "gtin", "mpn", "retailer_sku"]
    value: str = Field(min_length=1, max_length=200)
    namespace: str = Field(min_length=1, max_length=300)
    excerpt: str = Field(min_length=1, max_length=300)


class AttributeExtraction(StrictExtractionModel):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    value: str | int | float | bool
    unit: str | None = Field(default=None, max_length=30)
    origin: Literal["manufacturer", "retailer", "structured_data"]
    excerpt: str = Field(min_length=1, max_length=300)

    @field_validator("value")
    @classmethod
    def finite_numeric_value(cls, value):
        if isinstance(value, float) and (value != value or abs(value) == float("inf")):
            raise ValueError("numeric attribute values must be finite")
        return value

    @model_validator(mode="after")
    def validate_measurement_unit(self):
        if any(
            token in self.key
            for token in ("height", "width", "depth", "length", "clearance", "screen_size")
        ):
            if self.unit is None:
                return self
            unit = self.unit.casefold()
            if unit not in _LENGTH_BOUNDS:
                raise ValueError("dimension attribute uses an unsupported unit")
            if not isinstance(self.value, (int, float)) or isinstance(self.value, bool):
                raise ValueError("dimension attributes must be numeric")
            minimum, maximum = _LENGTH_BOUNDS[unit]
            if self.value < float(minimum) or self.value > float(maximum):
                raise ValueError("dimension value is outside plausible physical bounds")
        return self


class OfferExtraction(StrictExtractionModel):
    retailer_name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2048)
    amount: Decimal | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    availability: Literal["in_stock", "out_of_stock", "preorder", "unknown"] = "unknown"
    condition: Literal["new", "used", "refurbished", "unknown"] = "unknown"
    excerpt: str = Field(min_length=1, max_length=300)

    @field_validator("amount")
    @classmethod
    def bounded_amount(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and (
            not value.is_finite() or value < 0 or value > Decimal("10000000")
        ):
            raise ValueError("offer amount is outside supported bounds")
        if value is not None and value.as_tuple().exponent < -2:
            raise ValueError("offer amount cannot be represented exactly to cents")
        return value

    @field_validator("currency")
    @classmethod
    def supported_currency(cls, value: str | None) -> str | None:
        if value is not None and value not in SUPPORTED_CURRENCIES:
            raise ValueError("offer currency is not supported")
        return value

    @model_validator(mode="after")
    def require_amount_currency_pair(self):
        if (self.amount is None) != (self.currency is None):
            raise ValueError("offer amount and currency must both be known or both be unknown")
        return self


class CatalogExtraction(StrictExtractionModel):
    task_version: Literal["normalize_catalog_candidate.v1"] = "normalize_catalog_candidate.v1"
    product_name: str = Field(min_length=1, max_length=300)
    product_name_excerpt: str = Field(min_length=1, max_length=300)
    brand: str | None = Field(default=None, max_length=200)
    brand_excerpt: str | None = Field(default=None, max_length=300)
    category: str | None = Field(default=None, max_length=100)
    category_excerpt: str | None = Field(default=None, max_length=300)
    model_family: str | None = Field(default=None, max_length=200)
    model_family_excerpt: str | None = Field(default=None, max_length=300)
    variant_attributes: dict[str, str | int | float | bool] = Field(
        default_factory=dict, max_length=12
    )
    identifiers: list[IdentifierExtraction] = Field(default_factory=list, max_length=8)
    attributes: list[AttributeExtraction] = Field(default_factory=list, max_length=20)
    offer: OfferExtraction | None = None
    warnings: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("variant_attributes")
    @classmethod
    def variant_keys_are_bounded(cls, value):
        allowed = {"bundle", "region", "color", "capacity", "generation", "condition", "size"}
        invalid = set(value) - allowed
        if invalid:
            raise ValueError("unsupported variant identity fields")
        if any(len(str(item)) > 100 for item in value.values()):
            raise ValueError("variant identity value is too long")
        if any(isinstance(item, float) and not math.isfinite(item) for item in value.values()):
            raise ValueError("numeric variant identity values must be finite")
        for key in ("capacity", "size"):
            if key in value and isinstance(value[key], (int, float)) and value[key] <= 0:
                raise ValueError(f"{key} must be positive")
        return value

    @model_validator(mode="after")
    def identity_fields_have_source_excerpts(self):
        for value, excerpt, field in (
            (self.brand, self.brand_excerpt, "brand"),
            (self.category, self.category_excerpt, "category"),
            (self.model_family, self.model_family_excerpt, "model_family"),
        ):
            if value and not excerpt:
                raise ValueError(f"{field} requires a supporting source excerpt")
        return self
