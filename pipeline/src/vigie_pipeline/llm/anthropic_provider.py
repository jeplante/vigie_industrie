"""Implémentation Anthropic à sortie JSON strictement validée."""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic
from pydantic import ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from vigie_pipeline.exceptions import ConfigurationError, LlmError, TemporaryLlmError
from vigie_pipeline.llm.base import NewsAnalysis, T
from vigie_pipeline.settings import Settings

LOGGER = logging.getLogger(__name__)
PROMPT_VERSION = "2026-07-11.v1"


class AnthropicProvider:
    """Anthropic n’est appelé qu’après l’échec d’une extraction déterministe."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        if not settings.anthropic_api_key and client is None:
            raise ConfigurationError(
                "ANTHROPIC_API_KEY est absente; utilisez le mode hors ligne "
                "ou configurez le secret."
            )
        self.settings = settings
        self.client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def extract_structured(
        self,
        *,
        content: str,
        output_model: type[T],
        task_name: str,
        complex_task: bool = False,
    ) -> T:
        model = (
            self.settings.anthropic_complex_model
            if complex_task
            else self.settings.anthropic_standard_model
        )
        schema = output_model.model_json_schema()
        prompt = (
            "Retournez uniquement un objet JSON conforme au schéma fourni. "
            "N’inventez aucune donnée; utilisez null lorsque le schéma le permet.\n"
            f"Tâche: {task_name}\nSchéma: {json.dumps(schema, ensure_ascii=False)}\n"
            f"Contenu source:\n{content[: self.settings.llm_max_input_chars]}"
        )
        raw = self._request(model=model, task_name=task_name, prompt=prompt)
        try:
            return output_model.model_validate_json(raw)
        except ValidationError as error:
            raise LlmError(f"Réponse Anthropic non conforme pour {task_name}") from error

    def summarize_news(self, *, title: str, content: str, source_url: str) -> NewsAnalysis:
        prompt_content = f"Titre: {title}\nURL: {source_url}\nTexte: {content}"
        return self.extract_structured(
            content=prompt_content,
            output_model=NewsAnalysis,
            task_name="summarize_news_fr",
        )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(TemporaryLlmError),
        reraise=True,
    )
    def _request(self, *, model: str, task_name: str, prompt: str) -> str:
        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=2_048,
                temperature=0,
                system=f"Assistant d’extraction financière. Version de prompt: {PROMPT_VERSION}",
                messages=[{"role": "user", "content": prompt}],
            )
        except (
            anthropic.APITimeoutError,
            anthropic.APIConnectionError,
            anthropic.RateLimitError,
        ) as error:
            raise TemporaryLlmError(
                f"Erreur Anthropic temporaire: {error.__class__.__name__}"
            ) from error
        except anthropic.APIError as error:
            raise LlmError(f"Erreur Anthropic permanente: {error.__class__.__name__}") from error
        usage = getattr(response, "usage", None)
        LOGGER.info(
            "llm_request provider=anthropic model=%s task=%s usage=%s",
            model,
            task_name,
            usage,
        )
        blocks = getattr(response, "content", [])
        text = "".join(str(getattr(block, "text", "")) for block in blocks)
        if not text:
            raise LlmError(f"Réponse Anthropic vide pour {task_name}")
        return text.strip()
