"""Découverte de communiqués et PDF à partir des index configurés."""

from __future__ import annotations

from datetime import date
from typing import Literal
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pydantic import HttpUrl

from vigie_pipeline.fetch import FetchResult
from vigie_pipeline.hashing import sha256_bytes
from vigie_pipeline.models import DiscoveredDocument

DOCUMENT_KEYWORDS = (
    "result",
    "résultat",
    "quarter",
    "trimestre",
    "annual",
    "annuel",
    "financial",
    "rapport",
    "conference",
    "webcast",
    "earnings call",
)

FUTURE_EVENT_MARKERS = (
    "conference call",
    "earnings call",
    "webcast",
    "will release",
    "will announce",
    "to announce",
    "date of",
    "scheduled",
    "conférence téléphonique",
    "publiera ses résultats",
)
RESULT_MARKERS = ("results", "résultats", "earnings", "financial result")
REPORT_MARKERS = ("report", "rapport", ".pdf")


def discover_documents(source_id: str, index: FetchResult) -> list[DiscoveredDocument]:
    if index.content_type not in {"text/html", "application/xhtml+xml"}:
        return [
            DiscoveredDocument(
                source_id=source_id,
                canonical_url=HttpUrl(index.url),
                title=index.url.rsplit("/", 1)[-1],
                etag=index.etag,
                last_modified=index.last_modified,
                content_hash=sha256_bytes(index.content),
                content_type=index.content_type,
                document_kind=(
                    "downloadable_report"
                    if index.content_type == "application/pdf"
                    else "published_result"
                ),
            )
        ]
    soup = BeautifulSoup(index.content, "html.parser")
    result: list[DiscoveredDocument] = []
    seen: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href", "")).strip()
        title = anchor.get_text(" ", strip=True) or href.rsplit("/", 1)[-1]
        combined = f"{href} {title}".lower()
        if not href or not (
            href.lower().endswith(".pdf") or any(k in combined for k in DOCUMENT_KEYWORDS)
        ):
            continue
        url = urljoin(index.url, href).split("#", 1)[0]
        if url in seen:
            continue
        seen.add(url)
        context = anchor.parent.get_text(" ", strip=True) if anchor.parent else title
        published_at = _extract_date(context)
        kind, is_published = _classify_document(combined)
        result.append(
            DiscoveredDocument(
                source_id=source_id,
                canonical_url=HttpUrl(url),
                title=title,
                published_at=published_at,
                content_type="application/pdf" if href.lower().endswith(".pdf") else "text/html",
                document_kind=kind,
                is_published=is_published,
            )
        )
    return result


def _classify_document(
    text: str,
) -> tuple[
    Literal["published_result", "downloadable_report", "future_event", "unknown"],
    bool,
]:
    lowered = text.lower()
    if any(marker in lowered for marker in FUTURE_EVENT_MARKERS):
        return "future_event", False
    if any(marker in lowered for marker in RESULT_MARKERS):
        return "published_result", True
    if any(marker in lowered for marker in REPORT_MARKERS):
        return "downloadable_report", True
    return "unknown", True


def _extract_date(text: str) -> date | None:
    import re

    match = re.search(r"(20\d{2})[-_/](0[1-9]|1[0-2])[-_/]([0-2]\d|3[01])", text)
    if match is None:
        return None
    try:
        return date.fromisoformat("-".join(match.groups()))
    except ValueError:
        return None
