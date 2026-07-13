"""Modèles canoniques partagés par les étapes du pipeline."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])


class CanonicalModel(BaseModel):
    """Base stricte avec sérialisation camelCase pour le frontend."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class Company(CanonicalModel):
    id: str
    name: str
    full_name: str
    ticker: str
    investor_relations_url: HttpUrl


class Period(CanonicalModel):
    period_id: str = Field(pattern=r"^20\d{2}-(T1|T2|T3|AN)$")
    period_key: Literal["T1", "T2", "T3", "AN"]
    type: Literal["quarter", "annual"]
    year: int = Field(ge=2000)
    quarter: int | None = Field(default=None, ge=1, le=4)
    end_date: date
    label: str

    @model_validator(mode="after")
    def validate_composite_id(self) -> Period:
        expected_id = f"{self.year}-{self.period_key}"
        if self.period_id != expected_id:
            raise ValueError(f"periodId doit être {expected_id}")
        expected_quarter = {"T1": 1, "T2": 2, "T3": 3, "AN": None}[self.period_key]
        expected_type = "annual" if self.period_key == "AN" else "quarter"
        if self.quarter != expected_quarter or self.type != expected_type:
            raise ValueError("periodKey, quarter et type sont incohérents")
        return self


class SourceReference(CanonicalModel):
    source_id: str
    url: HttpUrl
    title: str
    published_at: date
    fetched_at: datetime
    document_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    priority: Literal["primary", "secondary"]


class LlmTrace(CanonicalModel):
    provider: str
    model: str
    prompt_version: str
    executed_at: datetime
    task_id: str
    source_fingerprint: str
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)


class ObservationQuality(CanonicalModel):
    status: Literal["validated", "warning", "rejected"]
    extraction_method: str
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    llm_trace: LlmTrace | None = None


class Comparison(CanonicalModel):
    period_id: str | None = None
    value: float | None = None
    display_value: str
    period_label: str
    change: float | None = None
    change_unit: Literal["PERCENT", "PERCENTAGE_POINT", "NONE"]
    display_change: str


class Observation(CanonicalModel):
    id: str
    company_id: str
    period: Period
    metric_id: str
    label: str
    value: Annotated[float, Field(allow_inf_nan=False)]
    unit: str
    display_value: str
    comparison: Comparison
    direction: Literal["up", "down", "neutral"]
    note: str
    source: SourceReference
    quality: ObservationQuality


class NewsSource(CanonicalModel):
    type: Literal["official_ir", "official_release", "specialized_media", "secondary"]
    name: str
    url: HttpUrl
    source_id: str | None = None
    fetched_at: datetime | None = None
    document_hash: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")


class NewsItem(CanonicalModel):
    id: str
    company_ids: list[str] = Field(min_length=1)
    period_id: str = Field(pattern=r"^20\d{2}-(T1|T2|T3|AN)$")
    period_key: Literal["T1", "T2", "T3", "AN"]
    published_at: date
    source: NewsSource
    title: str
    original_summary: str | None = None
    generated_summary: str | None = None
    categories: list[str] = Field(min_length=1)
    importance: Literal["high", "medium", "low"]
    themes: list[str]
    quality: ObservationQuality


class VigieDataset(CanonicalModel):
    schema_version: str
    generated_at: datetime
    companies: list[Company] = Field(min_length=1)
    periods: list[Period] = Field(min_length=1)
    observations: list[Observation] = Field(min_length=1)
    news: list[NewsItem]


class CompanyFreshness(CanonicalModel):
    company_id: str
    latest_available_period_id: str | None = None
    latest_published_period_id: str | None = None
    latest_source_check_at: datetime | None = None
    freshness_status: Literal["current", "stale", "unknown"]


class DatasetManifest(CanonicalModel):
    schema_version: str = "1.0.0"
    generated_at: datetime
    mode: Literal["offline", "live", "migration"]
    dataset_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    observation_count: int = Field(ge=0)
    news_count: int = Field(ge=0)
    company_count: int = Field(ge=0)
    last_successful_refresh: datetime
    company_freshness: list[CompanyFreshness]


class QualityIssue(CanonicalModel):
    code: str
    message: str
    source_id: str | None = None


class SourceRunResult(CanonicalModel):
    source_id: str
    company_id: str
    status: Literal["success", "warning", "failed"]
    documents_discovered: int = Field(ge=0)
    document_urls: list[str] = Field(default_factory=list)
    period_ids: list[str] = Field(default_factory=list)
    message: str | None = None
    anthropic_calls: int = Field(default=0, ge=0)


class QualityReport(CanonicalModel):
    generated_at: datetime
    mode: Literal["offline", "live", "migration"]
    dry_run: bool = False
    status: Literal["success", "partial", "failed"]
    sources_checked: int = Field(ge=0)
    sources_succeeded: int = Field(ge=0)
    sources_failed: int = Field(ge=0)
    observations_added: int = Field(ge=0)
    observations_updated: int = Field(ge=0)
    overrides_applied: int = Field(ge=0, default=0)
    warnings: list[QualityIssue] = Field(default_factory=list)
    errors: list[QualityIssue] = Field(default_factory=list)
    source_results: list[SourceRunResult] = Field(default_factory=list)


class DiscoveredDocument(CanonicalModel):
    source_id: str
    canonical_url: HttpUrl
    title: str
    published_at: date | None = None
    etag: str | None = None
    last_modified: str | None = None
    content_hash: str | None = None
    content_type: str | None = None
    document_kind: Literal[
        "published_result", "downloadable_report", "future_event", "index_metrics", "unknown"
    ] = "unknown"
    is_published: bool = True
