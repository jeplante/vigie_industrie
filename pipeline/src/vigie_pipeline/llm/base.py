"""Contrat indépendant du fournisseur et modèles de résultat LLM."""

from datetime import datetime
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class NewsAnalysis(BaseModel):
    summary: str = Field(min_length=1)
    categories: list[
        Literal[
            "financial_results",
            "capital_management",
            "merger_acquisition",
            "strategy",
            "distribution",
            "digital_transformation",
            "artificial_intelligence",
            "regulation",
            "risk",
            "leadership",
            "product",
            "wealth_management",
            "insurance",
            "other",
        ]
    ] = Field(min_length=1)
    importance: Literal["high", "medium", "low"]
    themes: list[str]
    company_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)


class LlmTrace(BaseModel):
    provider: str
    model: str
    prompt_version: str
    executed_at: datetime
    task_id: str
    source_fingerprint: str
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)


class LlmProvider(Protocol):
    def extract_structured(
        self,
        *,
        content: str,
        output_model: type[T],
        task_name: str,
        complex_task: bool = False,
    ) -> T: ...

    def summarize_news(self, *, title: str, content: str, source_url: str) -> NewsAnalysis: ...
