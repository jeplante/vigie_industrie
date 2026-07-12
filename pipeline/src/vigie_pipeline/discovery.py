"""Découverte de communiqués et PDF à partir des index configurés."""

from __future__ import annotations

from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

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
)


def discover_documents(source_id: str, index: FetchResult) -> list[DiscoveredDocument]:
    if index.content_type not in {"text/html", "application/xhtml+xml"}:
        return [
            DiscoveredDocument(
                source_id=source_id,
                canonical_url=index.url,
                title=index.url.rsplit("/", 1)[-1],
                etag=index.etag,
                last_modified=index.last_modified,
                content_hash=sha256_bytes(index.content),
                content_type=index.content_type,
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
        result.append(
            DiscoveredDocument(
                source_id=source_id,
                canonical_url=url,
                title=title,
                published_at=_extract_date(combined),
                content_type="application/pdf" if href.lower().endswith(".pdf") else "text/html",
            )
        )
    return result


def _extract_date(text: str) -> date | None:
    import re

    match = re.search(r"(20\d{2})[-_/](0[1-9]|1[0-2])[-_/]([0-2]\d|3[01])", text)
    if match is None:
        return None
    try:
        return date.fromisoformat("-".join(match.groups()))
    except ValueError:
        return None
