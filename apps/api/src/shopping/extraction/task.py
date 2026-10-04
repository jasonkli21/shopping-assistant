from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Protocol
from urllib.parse import urlsplit

from pydantic import ValidationError

from shopping.extraction.http_retriever import html_to_text
from shopping.extraction.retriever import RetrievedDocument
from shopping.extraction.schemas import SUPPORTED_CURRENCIES, CatalogExtraction, OfferExtraction


class CatalogExtractionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CatalogExtractionTask(Protocol):
    async def extract(self, document: RetrievedDocument) -> CatalogExtraction: ...


class FakeCatalogExtractionTask:
    """Task-shaped deterministic fixture adapter; it never interprets page instructions."""

    def __init__(self, outputs: dict[str, CatalogExtraction | dict]) -> None:
        self._outputs = {
            url: output
            if isinstance(output, CatalogExtraction)
            else CatalogExtraction.model_validate(output)
            for url, output in outputs.items()
        }

    async def extract(self, document: RetrievedDocument) -> CatalogExtraction:
        try:
            output = self._outputs[document.final_url]
        except KeyError as error:
            raise CatalogExtractionError(
                "no_fixture", "No extraction fixture matches this page."
            ) from error
        validate_extraction_evidence(output, document)
        return output


class StructuredDataCatalogExtractionTask:
    """Conservative local extractor for one JSON-LD Product object."""

    async def extract(self, document: RetrievedDocument) -> CatalogExtraction:
        products = _product_objects(document.body)
        if not products:
            raise CatalogExtractionError(
                "no_product_data", "No structured product identity was found."
            )
        if len(products) != 1:
            raise CatalogExtractionError(
                "ambiguous_products", "The page contains more than one structured product."
            )
        product = products[0]
        name = _string(product.get("name"))
        if not name:
            raise CatalogExtractionError(
                "missing_product_name", "The structured product has no name."
            )
        brand, brand_excerpt = _brand(product.get("brand"))
        category = _string(product.get("category"))
        model = _string(product.get("model"))
        warnings: list[str] = []
        identifiers = []
        if model and brand and category:
            namespace = f"brand:{brand.casefold()}|category:{category.casefold()}"
            identifiers.append(
                {
                    "scheme": "manufacturer_model",
                    "namespace": namespace,
                    "value": model,
                    "excerpt": model,
                }
            )
        for key, scheme in (
            ("gtin", "gtin"),
            ("gtin8", "gtin"),
            ("gtin12", "gtin"),
            ("gtin13", "gtin"),
            ("gtin14", "gtin"),
            ("sku", "retailer_sku"),
        ):
            value = _string(product.get(key))
            if not value:
                continue
            host = urlsplit(document.final_url).hostname or "unknown"
            namespace = host.casefold() if scheme == "retailer_sku" else "global"
            identifiers.append(
                {"scheme": scheme, "namespace": namespace, "value": value, "excerpt": value}
            )
        mpn = _string(product.get("mpn"))
        if mpn and brand:
            identifiers.append(
                {"scheme": "mpn", "namespace": brand.casefold(), "value": mpn, "excerpt": mpn}
            )
        variant_attributes, variant_excerpts = _variant_dimensions(product, warnings)
        offer = _extract_offer(product.get("offers"), document, warnings)
        data = {
            "product_name": name,
            "product_name_excerpt": name,
            "brand": brand,
            "brand_excerpt": brand_excerpt,
            "category": category,
            "category_excerpt": category,
            "model_family": model,
            "model_family_excerpt": model,
            "variant_attributes": variant_attributes,
            "variant_attribute_excerpts": variant_excerpts,
            "identifiers": identifiers,
            "offer": offer,
            "warnings": warnings,
        }
        try:
            result = CatalogExtraction.model_validate(data)
        except ValidationError as error:
            raise CatalogExtractionError(
                "invalid_structured_data", "The structured product data is invalid."
            ) from error
        validate_extraction_evidence(result, document, structured_source=True)
        return result


def validate_extraction_evidence(
    extraction: CatalogExtraction,
    document: RetrievedDocument,
    *,
    structured_source: bool = False,
) -> None:
    excerpts = [extraction.product_name_excerpt]
    excerpts.extend(
        value
        for value in (
            extraction.brand_excerpt,
            extraction.category_excerpt,
            extraction.model_family_excerpt,
        )
        if value
    )
    excerpts.extend(item.excerpt for item in extraction.identifiers)
    excerpts.extend(item.excerpt for item in extraction.attributes)
    excerpts.extend(extraction.variant_attribute_excerpts.values())
    if extraction.offer:
        excerpts.append(extraction.offer.excerpt)
    visible_and_structured = html_to_text(document.body)
    structured_products = _product_objects(document.body)
    if structured_products:
        visible_and_structured += json.dumps(structured_products, ensure_ascii=False)
    page = _normalize_evidence(visible_and_structured)
    if not structured_source and any(
        _normalize_evidence(excerpt) not in page for excerpt in excerpts
    ):
        raise CatalogExtractionError(
            "unsupported_extraction",
            "The extraction included a value without matching page text.",
        )
    supported_values = [
        (extraction.product_name, extraction.product_name_excerpt),
        *[
            (value, excerpt)
            for value, excerpt in (
                (extraction.brand, extraction.brand_excerpt),
                (extraction.category, extraction.category_excerpt),
                (extraction.model_family, extraction.model_family_excerpt),
            )
            if value is not None
        ],
        *[(item.value, item.excerpt) for item in extraction.identifiers],
        *[
            (value, extraction.variant_attribute_excerpts[key])
            for key, value in extraction.variant_attributes.items()
        ],
        *[(item.value, item.excerpt) for item in extraction.attributes],
    ]
    if any(not _excerpt_supports(value, excerpt) for value, excerpt in supported_values):
        raise CatalogExtractionError(
            "unsupported_extraction",
            "An extracted value is not present in its own supporting excerpt.",
        )
    for item in extraction.attributes:
        if item.unit and _normalize_evidence(item.unit) not in _normalize_evidence(item.excerpt):
            raise CatalogExtractionError(
                "unsupported_extraction",
                "An extracted measurement unit is not present in its supporting excerpt.",
            )
    if extraction.offer:
        offer_values = []
        if extraction.offer.amount is not None:
            offer_values.append((extraction.offer.amount, extraction.offer.excerpt))
        if extraction.offer.currency is not None:
            offer_values.append((extraction.offer.currency, extraction.offer.excerpt))
        if any(not _excerpt_supports(value, excerpt) for value, excerpt in offer_values):
            raise CatalogExtractionError(
                "unsupported_extraction",
                "An extracted offer value is not present in its supporting excerpt.",
            )
        if extraction.offer.availability != "unknown":
            availability_tokens = {
                "in_stock": ("instock", "in_stock"),
                "out_of_stock": ("outofstock", "out_of_stock"),
                "preorder": ("preorder", "presale"),
            }[extraction.offer.availability]
            excerpt = _normalize_evidence(extraction.offer.excerpt)
            if not any(token in excerpt for token in availability_tokens):
                raise CatalogExtractionError(
                    "unsupported_extraction",
                    "Offer availability is not present in its supporting excerpt.",
                )
        if extraction.offer.condition != "unknown":
            condition_tokens = {
                "new": ("newcondition", "new"),
                "used": ("usedcondition", "used"),
                "refurbished": ("refurbishedcondition", "refurbished"),
            }[extraction.offer.condition]
            excerpt = _normalize_evidence(extraction.offer.excerpt)
            if not any(token in excerpt for token in condition_tokens):
                raise CatalogExtractionError(
                    "unsupported_extraction",
                    "Offer condition is not present in its supporting excerpt.",
                )
    if extraction.offer and _origin(extraction.offer.url) != _origin(document.final_url):
        raise CatalogExtractionError(
            "unrelated_offer",
            "The extracted offer does not belong to the retrieved retailer page.",
        )


def _product_objects(html: str) -> list[dict]:
    scripts = re.findall(
        r"<script\b[^>]*type\s*=\s*['\"]application/ld\+json['\"][^>]*>(.*?)</script\s*>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    products: list[dict] = []
    total_chars = 0
    for raw in scripts[:20]:
        total_chars += len(raw)
        if len(raw) > 250_000 or total_chars > 750_000:
            continue
        try:
            data = json.loads(
                raw.strip(),
                object_pairs_hook=_unique_object,
                parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
            )
            nodes = list(_walk_json(data))
        except (json.JSONDecodeError, RecursionError, ValueError, _UnsafeStructuredData):
            continue
        for item in nodes:
            types = item.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if any(str(value).casefold() == "product" for value in types):
                products.append(item)
    return products


class _UnsafeStructuredData(ValueError):
    pass


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise _UnsafeStructuredData("duplicate JSON-LD key")
        value[key] = item
    return value


def _walk_json(value):
    stack = [(value, 0)]
    visited = 0
    while stack:
        item, depth = stack.pop()
        visited += 1
        if depth > 32 or visited > 5000:
            raise _UnsafeStructuredData("JSON-LD structure exceeds supported bounds")
        if isinstance(item, dict):
            yield item
            stack.extend(
                (child, depth + 1) for child in item.values() if isinstance(child, (dict, list))
            )
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item if isinstance(child, (dict, list)))


def _variant_dimensions(product: dict, warnings: list[str]) -> tuple[dict, dict]:
    aliases = {
        "bundle": "bundle",
        "package": "bundle",
        "package contents": "bundle",
        "region": "region",
        "market region": "region",
        "regional variant": "region",
        "color": "color",
        "colour": "color",
        "capacity": "capacity",
        "storage capacity": "capacity",
        "generation": "generation",
        "condition": "condition",
        "size": "size",
        "screen size": "size",
    }
    observed: dict[str, set[str]] = {}
    for key in ("bundle", "region", "color", "capacity", "generation", "condition", "size"):
        value = _string(product.get(key))
        if value:
            observed.setdefault(key, set()).add(value)
    additional = product.get("additionalProperty")
    properties = additional if isinstance(additional, list) else [additional]
    for item in properties:
        if not isinstance(item, dict):
            continue
        name = _string(item.get("name")) or _string(item.get("propertyID"))
        value = _string(item.get("value"))
        if not name or not value:
            continue
        key = aliases.get(" ".join(name.casefold().replace("_", " ").split()))
        if key:
            observed.setdefault(key, set()).add(value)
    dimensions = {}
    excerpts = {}
    for key, values in observed.items():
        if len(values) == 1:
            value = next(iter(values))
            dimensions[key] = value
            excerpts[key] = value
        else:
            warnings.append(f"conflicting_{key}_variant_values_unresolved")
    return dimensions, excerpts


def _brand(value) -> tuple[str | None, str | None]:
    if isinstance(value, str) and value.strip():
        return value.strip()[:200], value.strip()[:300]
    if isinstance(value, dict):
        name = _string(value.get("name"))
        if name:
            return name[:200], name[:300]
    return None, None


def _extract_offer(
    value, document: RetrievedDocument, warnings: list[str]
) -> OfferExtraction | None:
    offers = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
    if len(offers) != 1:
        if len(offers) > 1:
            warnings.append("multiple_page_offers_unresolved")
        return None
    raw = offers[0]
    price = _string(raw.get("price")) if isinstance(raw, dict) else None
    currency = _string(raw.get("priceCurrency")) if isinstance(raw, dict) else None
    amount = None
    if price is not None and currency in SUPPORTED_CURRENCIES:
        try:
            amount = Decimal(price)
        except InvalidOperation:
            warnings.append("malformed_price_unknown")
        else:
            if (
                not amount.is_finite()
                or amount < 0
                or amount > Decimal("10000000")
                or amount.as_tuple().exponent < -2
            ):
                amount = None
                warnings.append("unsupported_precision_or_range_price_unknown")
    elif price is not None:
        warnings.append("currency_unavailable_or_unsupported_price_unknown")
    elif currency is not None:
        warnings.append("amount_unavailable_price_unknown")

    availability_url = _string(raw.get("availability")) if isinstance(raw, dict) else None
    availability = _enum_tail(
        availability_url,
        {
            "instock": "in_stock",
            "outofstock": "out_of_stock",
            "preorder": "preorder",
            "presale": "preorder",
        },
        "unknown",
    )
    condition_url = _string(raw.get("itemCondition")) if isinstance(raw, dict) else None
    condition = _enum_tail(
        condition_url,
        {"newcondition": "new", "usedcondition": "used", "refurbishedcondition": "refurbished"},
        "unknown",
    )
    seller = raw.get("seller") if isinstance(raw, dict) else None
    seller_name = _string(seller.get("name")) if isinstance(seller, dict) else _string(seller)
    host = urlsplit(document.final_url).hostname or "Retailer"
    excerpt = None
    if isinstance(raw, dict):
        excerpt_parts = [
            part for part in (price, currency, availability_url, condition_url) if part
        ]
        if seller_name:
            excerpt_parts.append(seller_name)
        excerpt = " ".join(excerpt_parts) or None
    if not excerpt:
        warnings.append("offer_without_supporting_value")
        return None
    return OfferExtraction(
        retailer_name=(seller_name or host)[:200],
        url=document.final_url,
        amount=amount,
        currency=currency if amount is not None else None,
        availability=availability,
        condition=condition,
        excerpt=excerpt[:300],
    )


def _string(value) -> str | None:
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        result = str(value).strip()
        return result or None
    return None


def _enum_tail(value: str | None, options: dict[str, str], fallback: str) -> str:
    if not value:
        return fallback
    tail = value.rstrip("/#").rsplit("/", 1)[-1].rsplit("#", 1)[-1].casefold()
    return options.get(tail, fallback)


def _normalize_evidence(value: str) -> str:
    return "".join(value.casefold().split())


def _excerpt_supports(value, excerpt: str) -> bool:
    if isinstance(value, bool):
        rendered = "true" if value else "false"
    elif isinstance(value, float):
        rendered = format(Decimal(str(value)).normalize(), "f")
    elif isinstance(value, Decimal):
        rendered = format(value.normalize(), "f")
    else:
        rendered = str(value)
    return bool(rendered) and _normalize_evidence(rendered) in _normalize_evidence(excerpt)


def _origin(value: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(value)
    return parsed.scheme.casefold(), (parsed.hostname or "").casefold(), parsed.port
