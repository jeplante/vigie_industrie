"""Chargement strict des sources configurées en YAML."""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, HttpUrl


class SourceConfig(BaseModel):
    id: str
    company_id: str = Field(alias="companyId")
    type: str
    url: HttpUrl
    adapter: str
    priority: Literal["regulatory", "primary", "official_release", "specialized_media", "secondary"]
    language: str
    enabled: bool
    timeout_seconds: float = Field(alias="timeoutSeconds", gt=0)
    attempts: int = Field(ge=1)
    expected_metrics: list[str] = Field(alias="expectedMetrics")
    fetch_policy: str = Field(alias="fetchPolicy")


def load_sources(path: Path) -> list[SourceConfig]:
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [SourceConfig.model_validate(item) for item in raw.get("sources", [])]
