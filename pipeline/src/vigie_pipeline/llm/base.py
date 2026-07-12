"""Contrat indépendant du fournisseur et modèles de résultat LLM."""

from datetime import datetime
from typing import Protocol, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class NewsAnalysis(BaseModel):
    summary: str
    categories: list[str] = Field(min_length=1)
    importance: str
    themes: list[str]
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
