"""Chargement typé de toute la configuration YAML du projet."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from vigie_pipeline.exceptions import ConfigurationError

if TYPE_CHECKING:
    from vigie_pipeline.settings import Settings


class ConfigModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class CompanyConfig(ConfigModel):
    name: str
    full_name: str = Field(alias="fullName")
    ticker: str
    investor_relations_url: HttpUrl = Field(alias="investorRelationsUrl")


class MetricConfig(ConfigModel):
    label: str
    unit: str
    format: str
    comparison: Literal["percent", "percentage_point", "contextual"]
    favorable_trend: Literal["up", "down", "contextual"] = Field(alias="favorableTrend")


class SourceConfig(ConfigModel):
    id: str
    company_id: str = Field(alias="companyId")
    content_category: Literal["financial_results", "official_news", "secondary_news"] = Field(
        alias="contentCategory"
    )
    type: Literal["html_release_index", "html_news_index", "rss", "document"]
    url: HttpUrl
    adapter: str
    priority: Literal["regulatory", "primary", "official_release", "specialized_media", "secondary"]
    language: str
    enabled: bool
    required: bool = True
    timeout_seconds: float = Field(alias="timeoutSeconds", gt=0)
    attempts: int = Field(ge=1)
    expected_metrics: list[str] = Field(default_factory=list, alias="expectedMetrics")
    fetch_policy: str = Field(alias="fetchPolicy")
    link_selector: str = Field(default="a[href]", alias="linkSelector")
    article_selector: str = Field(default="article, main", alias="articleSelector")
    include_patterns: list[str] = Field(default_factory=list, alias="includePatterns")
    max_articles: int = Field(default=10, alias="maxArticles", ge=1, le=100)
    document_url_template: str | None = Field(default=None, alias="documentUrlTemplate")


class HttpConfig(ConfigModel):
    timeout_seconds: float = Field(alias="timeoutSeconds", gt=0)
    attempts: int = Field(ge=1)
    max_download_bytes: int = Field(alias="maxDownloadBytes", ge=1)


class ValidationConfig(ConfigModel):
    delta_tolerance: float = Field(alias="deltaTolerance", ge=0)
    minimum_observations: int = Field(alias="minimumObservations", ge=1)
    maximum_volume_drop: float = Field(alias="maximumVolumeDrop", ge=0, le=1)


class LlmConfig(ConfigModel):
    max_input_characters: int = Field(alias="maxInputCharacters", ge=1)
    max_output_tokens: int = Field(default=2048, alias="maxOutputTokens", ge=128)
    standard_model: str = Field(alias="standardModel")
    complex_model: str = Field(alias="complexModel")
    standard_tasks: list[str] = Field(alias="standardTasks")
    complex_tasks: list[str] = Field(alias="complexTasks")


class PublicationConfig(ConfigModel):
    destination: Literal["github_pages"]
    atomic: bool


class PipelineConfig(ConfigModel):
    http: HttpConfig
    validation: ValidationConfig
    llm: LlmConfig
    publication: PublicationConfig


class ProjectConfig(ConfigModel):
    companies: dict[str, CompanyConfig]
    metrics: dict[str, MetricConfig]
    sources: list[SourceConfig]
    pipeline: PipelineConfig

    @property
    def known_units(self) -> set[str]:
        return {metric.unit for metric in self.metrics.values()}


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as error:
        raise ConfigurationError(f"Configuration YAML illisible: {path}") from error
    if not isinstance(loaded, dict):
        raise ConfigurationError(f"La racine YAML doit être un objet: {path}")
    return loaded


def load_project_config(root_dir: Path, settings: Settings | None = None) -> ProjectConfig:
    """Charge les quatre YAML et applique les remplacements d’environnement autorisés."""

    config_dir = root_dir / "config"
    payload = {
        "companies": _read_yaml(config_dir / "companies.yaml").get("companies", {}),
        "metrics": _read_yaml(config_dir / "metrics.yaml").get("metrics", {}),
        "sources": _read_yaml(config_dir / "sources.yaml").get("sources", []),
        "pipeline": _read_yaml(config_dir / "pipeline.yaml"),
    }
    config = ProjectConfig.model_validate(payload)
    if settings is not None:
        if settings.anthropic_standard_model:
            config.pipeline.llm.standard_model = settings.anthropic_standard_model
        if settings.anthropic_complex_model:
            config.pipeline.llm.complex_model = settings.anthropic_complex_model
    _validate_references(config)
    return config


def _validate_references(config: ProjectConfig) -> None:
    for source in config.sources:
        if source.company_id not in config.companies:
            raise ConfigurationError(f"Source {source.id}: compagnie inconnue {source.company_id}")
        unknown_metrics = set(source.expected_metrics) - set(config.metrics)
        if unknown_metrics:
            raise ConfigurationError(
                f"Source {source.id}: métriques inconnues {sorted(unknown_metrics)}"
            )
        if source.content_category == "financial_results" and not source.expected_metrics:
            raise ConfigurationError(f"Source financière sans métriques attendues: {source.id}")
        if source.content_category != "financial_results" and source.expected_metrics:
            raise ConfigurationError(f"Source d’actualités avec métriques financières: {source.id}")
