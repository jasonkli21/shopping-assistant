from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Protocol
from urllib.parse import urlsplit

from pydantic import ValidationError

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
        identifiers = []
        if model:
            namespace = (
                f"brand:{(brand or 'unknown').casefold()}|"
                f"category:{(category or 'unknown').casefold()}"
            )
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
            ("mpn", "mpn"),
            ("sku", "retailer_sku"),
        ):
            value = _string(product.get(key))
            if not value:
                continue
            host = urlsplit(document.final_url).hostname or "unknown"
            namespace = (
                host.casefold()
                if scheme == "retailer_sku"
                else ("global" if scheme == "gtin" else (brand or "unknown").casefold())
            )
            identifiers.append(
                {"scheme": scheme, "namespace": namespace, "value": value, "excerpt": value}
            )
        warnings: list[str] = []
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
        validate_extraction_evidence(result, document)
        return result


def validate_extraction_evidence(
    extraction: CatalogExtraction, document: RetrievedDocument
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
    if extraction.offer:
        excerpts.append(extraction.offer.excerpt)
    page = _normalize_evidence(document.body)
    if any(_normalize_evidence(excerpt) not in page for excerpt in excerpts):
        raise CatalogExtractionError(
            "unsupported_extraction",
            "The extraction included a value without matching page text.",
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
    for raw in scripts[:20]:
        try:
            data = json.loads(raw.strip())
        except (json.JSONDecodeError, RecursionError):
            continue
        for item in _walk_json(data):
            types = item.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if any(str(value).casefold() == "product" for value in types):
                products.append(item)
    return products


def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


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
    excerpt = (
        price or availability_url or _string(raw.get("priceCurrency"))
        if isinstance(raw, dict)
        else None
    )
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


def _origin(value: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(value)
    return parsed.scheme.casefold(), (parsed.hostname or "").casefold(), parsed.port
