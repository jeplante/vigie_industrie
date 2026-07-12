"""Acquisition conservatrice des nouveaux documents financiers officiels."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from io import BytesIO

from pydantic import BaseModel, Field
from pypdf import PdfReader

from vigie_pipeline.config import SourceConfig
from vigie_pipeline.discovery import discover_documents
from vigie_pipeline.exceptions import ExtractionError
from vigie_pipeline.fetch import BoundedFetcher, FetchResult
from vigie_pipeline.hashing import sha256_bytes
from vigie_pipeline.llm.anthropic_provider import PROMPT_VERSION, AnthropicProvider
from vigie_pipeline.models import (
    Comparison,
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
METRIC_META = {
    "core_eps": ("BPA activités de base", "CAD_PER_SHARE"),
    "core_earnings": ("Résultat activités de base", "CAD_BILLION"),
    "net_income": ("Résultat net", "CAD_BILLION"),
    "licat_ratio": ("Ratio LICAT", "PERCENT"),
    "solvency_ratio": ("Ratio de solvabilité", "PERCENT"),
    "assets_under_management": ("Actif sous gestion", "CAD_BILLION"),
    "assets_under_administration": ("Actif sous gestion et administration", "CAD_BILLION"),
    "total_client_assets": ("Actifs clients totaux", "CAD_BILLION"),
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


def infer_period(title: str) -> Period | None:
    text = title.lower()
    year_match = re.search(r"20\d{2}", text)
    if year_match is None:
        return None
    year = int(year_match.group())
    quarter_patterns = {
        "T1": (1, ("q1", "t1", "first quarter", "premier trimestre"), (3, 31)),
        "T2": (2, ("q2", "t2", "second quarter", "deuxième trimestre"), (6, 30)),
        "T3": (3, ("q3", "t3", "third quarter", "troisième trimestre"), (9, 30)),
    }
    for key, (quarter, markers, end) in quarter_patterns.items():
        if any(marker in text for marker in markers):
            return Period(
                key=key,
                type="quarter",
                year=year,
                quarter=quarter,
                end_date=date(year, *end),
                label=f"{key} {year}",
            )
    if any(marker in text for marker in ("annual", "annuel", "full year", "exercice")):
        return Period(
            key="AN",
            type="annual",
            year=year,
            quarter=None,
            end_date=date(year, 12, 31),
            label=f"Annuel {year}",
        )
    return None


def document_text(result: FetchResult) -> str:
    if result.content_type == "application/pdf":
        try:
            return "\n".join(
                page.extract_text() or "" for page in PdfReader(BytesIO(result.content)).pages
            )
        except Exception as error:
            raise ExtractionError(f"PDF illisible: {result.url}") from error
    return result.content.decode("utf-8", errors="replace")


def _previous(
    dataset: VigieDataset, company_id: str, period: Period, metric_id: str
) -> Observation | None:
    matches = [
        item
        for item in dataset.observations
        if item.company_id == company_id
        and item.period.key == period.key
        and item.period.year < period.year
        and item.metric_id == metric_id
    ]
    return max(matches, key=lambda item: item.period.year, default=None)


def _build_observation(
    *,
    dataset: VigieDataset,
    source: SourceConfig,
    period: Period,
    document: FetchResult,
    title: str,
    candidate: MetricCandidate | LlmMetric,
    llm_trace: LlmTrace | None,
) -> Observation:
    metric_id = candidate.metric_id
    label, unit = METRIC_META[metric_id]
    previous = _previous(dataset, source.company_id, period, metric_id)
    change = calculate_change(candidate.value, previous.value) if previous else None
    direction = direction_for(candidate.value, previous.value) if previous else "neutral"
    display_value = (
        candidate.raw_value if isinstance(candidate, MetricCandidate) else candidate.display_value
    )
    display_change = "—" if change is None else f"{change:+.1%}".replace(".", ",")
    fingerprint = sha256_bytes(document.content)
    confidence = 1.0 if isinstance(candidate, MetricCandidate) else candidate.confidence
    warnings = [] if isinstance(candidate, MetricCandidate) else candidate.warnings
    return Observation(
        id=f"{source.company_id}-{period.year}-{period.key}-{metric_id}",
        company_id=source.company_id,
        period=period,
        metric_id=metric_id,
        label=label,
        value=candidate.value,
        unit=unit,
        display_value=display_value,
        comparison=Comparison(
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
            url=document.url,
            title=title,
            published_at=period.end_date,
            fetched_at=datetime.now(UTC),
            document_hash=fingerprint,
            priority="primary",
        ),
        quality=ObservationQuality(
            status="validated",
            extraction_method="anthropic" if llm_trace else "deterministic",
            confidence=confidence,
            warnings=warnings,
            llm_trace=llm_trace,
        ),
    )


def acquire_source(
    dataset: VigieDataset, source: SourceConfig, settings: Settings
) -> list[Observation]:
    adapter_type = ADAPTERS.get(source.adapter)
    if adapter_type is None:
        raise ExtractionError(f"Adaptateur inconnu: {source.adapter}")
    with BoundedFetcher(
        timeout=source.timeout_seconds,
        attempts=source.attempts,
        max_bytes=settings.max_download_bytes,
    ) as fetcher:
        index = fetcher.fetch(str(source.url))
        documents = discover_documents(source.id, index)
        results: list[Observation] = []
        for discovered in documents:
            period = infer_period(discovered.title)
            if period is None:
                continue
            existing = [
                item
                for item in dataset.observations
                if item.company_id == source.company_id
                and item.period.key == period.key
                and item.period.year == period.year
            ]
            if existing and all(
                item.quality.extraction_method == "v1_migration" for item in existing
            ):
                continue
            document = fetcher.fetch(str(discovered.canonical_url))
            fingerprint = sha256_bytes(document.content)
            if existing and all(item.source.document_hash == fingerprint for item in existing):
                continue
            content = document_text(document)
            deterministic = adapter_type().extract_metrics(content)
            candidates: list[MetricCandidate | LlmMetric] = list(deterministic)
            llm_trace = None
            found = {item.metric_id for item in candidates}
            missing = set(source.expected_metrics) - found
            if missing and settings.anthropic_api_key:
                provider = AnthropicProvider(settings)
                extraction = provider.extract_structured(
                    content=content,
                    output_model=LlmMetricExtraction,
                    task_name=f"financial_extraction_{source.company_id}_{period.label}",
                    complex_task=True,
                )
                candidates.extend(item for item in extraction.metrics if item.metric_id in missing)
                found = {item.metric_id for item in candidates}
                llm_trace = LlmTrace(
                    provider="anthropic",
                    model=settings.anthropic_complex_model,
                    prompt_version=PROMPT_VERSION,
                    executed_at=datetime.now(UTC),
                    task_id=f"financial_extraction_{source.company_id}_{period.label}",
                    source_fingerprint=fingerprint,
                    confidence=min((item.confidence for item in extraction.metrics), default=0.5),
                    warnings=[],
                )
            missing = set(source.expected_metrics) - found
            if missing:
                raise ExtractionError(
                    f"{source.id}/{period.label}: métriques officielles "
                    f"manquantes {sorted(missing)}"
                )
            by_metric = {item.metric_id: item for item in candidates}
            results.extend(
                _build_observation(
                    dataset=dataset,
                    source=source,
                    period=period,
                    document=document,
                    title=discovered.title,
                    candidate=by_metric[metric_id],
                    llm_trace=llm_trace,
                )
                for metric_id in source.expected_metrics
            )
        return results
