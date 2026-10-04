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
    host = (urlsplit(url).hostname or "").casefold().removeprefix("www.")
    title_text = (title or "").casefold()
    sample = f"{title_text} {text[:8000].casefold()}"
    if any(
        marker in sample
        for marker in ("affiliate link", "we may earn a commission", "sponsored review")
    ):
        return SourceClassification(
            "editorial_assessment", "affiliate or sponsorship disclosure detected"
        )
    if any(marker in host for marker in ("reddit.com", "forums.", "forum.", "community.")):
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
        marker in host
        for marker in (
            "wirecutter.com",
            "rtings.com",
            "consumerreports.org",
            "techradar.com",
            "which.co.uk",
        )
    ):
        if any(
            marker in sample for marker in ("tested", "measured", "test results", "runtime test")
        ):
            return SourceClassification(
                "independent_measurement", "review publisher with measurement language"
            )
        return SourceClassification("editorial_assessment", "recognized editorial review publisher")
    if any(
        marker in host
        for marker in (
            "amazon.",
            "bestbuy.",
            "walmart.",
            "target.",
            "costco.",
            "homedepot.",
            "lowes.",
            "ebay.",
        )
    ):
        return SourceClassification("retailer_listing", "retailer host marker detected")
    brand_tokens = (
        [token for token in re.findall(r"[a-z0-9]+", brand.casefold()) if len(token) >= 3]
        if brand
        else []
    )
    if (
        brand_tokens and any(token in host.split(".") for token in brand_tokens)
    ) or "official" in host:
        if any(marker in host + sample for marker in ("specification", "specs", "technical data")):
            return SourceClassification(
                "manufacturer_specification", "brand host and specification marker detected"
            )
        return SourceClassification("manufacturer_claim", "brand or official host marker detected")
    return SourceClassification(
        "unknown", "publisher type could not be established from page metadata"
    )
