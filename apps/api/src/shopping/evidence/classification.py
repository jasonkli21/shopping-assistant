from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit


@dataclass(frozen=True)
class SourceMetadata:
    title: str | None
    published_at: datetime | None


@dataclass(frozen=True)
class SourceClassification:
    classification: str
    basis: str


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def _has_measurement_content(value: str) -> bool:
    for sentence in re.split(r"[.!?\n]+", value):
        has_measurement_verb = re.search(r"\b(measured|tested|recorded)\b", sentence)
        has_numeric_measurement = re.search(
            r"\b\d+(?:\.\d+)?\s*(?:minutes?|mins?|hours?|hrs?|db|decibels?|watts?|w|kg|g)\b",
            sentence,
        )
        if has_measurement_verb and has_numeric_measurement:
            return True
    return False


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title_text: list[str] = []
        self.values: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.casefold(): value for key, value in attrs}
        if tag.casefold() == "title":
            self.in_title = True
        if tag.casefold() == "meta":
            key = (attributes.get("property") or attributes.get("name") or "").casefold()
            value = attributes.get("content")
            if (
                key
                and value
                and key
                in {
                    "article:published_time",
                    "datepublished",
                    "date",
                    "og:title",
                }
            ):
                self.values.setdefault(key, value.strip())
        if (attributes.get("itemprop") or "").casefold() == "datepublished":
            value = attributes.get("content") or attributes.get("datetime")
            if value:
                self.values.setdefault("datepublished", value.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title and data.strip():
            self.title_text.append(data.strip())


def page_metadata(html: str) -> SourceMetadata:
    parser = _MetadataParser()
    try:
        parser.feed(html[:1_000_000])
    except Exception:
        return SourceMetadata(title=None, published_at=None)
    title = (
        " ".join(parser.title_text).strip()[:300] or parser.values.get("og:title", "")[:300] or None
    )
    published = None
    for key in ("article:published_time", "datepublished", "date"):
        raw = parser.values.get(key)
        if not raw:
            continue
        try:
            published = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                published = parsedate_to_datetime(raw)
            except (TypeError, ValueError, OverflowError):
                continue
        if published.tzinfo is None or published.utcoffset() is None:
            published = published.replace(tzinfo=UTC)
        published = published.astimezone(UTC)
        break
    return SourceMetadata(title=title, published_at=published)


def classify_source(
    url: str,
    *,
    title: str | None = None,
    text: str = "",
    brand: str | None = None,
) -> SourceClassification:
    host = (urlsplit(url).hostname or "").casefold().rstrip(".").removeprefix("www.")
    title_text = (title or "").casefold()
    sample = f"{title_text} {text[:8000].casefold()}"
    if any(
        marker in sample
        for marker in ("affiliate link", "we may earn a commission", "sponsored review")
    ):
        return SourceClassification(
            "editorial_assessment", "affiliate or sponsorship disclosure detected"
        )
    if _host_matches(host, "reddit.com") or host.startswith(("forums.", "forum.", "community.")):
        category = (
            "individual_anecdote"
            if any(
                marker in sample
                for marker in ("my unit", "my vacuum", "in my experience", "i bought")
            )
            else "community_observation"
        )
        return SourceClassification(category, "community or forum host marker detected")
    if any(
        _host_matches(host, marker)
        for marker in (
            "wirecutter.com",
            "rtings.com",
            "consumerreports.org",
            "techradar.com",
            "which.co.uk",
        )
    ):
        if _has_measurement_content(text[:8000].casefold()):
            return SourceClassification(
                "independent_measurement", "recognized review publisher with quoted measured result"
            )
        return SourceClassification("editorial_assessment", "recognized editorial review publisher")
    if any(
        _host_matches(host, marker)
        for marker in (
            "amazon.com",
            "bestbuy.com",
            "walmart.com",
            "target.com",
            "costco.com",
            "homedepot.com",
            "lowes.com",
            "ebay.com",
        )
    ):
        return SourceClassification("retailer_listing", "retailer host marker detected")
    brand_tokens = (
        [token for token in re.findall(r"[a-z0-9]+", brand.casefold()) if len(token) >= 3]
        if brand
        else []
    )
    host_labels = host.split(".")
    registered_label = host_labels[-2] if len(host_labels) >= 2 else ""
    brand_in_content = bool(
        brand
        and re.search(
            rf"(?<![a-z0-9]){re.escape(brand.casefold())}(?![a-z0-9])", text[:8000].casefold()
        )
    )
    if brand_tokens and registered_label in brand_tokens and brand_in_content:
        if any(
            marker in text[:8000].casefold()
            for marker in ("specification", "specs", "technical data")
        ):
            return SourceClassification(
                "manufacturer_specification",
                "brand-named page contains specification content and matches the brand domain",
            )
        return SourceClassification(
            "manufacturer_claim",
            "brand-named product content appears on a matching brand domain",
        )
    return SourceClassification(
        "unknown", "publisher type could not be established from page metadata"
    )


def classify_claim(category: str, quote: str, context: str) -> str:
    """Do not promote a quotation to the publisher's strongest evidence class."""
    sample = f"{context} {quote}".casefold()
    if any(marker in sample for marker in ("in my experience", "my unit", "i bought")):
        return "individual_anecdote"
    if any(marker in sample for marker in ("users report", "owners report", "forum users")):
        return "community_observation"
    if any(
        marker in sample
        for marker in (
            "according to the manufacturer",
            "manufacturer claims",
            "advertised",
            "rated at",
        )
    ):
        return "manufacturer_claim"
    if category == "unknown":
        return "unknown"
    if re.search(r"\bup\s+to\b", quote, re.I) and not _has_measurement_content(sample):
        return "manufacturer_claim"
    if category == "independent_measurement" and not _has_measurement_content(sample):
        return "editorial_assessment"
    if category == "independent_measurement":
        return "independent_measurement"
    return category
