"""Acquisition conservatrice des nouveaux documents financiers officiels."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from io import BytesIO
from typing import Literal, cast

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, HttpUrl
from pypdf import PdfReader

from vigie_pipeline.config import MetricConfig, ProjectConfig, SourceConfig
from vigie_pipeline.discovery import discover_documents
from vigie_pipeline.exceptions import ExtractionError, PipelineError
from vigie_pipeline.fetch import BoundedFetcher, FetchResult
from vigie_pipeline.hashing import sha256_bytes
from vigie_pipeline.llm.anthropic_provider import PROMPT_VERSION, AnthropicProvider
from vigie_pipeline.llm.base import LlmProvider
from vigie_pipeline.models import (
    Comparison,
    DiscoveredDocument,
    LlmTrace,
    Observation,
    ObservationQuality,
    Period,
    SourceReference,
    VigieDataset,
)
from vigie_pipeline.normalize import calculate_change, direction_for
from vigie_pipeline.settings import Settings
from vigie_pipeline.sources.base import MetricCandidate, SourceAdapter
from vigie_pipeline.sources.great_west import GreatWestAdapter
from vigie_pipeline.sources.ia import IaAdapter
from vigie_pipeline.sources.manulife import ManulifeAdapter
from vigie_pipeline.sources.sunlife import SunLifeAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {
    "manulife": ManulifeAdapter,
    "sunlife": SunLifeAdapter,
    "great_west": GreatWestAdapter,
    "ia": IaAdapter,
}


class LlmMetric(BaseModel):
    metric_id: str
    value: float
    display_value: str
    unit: str
    context: str
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)


class LlmMetricExtraction(BaseModel):
    metrics: list[LlmMetric]


@dataclass(frozen=True)
class FinancialAcquisition:
    observations: list[Observation]
    discovered_periods: list[Period]
    documents: list[DiscoveredDocument]
    failures: list[DocumentFailure]
    anthropic_calls: int
    checked_at: datetime


@dataclass(frozen=True)
class DocumentFailure:
    source_id: str
    period: Period
    document_url: str
    message: str
    is_newer: bool


def infer_period(title: str) -> Period | None:
    text = title.lower()
    explicit_quarter = re.search(r"(?:q|t)([1-4])[-_/ ]*(20\d{2})", text)
    if explicit_quarter is None:
        reverse_quarter = re.search(r"(20\d{2})[-_/ ]*(?:q|t)([1-4])", text)
        if reverse_quarter:
            explicit_quarter = reverse_quarter
            quarter_number = int(reverse_quarter[2])
            year = int(reverse_quarter[1])
        else:
            quarter_number = 0
            year = 0
    else:
        quarter_number = int(explicit_quarter[1])
        year = int(explicit_quarter[2])
    if quarter_number:
        key = "AN" if quarter_number == 4 else f"T{quarter_number}"
        quarter = None if quarter_number == 4 else quarter_number
        end = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[quarter_number]
        return Period(
            period_id=f"{year}-{key}",
            period_key=cast(Literal["T1", "T2", "T3", "AN"], key),
            type="annual" if key == "AN" else "quarter",
            year=year,
            quarter=quarter,
            end_date=date(year, *end),
            label=f"Annuel {year}" if key == "AN" else f"{key} {year}",
        )
    quarter_patterns: dict[
        Literal["T1", "T2", "T3", "AN"], tuple[int, tuple[str, ...], tuple[int, int]]
    ] = {
        "T1": (1, ("first quarter", "1st quarter", "premier trimestre"), (3, 31)),
        "T2": (2, ("second quarter", "2nd quarter", "deuxième trimestre"), (6, 30)),
        "T3": (3, ("third quarter", "3rd quarter", "troisième trimestre"), (9, 30)),
        "AN": (4, ("fourth quarter", "4th quarter", "quatrième trimestre"), (12, 31)),
    }
    for key, (quarter, markers, end) in quarter_patterns.items():
        marker_position = next((text.find(marker) for marker in markers if marker in text), -1)
        if marker_position >= 0:
            nearby = text[max(0, marker_position - 40) : marker_position + 100]
            year_match = re.search(r"20\d{2}", nearby)
            if year_match is None:
                continue
            year = int(year_match.group())
            return Period(
                period_id=f"{year}-{key}",
                period_key=key,
                type="annual" if key == "AN" else "quarter",
                year=year,
                quarter=None if key == "AN" else quarter,
                end_date=date(year, *end),
                label=f"Annuel {year}" if key == "AN" else f"{key} {year}",
            )
    annual_match = re.search(
        r"annual[-_ ]?report[^0-9]{0,15}(20\d{2})",
        text,
    ) or re.search(
        r"(?:annuel|full year|exercice|annual)[^0-9]{0,30}(20\d{2})",
        text,
    )
    if annual_match:
        year = int(annual_match[1])
        return Period(
            period_id=f"{year}-AN",
            period_key="AN",
            type="annual",
            year=year,
            quarter=None,
            end_date=date(year, 12, 31),
            label=f"Annuel {year}",
        )
    return None


def _relevant_financial_document(document: DiscoveredDocument) -> bool:
    text = f"{document.title} {document.canonical_url}".lower()
    excluded = (
        "certification",
        "dividend",
        "prospectus",
        "transcript",
        ".mp3",
        ".xlsx",
        "conference-call",
        "annual-meeting",
        "circular",
        "notice-of",
    )
    if any(marker in text for marker in excluded):
        return False
    included = (
        "result",
        "résultat",
        "news-release",
        "earnings-release",
        "shareholders-report",
        "report-to-shareholders",
        "quarterly-report",
        "annual-report",
        "annualreport",
        "financial-statements",
        "-mda",
        "fact-sheet",
        "sip-pdf",
    )
    return any(marker in text for marker in included)


def _relevant_future_event(document: DiscoveredDocument) -> bool:
    url = str(document.canonical_url).lower()
    return document.content_type == "text/html" and not any(
        marker in url for marker in (".pdf", ".mp3", ".xlsx", "transcript")
    )


def document_text(result: FetchResult) -> str:
    if result.content_type == "application/pdf":
        try:
            return "\n".join(
                page.extract_text() or "" for page in PdfReader(BytesIO(result.content)).pages
            )
        except Exception as error:
            raise ExtractionError(f"PDF illisible: {result.url}") from error
    return result.content.decode("utf-8", errors="replace")


def publication_date(result: FetchResult) -> date | None:
    """Extrait uniquement une date de publication explicite du document."""

    # Les rapports PDF placent souvent la date officielle au début du MD&A,
    # après une couverture et une table des matières assez longues.
    text = document_text(result)[:50_000]
    if result.content_type in {"text/html", "application/xhtml+xml"}:
        soup = BeautifulSoup(result.content, "html.parser")
        selectors = (
            'meta[property="article:published_time"][content]',
            'meta[name="date"][content]',
            'meta[name="publication_date"][content]',
            "time[datetime]",
        )
        for selector in selectors:
            node = soup.select_one(selector)
            if node is not None:
                text = f"{node.get('content') or node.get('datetime') or ''} {text}"
    months = {
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
    names = "|".join(months)
    explicitly_dated = re.search(
        rf"\b(?:dated|dat[ée])\s*:?\s*({names})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b",
        text.lower(),
    )
    if explicitly_dated:
        return date(
            int(explicitly_dated[3]),
            months[explicitly_dated[1]],
            int(explicitly_dated[2]),
        )
    explicit_release = re.search(
        rf"(?:released|reported|announced|publi[ée]s?).{{0,180}}?"
        rf"\b({names})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b",
        text.lower(),
    )
    if explicit_release:
        return date(
            int(explicit_release[3]),
            months[explicit_release[1]],
            int(explicit_release[2]),
        )
    iso = re.search(r"(20\d{2})-(0[1-9]|1[0-2])-([0-2]\d|3[01])", text)
    if iso:
        try:
            return date.fromisoformat("-".join(iso.groups()))
        except ValueError:
            pass
    named = re.search(rf"\b({names})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b", text.lower())
    if named:
        return date(int(named[3]), months[named[1]], int(named[2]))
    french = re.search(rf"\b(\d{{1,2}})\s+({names})\s+(20\d{{2}})\b", text.lower())
    if french:
        return date(int(french[3]), months[french[2]], int(french[1]))
    return None


def _index_period(index: FetchResult, text: str) -> Period | None:
    if index.content_type not in {"text/html", "application/xhtml+xml"}:
        return infer_period(text[:2_000])
    soup = BeautifulSoup(index.content, "html.parser")
    heading = " ".join(
        node.get_text(" ", strip=True)
        for node in (soup.select_one("title"), soup.select_one("h1"))
        if node is not None
    )
    return infer_period(heading)


def _previous(
    dataset: VigieDataset, company_id: str, period: Period, metric_id: str
) -> Observation | None:
    matches = [
        item
        for item in dataset.observations
        if item.company_id == company_id
        and item.period.period_key == period.period_key
        and item.period.year == period.year - 1
        and item.metric_id == metric_id
    ]
    return max(matches, key=lambda item: item.period.year, default=None)


def _llm_trace(
    *,
    candidate: MetricCandidate | LlmMetric,
    config: ProjectConfig,
    source: SourceConfig,
    period: Period,
    fingerprint: str,
) -> LlmTrace | None:
    if not isinstance(candidate, LlmMetric):
        return None
    return LlmTrace(
        provider="anthropic",
        model=config.pipeline.llm.complex_model,
        prompt_version=PROMPT_VERSION,
        executed_at=datetime.now(UTC),
        task_id=(f"financial_extraction_{source.company_id}_{period.label}_{candidate.metric_id}"),
        source_fingerprint=fingerprint,
        confidence=candidate.confidence,
        warnings=candidate.warnings,
    )


def _build_observation(
    *,
    dataset: VigieDataset,
    source: SourceConfig,
    period: Period,
    document: FetchResult,
    title: str,
    candidate: MetricCandidate | LlmMetric,
    metric: MetricConfig,
    config: ProjectConfig,
    published_at: date | None = None,
    publication_date_fallback: bool = False,
) -> Observation:
    previous = _previous(dataset, source.company_id, period, candidate.metric_id)
    change = calculate_change(candidate.value, previous.value) if previous else None
    direction = cast(
        Literal["up", "down", "neutral"],
        direction_for(candidate.value, previous.value) if previous else "neutral",
    )
    is_llm = isinstance(candidate, LlmMetric)
    if isinstance(candidate, LlmMetric):
        display_value = candidate.display_value
        warnings = list(candidate.warnings)
        confidence = candidate.confidence
        if candidate.unit != metric.unit:
            warnings.append(
                f"Unité LLM {candidate.unit} normalisée vers l’unité configurée {metric.unit}."
            )
    else:
        display_value = candidate.raw_value
        warnings = []
        confidence = 1.0
    if published_at is None:
        published_at = period.end_date
        publication_date_fallback = True
    if publication_date_fallback:
        warnings.append("Date réelle de publication introuvable; date de fin de période utilisée.")
    display_change = "—" if change is None else f"{change:+.1%}".replace(".", ",")
    fingerprint = sha256_bytes(document.content)
    return Observation(
        id=f"{source.company_id}-{period.period_id}-{candidate.metric_id}",
        company_id=source.company_id,
        period=period,
        metric_id=candidate.metric_id,
        label=metric.label,
        value=candidate.value,
        unit=metric.unit,
        display_value=display_value,
        comparison=Comparison(
            period_id=previous.period.period_id if previous else None,
            value=previous.value if previous else None,
            display_value=previous.display_value if previous else "—",
            period_label=previous.period.label if previous else "",
            change=change,
            change_unit="PERCENT" if change is not None else "NONE",
            display_change=display_change,
        ),
        direction=direction,
        note=candidate.context[:500],
        source=SourceReference(
            source_id=source.id,
            url=HttpUrl(document.url),
            title=title,
            published_at=published_at,
            fetched_at=datetime.now(UTC),
            document_hash=fingerprint,
            priority="primary",
        ),
        quality=ObservationQuality(
            status="validated",
            extraction_method="anthropic" if is_llm else "deterministic",
            confidence=confidence,
            warnings=warnings,
            llm_trace=_llm_trace(
                candidate=candidate,
                config=config,
                source=source,
                period=period,
                fingerprint=fingerprint,
            ),
        ),
    )


def acquire_source(
    dataset: VigieDataset,
    source: SourceConfig,
    settings: Settings,
    config: ProjectConfig,
    llm_provider: LlmProvider | None = None,
) -> FinancialAcquisition:
    adapter_type = ADAPTERS.get(source.adapter)
    if adapter_type is None:
        raise ExtractionError(f"Adaptateur inconnu: {source.adapter}")
    with BoundedFetcher(
        timeout=source.timeout_seconds,
        attempts=source.attempts,
        max_bytes=config.pipeline.http.max_download_bytes,
    ) as fetcher:
        index = fetcher.fetch(str(source.url))
        documents = [
            item
            for item in discover_documents(source.id, index)
            if (item.document_kind == "future_event" and _relevant_future_event(item))
            or _relevant_financial_document(item)
        ]
        checked_at = datetime.now(UTC)
        adapter = adapter_type()
        index_text = document_text(index)
        index_candidates = list(adapter.extract_metrics(index_text))
        index_period = _index_period(index, index_text)
        if source.document_url_template and index_period is not None:
            quarter = index_period.quarter or 4
            document_url = source.document_url_template.format(
                year=index_period.year,
                quarter=quarter,
                period_key=index_period.period_key.lower(),
            )
            documents.insert(
                0,
                DiscoveredDocument(
                    source_id=source.id,
                    canonical_url=HttpUrl(document_url),
                    title=f"{source.id} {index_period.label} quarterly report",
                    content_type="application/pdf",
                    document_kind="downloadable_report",
                    is_published=True,
                ),
            )
        if index_candidates and index_period is not None:
            documents.insert(
                0,
                DiscoveredDocument(
                    source_id=source.id,
                    canonical_url=HttpUrl(index.url),
                    title=f"{source.id} index {index_period.label}",
                    published_at=publication_date(index),
                    content_hash=sha256_bytes(index.content),
                    content_type=index.content_type,
                    document_kind="index_metrics",
                    is_published=True,
                ),
            )
        period_documents = [
            (document, period)
            for document in documents
            if document.is_published
            and (period := infer_period(f"{document.title} {document.canonical_url}")) is not None
        ]
        latest_published = max(
            (item.period for item in dataset.observations if item.company_id == source.company_id),
            key=lambda item: item.end_date,
            default=None,
        )
        latest_discovered = max(
            (period for _, period in period_documents),
            key=lambda item: item.end_date,
            default=None,
        )
        known_urls = {
            str(item.source.url).rstrip("/").lower()
            for item in dataset.observations
            if item.company_id == source.company_id
        }
        period_documents.sort(
            key=lambda item: (
                item[1].end_date > latest_published.end_date if latest_published else True,
                str(item[0].canonical_url).rstrip("/").lower() not in known_urls,
                item[1].end_date,
            ),
            reverse=True,
        )
        results: list[Observation] = []
        failures: list[DocumentFailure] = []
        anthropic_calls = 0
        successful_periods: set[str] = set()
        attempted_per_period: dict[str, int] = {}
        reported_documents = [
            item
            for item in documents
            if not item.is_published
            and ((future_period := infer_period(f"{item.title} {item.canonical_url}")) is not None)
            and (latest_published is None or future_period.end_date >= latest_published.end_date)
        ][:10]
        for discovered, period in period_documents:
            canonical_url = str(discovered.canonical_url).rstrip("/").lower()
            unknown_document = canonical_url not in known_urls
            is_newer = latest_published is None or period.end_date > latest_published.end_date
            is_latest = (
                latest_discovered is not None and period.period_id == latest_discovered.period_id
            )
            unknown_current = (
                unknown_document
                and latest_published is not None
                and period.end_date >= latest_published.end_date
            )
            if not (is_newer or is_latest or unknown_current):
                continue
            if period.period_id in successful_periods:
                continue
            attempts_for_period = attempted_per_period.get(period.period_id, 0)
            if attempts_for_period >= 3:
                continue
            attempted_per_period[period.period_id] = attempts_for_period + 1
            reported_documents.append(discovered)
            existing = [
                item
                for item in dataset.observations
                if item.company_id == source.company_id
                and item.period.period_id == period.period_id
            ]
            try:
                document = (
                    index
                    if discovered.document_kind == "index_metrics"
                    else fetcher.fetch(str(discovered.canonical_url))
                )
                fingerprint = sha256_bytes(document.content)
                if existing and all(item.source.document_hash == fingerprint for item in existing):
                    continue
                content = document_text(document)
                candidates: list[MetricCandidate | LlmMetric] = list(
                    index_candidates
                    if discovered.document_kind == "index_metrics"
                    else adapter.extract_metrics(content)
                )
                found = {item.metric_id for item in candidates}
                missing = set(source.expected_metrics) - found
                if missing and settings.anthropic_api_key:
                    provider = llm_provider or AnthropicProvider(settings, config.pipeline.llm)
                    anthropic_calls += 1
                    extraction = provider.extract_structured(
                        content=content,
                        output_model=LlmMetricExtraction,
                        task_name=f"financial_extraction_{source.company_id}_{period.label}",
                        complex_task=True,
                    )
                    candidates.extend(
                        item for item in extraction.metrics if item.metric_id in missing
                    )
                    found = {item.metric_id for item in candidates}
                missing = set(source.expected_metrics) - found
                if missing:
                    raise ExtractionError(
                        f"{source.id}/{period.label}: métriques officielles "
                        f"manquantes {sorted(missing)}"
                    )
                by_metric = {item.metric_id: item for item in candidates}
                real_publication_date = discovered.published_at or publication_date(document)
                used_fallback_date = real_publication_date is None
                effective_publication_date = real_publication_date or period.end_date
                results.extend(
                    _build_observation(
                        dataset=dataset,
                        source=source,
                        period=period,
                        document=document,
                        title=discovered.title,
                        candidate=by_metric[metric_id],
                        metric=config.metrics[metric_id],
                        config=config,
                        published_at=effective_publication_date,
                        publication_date_fallback=used_fallback_date,
                    )
                    for metric_id in source.expected_metrics
                )
                successful_periods.add(period.period_id)
            except PipelineError as error:
                failures.append(
                    DocumentFailure(
                        source_id=source.id,
                        period=period,
                        document_url=str(discovered.canonical_url),
                        message=f"{source.id}/{period.label}: {error}",
                        is_newer=is_newer,
                    )
                )
                continue
        reported_periods = [
            period
            for document in reported_documents
            if document.is_published
            and (period := infer_period(f"{document.title} {document.canonical_url}")) is not None
        ]
        unique_periods = {period.period_id: period for period in reported_periods}
        unique_documents = {
            str(document.canonical_url): document for document in reported_documents
        }
        return FinancialAcquisition(
            observations=results,
            discovered_periods=sorted(unique_periods.values(), key=lambda item: item.end_date),
            documents=list(unique_documents.values()),
            failures=failures,
            anthropic_calls=anthropic_calls,
            checked_at=checked_at,
        )
