"""Fournisseur Anthropic utilisant les Structured Outputs natifs du SDK."""

from __future__ import annotations

import logging
from typing import Any

import anthropic
from pydantic import ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from vigie_pipeline.config import LlmConfig
from vigie_pipeline.exceptions import (
    ConfigurationError,
    LlmError,
    LlmIncompleteError,
    LlmRefusalError,
    StructuredOutputUnsupportedError,
    TemporaryLlmError,
)
from vigie_pipeline.llm.base import NewsAnalysis, T
from vigie_pipeline.settings import Settings

LOGGER = logging.getLogger(__name__)
PROMPT_VERSION = "2026-07-12.v2"


class AnthropicProvider:
    """Appelle Anthropic avec un modèle Pydantic comme format de sortie contraint."""

    def __init__(
        self,
        settings: Settings,
        llm_config: LlmConfig,
        client: Any | None = None,
    ) -> None:
        if not settings.anthropic_api_key and client is None:
            raise ConfigurationError(
                "ANTHROPIC_API_KEY est absente; utilisez le mode hors ligne "
                "ou configurez le secret."
            )
        self.settings = settings
        self.config = llm_config
        self.client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def extract_structured(
        self,
        *,
        content: str,
        output_model: type[T],
        task_name: str,
        complex_task: bool = False,
    ) -> T:
        model = self.config.complex_model if complex_task else self.config.standard_model
        prompt = (
            "N’inventez aucune donnée. Retournez seulement les faits explicitement présents "
            "dans le contenu source et utilisez les champs optionnels lorsque l’information "
            f"manque. Tâche: {task_name}\nContenu source:\n"
            f"{content[: self.config.max_input_characters]}"
        )
        return self._request(
            model=model,
            task_name=task_name,
            prompt=prompt,
            output_model=output_model,
        )

    def summarize_news(self, *, title: str, content: str, source_url: str) -> NewsAnalysis:
        prompt_content = (
            "Produisez un résumé factuel en français, puis classez l’actualité. "
            "company_ids doit utiliser uniquement MFC, SLF, GWO ou IAG quand la société "
            f"est explicitement concernée.\nTitre: {title}\nURL: {source_url}\nTexte: {content}"
        )
        return self.extract_structured(
            content=prompt_content,
            output_model=NewsAnalysis,
            task_name="summarize_news_fr",
            complex_task=False,
        )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(TemporaryLlmError),
        reraise=True,
    )
    def _request(
        self,
        *,
        model: str,
        task_name: str,
        prompt: str,
        output_model: type[T],
    ) -> T:
        try:
            response = self.client.messages.parse(
                model=model,
                max_tokens=self.config.max_output_tokens,
                temperature=0,
                system=f"Analyse financière factuelle. Prompt: {PROMPT_VERSION}",
                messages=[{"role": "user", "content": prompt}],
                output_format=output_model,
            )
        except (
            anthropic.APITimeoutError,
            anthropic.APIConnectionError,
            anthropic.RateLimitError,
        ) as error:
            raise TemporaryLlmError(
                f"Erreur Anthropic temporaire: {error.__class__.__name__}"
            ) from error
        except anthropic.BadRequestError as error:
            message = str(error).lower()
            if any(term in message for term in ("structured", "output_format", "json schema")):
                raise StructuredOutputUnsupportedError(
                    f"Structured Outputs non pris en charge par {model}"
                ) from error
            raise LlmError(f"Requête Anthropic refusée: {error.__class__.__name__}") from error
        except anthropic.APIError as error:
            raise LlmError(f"Erreur Anthropic permanente: {error.__class__.__name__}") from error

        stop_reason = str(getattr(response, "stop_reason", ""))
        if stop_reason == "refusal" or any(
            getattr(block, "type", "") == "refusal" for block in getattr(response, "content", [])
        ):
            raise LlmRefusalError(f"Claude a refusé la tâche {task_name}")
        if stop_reason in {"max_tokens", "model_context_window_exceeded"}:
            raise LlmIncompleteError(f"Réponse Anthropic tronquée ({stop_reason}) pour {task_name}")
        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            raise LlmIncompleteError(f"Réponse structurée absente pour {task_name}")
        try:
            validated = output_model.model_validate(parsed)
        except ValidationError as error:
            raise LlmError(f"Réponse Anthropic non conforme pour {task_name}") from error
        LOGGER.info(
            "llm_request provider=anthropic model=%s task=%s usage=%s",
            model,
            task_name,
            getattr(response, "usage", None),
        )
        return validated
