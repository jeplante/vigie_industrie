from types import SimpleNamespace

import anthropic
import httpx
import pytest

from vigie_pipeline.config import ProjectConfig
from vigie_pipeline.exceptions import (
    ConfigurationError,
    LlmError,
    LlmIncompleteError,
    LlmRefusalError,
    StructuredOutputUnsupportedError,
)
from vigie_pipeline.llm.anthropic_provider import AnthropicProvider
from vigie_pipeline.llm.base import NewsAnalysis
from vigie_pipeline.settings import Settings


class FakeMessages:
    def __init__(self, response: SimpleNamespace | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeClient:
    def __init__(self, response: SimpleNamespace | Exception) -> None:
        self.messages = FakeMessages(response)


def response(
    parsed: object | None,
    *,
    stop_reason: str = "end_turn",
    block_type: str = "text",
) -> SimpleNamespace:
    return SimpleNamespace(
        parsed_output=parsed,
        stop_reason=stop_reason,
        content=[SimpleNamespace(type=block_type)],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


def valid_analysis() -> NewsAnalysis:
    return NewsAnalysis(
        summary="Résumé français",
        categories=["financial_results"],
        importance="high",
        themes=["BPA"],
        company_ids=["MFC"],
        confidence=0.9,
        warnings=[],
    )


def test_missing_api_key_is_rejected(project_config: ProjectConfig) -> None:
    with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider(Settings(anthropic_api_key=None), project_config.pipeline.llm)


def test_native_structured_response_is_validated(project_config: ProjectConfig) -> None:
    client = FakeClient(response(valid_analysis()))
    provider = AnthropicProvider(Settings(), project_config.pipeline.llm, client=client)
    result = provider.summarize_news(
        title="Titre", content="Contenu", source_url="https://example.com"
    )
    assert result == valid_analysis()
    call = client.messages.calls[0]
    assert call["output_format"] is NewsAnalysis
    assert call["model"] == "claude-haiku-4-5"
    assert call["temperature"] == 0


@pytest.mark.parametrize("stop_reason", ["max_tokens", "model_context_window_exceeded"])
def test_incomplete_response_is_rejected(project_config: ProjectConfig, stop_reason: str) -> None:
    provider = AnthropicProvider(
        Settings(),
        project_config.pipeline.llm,
        client=FakeClient(response(None, stop_reason=stop_reason)),
    )
    with pytest.raises(LlmIncompleteError, match="tronquée"):
        provider.summarize_news(title="Titre", content="Contenu", source_url="https://example.com")


def test_refusal_is_rejected(project_config: ProjectConfig) -> None:
    provider = AnthropicProvider(
        Settings(),
        project_config.pipeline.llm,
        client=FakeClient(response(None, stop_reason="refusal", block_type="refusal")),
    )
    with pytest.raises(LlmRefusalError, match="refusé"):
        provider.summarize_news(title="Titre", content="Contenu", source_url="https://example.com")


def test_missing_parsed_output_is_rejected(project_config: ProjectConfig) -> None:
    provider = AnthropicProvider(
        Settings(), project_config.pipeline.llm, client=FakeClient(response(None))
    )
    with pytest.raises(LlmIncompleteError, match="absente"):
        provider.summarize_news(title="Titre", content="Contenu", source_url="https://example.com")


def test_additional_pydantic_validation_rejects_wrong_shape(
    project_config: ProjectConfig,
) -> None:
    provider = AnthropicProvider(
        Settings(),
        project_config.pipeline.llm,
        client=FakeClient(response({"summary": "incomplet"})),
    )
    with pytest.raises(LlmError, match="non conforme"):
        provider.summarize_news(title="Titre", content="Contenu", source_url="https://example.com")


def test_unsupported_structured_outputs_are_explicit(project_config: ProjectConfig) -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.BadRequestError(
        "Model does not support structured output_format",
        response=httpx.Response(400, request=request),
        body=None,
    )
    provider = AnthropicProvider(Settings(), project_config.pipeline.llm, client=FakeClient(error))
    with pytest.raises(StructuredOutputUnsupportedError, match="non pris en charge"):
        provider.summarize_news(title="Titre", content="Contenu", source_url="https://example.com")


def test_complex_tasks_use_sonnet_5(project_config: ProjectConfig) -> None:
    client = FakeClient(response(valid_analysis()))
    provider = AnthropicProvider(Settings(), project_config.pipeline.llm, client=client)
    provider.extract_structured(
        content="tableau complexe",
        output_model=NewsAnalysis,
        task_name="complex_table",
        complex_task=True,
    )
    assert client.messages.calls[0]["model"] == "claude-sonnet-5"
