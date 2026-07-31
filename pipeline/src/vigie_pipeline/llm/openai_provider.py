"""Fournisseur OpenAI utilisant les Structured Outputs de l'API Responses."""

from __future__ import annotations

import logging
from typing import Any

import openai
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


class OpenAIProvider:
    """Appelle OpenAI avec un modèle Pydantic comme format de sortie contraint."""

    def __init__(
        self,
        settings: Settings,
        llm_config: LlmConfig,
        client: Any | None = None,
    ) -> None:
        if not settings.openai_api_key and client is None:
            raise ConfigurationError(
                "OPENAI_API_KEY est absente; utilisez le mode hors ligne ou configurez le secret."
            )
        self.settings = settings
        self.config = llm_config
        self.client = client or openai.OpenAI(api_key=settings.openai_api_key)

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
            "N'inventez aucune donnée. Retournez seulement les faits explicitement présents "
            "dans le contenu source et utilisez les champs optionnels lorsque l'information "
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
            "Produisez un résumé factuel en français, puis classez l'actualité. "
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
            response = self.client.responses.parse(
                model=model,
                instructions=f"Analyse financière factuelle. Prompt: {PROMPT_VERSION}",
                input=prompt,
                text_format=output_model,
                max_output_tokens=self.config.max_output_tokens,
                reasoning={"effort": "none"},
                store=False,
            )
        except ValidationError as error:
            raise LlmIncompleteError(
                f"Réponse structurée OpenAI tronquée ou illisible pour {task_name}"
            ) from error
        except (
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.RateLimitError,
        ) as error:
            raise TemporaryLlmError(
                f"Erreur OpenAI temporaire: {error.__class__.__name__}"
            ) from error
        except openai.BadRequestError as error:
            message = str(error).lower()
            if any(term in message for term in ("structured", "text_format", "json schema")):
                raise StructuredOutputUnsupportedError(
                    f"Structured Outputs non pris en charge par {model}"
                ) from error
            raise LlmError(f"Requête OpenAI refusée: {error.__class__.__name__}") from error
        except openai.APIError as error:
            raise LlmError(f"Erreur OpenAI permanente: {error.__class__.__name__}") from error

        if any(
            getattr(part, "type", "") == "refusal"
            for item in getattr(response, "output", [])
            for part in getattr(item, "content", [])
        ):
            raise LlmRefusalError(f"OpenAI a refusé la tâche {task_name}")
        status = str(getattr(response, "status", ""))
        if status == "incomplete":
            details = getattr(response, "incomplete_details", None)
            reason = getattr(details, "reason", "unknown")
            raise LlmIncompleteError(f"Réponse OpenAI tronquée ({reason}) pour {task_name}")
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise LlmIncompleteError(f"Réponse structurée absente pour {task_name}")
        try:
            validated = output_model.model_validate(parsed)
        except ValidationError as error:
            raise LlmError(f"Réponse OpenAI non conforme pour {task_name}") from error
        LOGGER.info(
            "llm_request provider=openai model=%s task=%s usage=%s",
            model,
            task_name,
            getattr(response, "usage", None),
        )
        return validated
