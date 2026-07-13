"""Découverte, récupération et analyse canonique des actualités."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag
from pydantic import HttpUrl

from vigie_pipeline.config import ProjectConfig, SourceConfig
from vigie_pipeline.exceptions import ExtractionError, PipelineError
from vigie_pipeline.fetch import BoundedFetcher, FetchResult
from vigie_pipeline.hashing import sha256_bytes, sha256_text
from vigie_pipeline.llm.anthropic_provider import PROMPT_VERSION, AnthropicProvider
from vigie_pipeline.llm.base import LlmProvider
from vigie_pipeline.models import (
    DiscoveredDocument,
    LlmTrace,
    NewsItem,
    NewsSource,
    ObservationQuality,
    Period,
    VigieDataset,
)
from vigie_pipeline.settings import Settings

TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "janvier": 1,
    "février": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
}


@dataclass(frozen=True)
class ArticleContent:
    canonical_url: str
    title: str
    published_at: date
    original_summary: str | None
    text: str
    fingerprint: str
    fetched_at: datetime


@dataclass(frozen=True)
class NewsFailure:
    source_id: str
    document_url: str
    message: str


@dataclass(frozen=True)
class NewsAcquisition:
    items: list[NewsItem]
    documents: list[DiscoveredDocument]
    failures: list[NewsFailure]
    anthropic_calls: int


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url)
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
        ]
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def discover_news_documents(source: SourceConfig, index: FetchResult) -> list[DiscoveredDocument]:
    if index.content_type not in {"text/html", "application/xhtml+xml"}:
        raise ExtractionError(f"Index d’actualités non HTML: {source.id}")
    soup = BeautifulSoup(index.content, "html.parser")
    index_url = canonicalize_url(index.url)
    seen: set[str] = set()
    result: list[DiscoveredDocument] = []
    for anchor in soup.select(source.link_selector):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href", "")).strip()
        if not href:
            continue
        url = canonicalize_url(urljoin(index.url, href))
        if url == index_url or url in seen:
            continue
        searchable = f"{url} {anchor.get_text(' ', strip=True)}".lower()
        if source.include_patterns and not any(
            pattern.lower() in searchable for pattern in source.include_patterns
        ):
            continue
        title = anchor.get_text(" ", strip=True) or url.rsplit("/", 1)[-1]
        result.append(
            DiscoveredDocument(
                source_id=source.id,
                canonical_url=HttpUrl(url),
                title=title,
                published_at=_date_from_anchor(anchor),
                content_type="text/html",
            )
        )
        seen.add(url)
        if len(result) >= source.max_articles:
            break
    return result


def extract_article(
    result: FetchResult, discovered: DiscoveredDocument, source: SourceConfig
) -> ArticleContent:
    if result.content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
        raise ExtractionError(f"Article non textuel: {result.url}")
    soup = BeautifulSoup(result.content, "html.parser")
    for node in soup.select("script, style, noscript, nav, footer"):
        node.decompose()
    canonical = soup.select_one('link[rel="canonical"][href]')
    canonical_url = canonicalize_url(
        urljoin(result.url, str(canonical.get("href"))) if canonical else result.url
    )
    title_node = soup.select_one('meta[property="og:title"][content]')
    heading = soup.select_one("h1")
    title = (
        str(title_node.get("content", "")).strip()
        if title_node
        else heading.get_text(" ", strip=True)
        if heading
        else discovered.title
    )
    date_value = discovered.published_at or _date_from_document(soup)
    if date_value is None:
        raise ExtractionError(f"Date de publication introuvable: {canonical_url}")
    description = soup.select_one(
        'meta[name="description"][content], meta[property="og:description"][content]'
    )
    original_summary = str(description.get("content", "")).strip() or None if description else None
    article = soup.select_one(source.article_selector) or soup.body
    if article is None:
        raise ExtractionError(f"Corps d’article introuvable: {canonical_url}")
    text = article.get_text(" ", strip=True)
    if len(text) < 80:
        raise ExtractionError(f"Corps d’article trop court: {canonical_url}")
    return ArticleContent(
        canonical_url=canonical_url,
        title=title,
        published_at=date_value,
        original_summary=original_summary or text[:500],
        text=text,
        fingerprint=sha256_bytes(result.content),
        fetched_at=datetime.now(UTC),
    )


def acquire_news(
    dataset: VigieDataset,
    source: SourceConfig,
    settings: Settings,
    config: ProjectConfig,
    llm_provider: LlmProvider | None = None,
) -> NewsAcquisition:
    existing_by_url = {canonicalize_url(str(item.source.url)): item for item in dataset.news}
    results: list[NewsItem] = []
    failures: list[NewsFailure] = []
    anthropic_calls = 0
    with BoundedFetcher(
        timeout=source.timeout_seconds,
        attempts=source.attempts,
        max_bytes=config.pipeline.http.max_download_bytes,
    ) as fetcher:
        index = fetcher.fetch(str(source.url))
        documents = discover_news_documents(source, index)
        for discovered in documents:
            try:
                article = extract_article(
                    fetcher.fetch(str(discovered.canonical_url)), discovered, source
                )
            except PipelineError as error:
                failures.append(
                    NewsFailure(
                        source_id=source.id,
                        document_url=str(discovered.canonical_url),
                        message=str(error),
                    )
                )
                continue
            existing = existing_by_url.get(article.canonical_url)
            if existing is not None and existing.source.document_hash == article.fingerprint:
                continue
            analysis = None
            llm_warning: str | None = None
            if llm_provider is not None or settings.anthropic_api_key:
                try:
                    provider = llm_provider or AnthropicProvider(settings, config.pipeline.llm)
                    anthropic_calls += 1
                    analysis = provider.summarize_news(
                        title=article.title,
                        content=article.text,
                        source_url=article.canonical_url,
                    )
                except PipelineError as error:
                    llm_warning = f"Analyse Anthropic indisponible: {error}"
            else:
                llm_warning = "Analyse Anthropic non exécutée: clé absente."
            company_ids = [source.company_id]
            trace = None
            if analysis is not None:
                company_ids = [
                    company_id
                    for company_id in dict.fromkeys([source.company_id, *analysis.company_ids])
                    if company_id in config.companies
                ]
                trace = LlmTrace(
                    provider="anthropic",
                    model=config.pipeline.llm.standard_model,
                    prompt_version=PROMPT_VERSION,
                    executed_at=datetime.now(UTC),
                    task_id=(
                        f"summarize_news_{source.id}_{sha256_text(article.canonical_url)[7:19]}"
                    ),
                    source_fingerprint=article.fingerprint,
                    confidence=analysis.confidence,
                    warnings=analysis.warnings,
                )
            item_period = period_for_date(article.published_at)
            results.append(
                NewsItem(
                    id=f"news-{sha256_text(article.canonical_url)[7:27]}",
                    company_ids=company_ids,
                    period_id=item_period.period_id,
                    period_key=item_period.period_key,
                    published_at=article.published_at,
                    source=NewsSource(
                        type=(
                            "official_release"
                            if source.content_category == "official_news"
                            else "secondary"
                        ),
                        name=config.companies[source.company_id].name,
                        url=HttpUrl(article.canonical_url),
                        source_id=source.id,
                        fetched_at=article.fetched_at,
                        document_hash=article.fingerprint,
                    ),
                    title=article.title,
                    original_summary=article.original_summary,
                    generated_summary=analysis.summary if analysis else None,
                    categories=list(analysis.categories) if analysis else ["other"],
                    importance=analysis.importance if analysis else "medium",
                    themes=analysis.themes if analysis else [],
                    quality=ObservationQuality(
                        status="validated" if analysis else "warning",
                        extraction_method=("anthropic" if analysis else "deterministic_fallback"),
                        confidence=analysis.confidence if analysis else 0.5,
                        warnings=analysis.warnings if analysis else [llm_warning or ""],
                        llm_trace=trace,
                    ),
                )
            )
            existing_by_url[article.canonical_url] = results[-1]
    return NewsAcquisition(
        items=results,
        documents=documents,
        failures=failures,
        anthropic_calls=anthropic_calls,
    )


def period_for_date(value: date) -> Period:
    key: Literal["T1", "T2", "T3", "AN"]
    if value.month <= 3:
        key, quarter, end = "T1", 1, date(value.year, 3, 31)
    elif value.month <= 6:
        key, quarter, end = "T2", 2, date(value.year, 6, 30)
    elif value.month <= 9:
        key, quarter, end = "T3", 3, date(value.year, 9, 30)
    else:
        key, quarter, end = "AN", None, date(value.year, 12, 31)
    return Period(
        period_id=f"{value.year}-{key}",
        period_key=key,
        type="annual" if key == "AN" else "quarter",
        year=value.year,
        quarter=quarter,
        end_date=end,
        label=f"Annuel {value.year}" if key == "AN" else f"{key} {value.year}",
    )


def _date_from_anchor(anchor: Tag) -> date | None:
    for parent in [anchor, *list(anchor.parents)[:3]]:
        if isinstance(parent, Tag):
            parsed = _parse_date(parent.get_text(" ", strip=True))
            if parsed:
                return parsed
    return None


def _date_from_document(soup: BeautifulSoup) -> date | None:
    selectors = (
        'meta[property="article:published_time"][content]',
        'meta[name="date"][content]',
        "time[datetime]",
    )
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            parsed = _parse_date(str(node.get("content") or node.get("datetime") or ""))
            if parsed:
                return parsed
    return _parse_date(soup.get_text(" ", strip=True)[:1000])


def _parse_date(text: str) -> date | None:
    iso = re.search(r"(20\d{2})[-/](0?[1-9]|1[0-2])[-/]([0-2]?\d|3[01])", text)
    if iso:
        try:
            return date(int(iso[1]), int(iso[2]), int(iso[3]))
        except ValueError:
            return None
    month_names = "|".join(MONTHS)
    named = re.search(
        rf"\b({month_names})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b",
        text.lower(),
    )
    if named:
        return date(int(named[3]), MONTHS[named[1]], int(named[2]))
    french = re.search(
        rf"\b(\d{{1,2}})\s+({month_names})\s+(20\d{{2}})\b",
        text.lower(),
    )
    if french:
        return date(int(french[3]), MONTHS[french[2]], int(french[1]))
    return None
