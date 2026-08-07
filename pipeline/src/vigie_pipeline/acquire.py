"""Acquisition conservatrice des nouveaux documents financiers officiels."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
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
from vigie_pipeline.llm.base import LlmProvider
from vigie_pipeline.llm.openai_provider import PROMPT_VERSION, OpenAIProvider
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
    llm_calls: int
    checked_at: datetime
    discovery_warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DocumentFailure:
    source_id: str
    period: Period
    document_url: str
    message: str
    is_newer: bool


def infer_period(title: str) -> Period | None:
    text = title.lower()
    has_annual_marker = (
        re.search(
            r"\b(?:annual|annuel|full[- ]year|exercice)\b",
            text,
        )
        is not None
    )
    explicit_quarter = re.search(r"(?:q|t)([1-4])[-_/ ]*(20\d{2})", text)
    compact_quarter = (
        re.search(r"(?:q|t)([1-4])([0-9]{2})(?!\d)", text) if explicit_quarter is None else None
    )
    reverse_compact_quarter = (
        re.search(r"([1-4])(?:q|t)([0-9]{2})(?!\d)", text)
        if explicit_quarter is None and compact_quarter is None
        else None
    )
    if explicit_quarter is None:
        reverse_quarter = (
            re.search(r"(20\d{2})[-_/ ]*(?:q|t)([1-4])", text)
            if compact_quarter is None and reverse_compact_quarter is None
            else None
        )
        if compact_quarter:
            quarter_number = int(compact_quarter[1])
            year = 2000 + int(compact_quarter[2])
        elif reverse_compact_quarter:
            quarter_number = int(reverse_compact_quarter[1])
            year = 2000 + int(reverse_compact_quarter[2])
        elif reverse_quarter:
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
        if quarter_number == 4 and not has_annual_marker:
            return None
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
    word_text = re.sub(r"[-_/]+", " ", text)
    quarter_patterns: dict[
        Literal["T1", "T2", "T3", "AN"], tuple[int, tuple[str, ...], tuple[int, int]]
    ] = {
        "T1": (1, ("first quarter", "1st quarter", "premier trimestre"), (3, 31)),
        "T2": (2, ("second quarter", "2nd quarter", "deuxième trimestre"), (6, 30)),
        "T3": (3, ("third quarter", "3rd quarter", "troisième trimestre"), (9, 30)),
        "AN": (4, ("fourth quarter", "4th quarter", "quatrième trimestre"), (12, 31)),
    }
    for key, (quarter, markers, end) in quarter_patterns.items():
        marker = next((item for item in markers if item in word_text), None)
        if marker is not None:
            if key == "AN" and not has_annual_marker:
                continue
            marker_position = word_text.find(marker)
            following = word_text[marker_position + len(marker) : marker_position + 100]
            preceding = word_text[max(0, marker_position - 40) : marker_position]
            preceding_years = list(re.finditer(r"20\d{2}", preceding))
            year_match = re.search(r"20\d{2}", following) or (
                preceding_years[-1] if preceding_years else None
            )
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
    annual_match = (
        re.search(
            r"annual[-_ ]?report[^0-9]{0,15}(20\d{2})",
            word_text,
        )
        or re.search(
            r"(?:annuel|full year|exercice|annual)[^0-9]{0,30}(20\d{2})",
            word_text,
        )
        or re.search(
            r"\breports? (20\d{2}) (?:net income|core earnings|results)\b",
            word_text,
        )
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


def historical_periods(latest: Period, years: int) -> list[Period]:
    """Construit la fenêtre glissante, sans créer de période après la plus récente."""

    result: list[Period] = []
    first_year = max(2000, latest.year - years + 1)
    for year in range(first_year, latest.year + 1):
        last_quarter = (latest.quarter or 4) if year == latest.year else 4
        for quarter in range(1, last_quarter + 1):
            key = "AN" if quarter == 4 else f"T{quarter}"
            end = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[quarter]
            result.append(
                Period(
                    period_id=f"{year}-{key}",
                    period_key=cast(Literal["T1", "T2", "T3", "AN"], key),
                    type="annual" if quarter == 4 else "quarter",
                    year=year,
                    quarter=None if quarter == 4 else quarter,
                    end_date=date(year, *end),
                    label=f"Annuel {year}" if quarter == 4 else f"T{quarter} {year}",
                )
            )
    return result


def _missing_history_period_ids(
    dataset: VigieDataset,
    source: SourceConfig,
    latest: Period,
    years: int,
) -> set[str]:
    metrics_by_period: dict[str, set[str]] = {}
    for item in dataset.observations:
        if item.company_id == source.company_id:
            metrics_by_period.setdefault(item.period.period_id, set()).add(item.metric_id)
    expected = set(source.metrics_required_for_success)
    return {
        period.period_id
        for period in historical_periods(latest, years)
        if period.type in source.historical_period_types
        and not expected.issubset(metrics_by_period.get(period.period_id, set()))
    }


def _archive_index_urls(source: SourceConfig) -> list[str]:
    urls: list[str] = []
    if source.archive_url is not None:
        urls.append(str(source.archive_url))
    if source.archive_url_template is not None:
        urls.extend(
            source.archive_url_template.format(page=page)
            for page in range(1, source.archive_pages + 1)
        )
    return urls


def _templated_document(source: SourceConfig, period: Period) -> DiscoveredDocument:
    if source.document_url_template is None:
        raise ExtractionError(f"Source {source.id}: modèle de document absent.")
    quarter = period.quarter or 4
    document_url = source.document_url_template.format(
        year=period.year,
        year_short=str(period.year)[-2:],
        quarter=quarter,
        period_key=period.period_key.lower(),
    )
    return DiscoveredDocument(
        source_id=source.id,
        canonical_url=HttpUrl(document_url),
        title=f"{source.id} {period.label} official results",
        content_type="application/pdf",
        document_kind="downloadable_report",
        is_published=True,
    )


def _configured_historical_documents(source: SourceConfig) -> list[DiscoveredDocument]:
    return [
        DiscoveredDocument(
            source_id=source.id,
            canonical_url=url,
            title=str(url),
            content_type="text/html",
            document_kind="downloadable_report",
            is_published=True,
        )
        for url in source.historical_document_urls
    ]


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
        "annual-information-form",
        "circular",
        "notice-of",
    )
    if any(marker in text for marker in excluded):
        return False
    included = (
        "result",
        "résultat",
        "manulife-reports",
        "news-release",
        "earnings-release",
        "earnings news release",
        "-earnings.pdf",
        "shareholders-report",
        "shareholders report",
        "shareholders' report",
        "-shrpt.pdf",
        "report-to-shareholders",
        "quarterly-report",
        "annual-report",
        "annualreport",
        "annual-",
        "rapport annuel",
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
                structured_attribute = node.get("content") or node.get("datetime")
                structured_value = (
                    structured_attribute if isinstance(structured_attribute, str) else ""
                )
                structured_iso_date = re.match(
                    r"(20\d{2}-(?:0[1-9]|1[0-2])-(?:[0-2]\d|3[01]))",
                    structured_value,
                )
                if structured_iso_date:
                    try:
                        return date.fromisoformat(structured_iso_date[1])
                    except ValueError:
                        pass
                text = f"{structured_value} {text}"
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
    normalized_text = text.lower()
    header_text = normalized_text[:5_000]
    explicitly_dated = re.search(
        rf"\b(?:dated|dat[ée])\s*:?\s*({names})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b",
        normalized_text,
    )
    if explicitly_dated:
        return date(
            int(explicitly_dated[3]),
            months[explicitly_dated[1]],
            int(explicitly_dated[2]),
        )
    release_header = re.search(
        rf"(?:news\s+release|press\s+release|media\s+release|"
        rf"communiqu[ée](?:\s+de\s+presse)?).{{0,180}}?"
        rf"\b({names})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b",
        header_text,
    )
    if release_header:
        return date(
            int(release_header[3]),
            months[release_header[1]],
            int(release_header[2]),
        )
    explicit_release = re.search(
        rf"(?:released|reported|announced|publi[ée]s?).{{0,180}}?"
        rf"\b({names})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b",
        header_text,
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
    named = re.search(rf"\b({names})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b", normalized_text)
    if named:
        return date(int(named[3]), months[named[1]], int(named[2]))
    french = re.search(rf"\b(\d{{1,2}})\s+({names})\s+(20\d{{2}})\b", normalized_text)
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
        provider="openai",
        model=config.pipeline.llm.complex_model,
        prompt_version=PROMPT_VERSION,
        executed_at=datetime.now(UTC),
        task_id=(f"financial_extraction_{source.company_id}_{period.label}_{candidate.metric_id}"),
        source_fingerprint=fingerprint,
        confidence=candidate.confidence,
        warnings=candidate.warnings,
    )


def _comparison_values(
    current: float,
    previous: Observation | None,
    metric: MetricConfig,
) -> tuple[
    float | None,
    Literal["PERCENT", "PERCENTAGE_POINT", "NONE"],
    str,
]:
    if previous is None:
        return None, "NONE", "—"
    if metric.comparison == "percentage_point":
        change = current - previous.value
        return change, "PERCENTAGE_POINT", f"{change:+.1f} pp".replace(".", ",")
    relative_change = calculate_change(current, previous.value)
    return (
        relative_change,
        "PERCENT" if relative_change is not None else "NONE",
        "—" if relative_change is None else f"{relative_change:+.1%}".replace(".", ","),
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
    change, change_unit, display_change = _comparison_values(
        candidate.value,
        previous,
        metric,
    )
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
            change_unit=change_unit,
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
            extraction_method="openai" if is_llm else "deterministic",
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


def _rebuild_acquired_comparisons(
    dataset: VigieDataset,
    observations: list[Observation],
    config: ProjectConfig,
) -> list[Observation]:
    by_id = {item.id: item for item in dataset.observations}
    by_id.update({item.id: item for item in observations})
    combined = dataset.model_copy(update={"observations": list(by_id.values())})
    rebuilt: list[Observation] = []
    for observation in observations:
        previous = _previous(
            combined,
            observation.company_id,
            observation.period,
            observation.metric_id,
        )
        change, change_unit, display_change = _comparison_values(
            observation.value,
            previous,
            config.metrics[observation.metric_id],
        )
        direction = cast(
            Literal["up", "down", "neutral"],
            (
                direction_for(observation.value, previous.value)
                if previous is not None
                else "neutral"
            ),
        )
        rebuilt.append(
            observation.model_copy(
                update={
                    "comparison": Comparison(
                        period_id=previous.period.period_id if previous else None,
                        value=previous.value if previous else None,
                        display_value=previous.display_value if previous else "—",
                        period_label=previous.period.label if previous else "",
                        change=change,
                        change_unit=change_unit,
                        display_change=display_change,
                    ),
                    "direction": direction,
                }
            )
        )
    return rebuilt


def rebuild_dataset_comparisons(
    dataset: VigieDataset,
    config: ProjectConfig,
) -> list[Observation]:
    """Rebuild derived comparisons after audited historical corrections."""
    return _rebuild_acquired_comparisons(dataset, dataset.observations, config)


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
        latest_published = max(
            (item.period for item in dataset.observations if item.company_id == source.company_id),
            key=lambda item: item.end_date,
            default=None,
        )
        initial_periods = [
            period
            for document in documents
            if document.is_published
            and (period := infer_period(f"{document.title} {document.canonical_url}")) is not None
        ]
        if index_period is not None:
            initial_periods.append(index_period)
        latest_anchor = max(
            [*initial_periods, *([latest_published] if latest_published else [])],
            key=lambda item: item.end_date,
            default=None,
        )
        discovery_warnings: list[str] = []
        if latest_anchor is not None and _missing_history_period_ids(
            dataset,
            source,
            latest_anchor,
            config.pipeline.financial_history_years,
        ):
            documents.extend(_configured_historical_documents(source))
            for archive_url in _archive_index_urls(source):
                try:
                    archive_index = fetcher.fetch(archive_url)
                except PipelineError as error:
                    discovery_warnings.append(
                        f"{source.id}: archive inaccessible {archive_url}: {error}"
                    )
                    continue
                documents.extend(
                    item
                    for item in discover_documents(source.id, archive_index)
                    if (item.document_kind == "future_event" and _relevant_future_event(item))
                    or _relevant_financial_document(item)
                )

        archive_periods = [
            period
            for document in documents
            if document.is_published
            and (period := infer_period(f"{document.title} {document.canonical_url}")) is not None
        ]
        latest_anchor = max(
            [*archive_periods, *([latest_anchor] if latest_anchor else [])],
            key=lambda item: item.end_date,
            default=None,
        )
        history_period_ids: set[str] = set()
        if latest_anchor is not None:
            history_period_ids = _missing_history_period_ids(
                dataset,
                source,
                latest_anchor,
                config.pipeline.financial_history_years,
            )
            if source.document_url_template:
                documents.extend(
                    _templated_document(source, period)
                    for period in historical_periods(
                        latest_anchor,
                        config.pipeline.financial_history_years,
                    )
                    if period.period_id in history_period_ids and period.type != "annual"
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
        published_periods = [
            period
            for document in documents
            if document.is_published
            and (period := infer_period(f"{document.title} {document.canonical_url}")) is not None
        ]
        if (
            source.document_url_template
            and latest_published is not None
            and latest_published.type in source.historical_period_types
            and not published_periods
        ):
            documents.append(_templated_document(source, latest_published))
        documents = list(
            {
                str(document.canonical_url).rstrip("/").lower(): document for document in documents
            }.values()
        )
        period_documents = [
            (document, period)
            for document in documents
            if document.is_published
            and (period := infer_period(f"{document.title} {document.canonical_url}")) is not None
        ]
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
                item[1].period_id in history_period_ids,
                str(item[0].canonical_url).rstrip("/").lower() not in known_urls,
                item[1].end_date,
            ),
            reverse=True,
        )
        results: list[Observation] = []
        failures: list[DocumentFailure] = []
        llm_calls = 0
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
                and latest_discovered is not None
                and latest_discovered.period_id == latest_published.period_id
            )
            missing_history = period.period_id in history_period_ids
            if not (is_newer or is_latest or unknown_current or missing_history):
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
                existing_metrics = {item.metric_id for item in existing}
                if (
                    set(source.expected_metrics).issubset(existing_metrics)
                    and existing
                    and all(item.source.document_hash == fingerprint for item in existing)
                ):
                    successful_periods.add(period.period_id)
                    continue
                content = document_text(document)
                candidates: list[MetricCandidate | LlmMetric] = list(
                    index_candidates
                    if discovered.document_kind == "index_metrics"
                    else adapter.extract_metrics(content)
                )
                found = {item.metric_id for item in candidates}
                missing_expected = set(source.expected_metrics) - (found | existing_metrics)
                if missing_expected and settings.openai_api_key:
                    provider = llm_provider or OpenAIProvider(settings, config.pipeline.llm)
                    llm_calls += 1
                    extraction = provider.extract_structured(
                        content=content,
                        output_model=LlmMetricExtraction,
                        task_name=f"financial_extraction_{source.company_id}_{period.label}",
                        complex_task=True,
                    )
                    candidates.extend(
                        item for item in extraction.metrics if item.metric_id in missing_expected
                    )
                    found = {item.metric_id for item in candidates}
                missing_required = set(source.metrics_required_for_success) - (
                    found | existing_metrics
                )
                if missing_required:
                    raise ExtractionError(
                        f"{source.id}/{period.label}: métriques officielles "
                        f"requises manquantes {sorted(missing_required)}"
                    )
                by_metric = {item.metric_id: item for item in candidates}
                same_document_metrics = {
                    item.metric_id
                    for item in existing
                    if str(item.source.url).rstrip("/").lower() == canonical_url
                }
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
                    if metric_id in by_metric
                    and (metric_id not in existing_metrics or metric_id in same_document_metrics)
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
        failures = [
            failure for failure in failures if failure.period.period_id not in successful_periods
        ]
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
        discovered_period_ids = {period.period_id for _, period in period_documents}
        undiscovered_history = sorted(history_period_ids - discovered_period_ids)
        if undiscovered_history:
            discovery_warnings.append(
                f"{source.id}: périodes historiques non découvertes {undiscovered_history}."
            )
        return FinancialAcquisition(
            observations=_rebuild_acquired_comparisons(dataset, results, config),
            discovered_periods=sorted(unique_periods.values(), key=lambda item: item.end_date),
            documents=list(unique_documents.values()),
            failures=failures,
            discovery_warnings=discovery_warnings,
            llm_calls=llm_calls,
            checked_at=checked_at,
        )
