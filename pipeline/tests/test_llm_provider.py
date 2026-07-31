from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import ValidationError

from vigie_pipeline.config import ProjectConfig
from vigie_pipeline.exceptions import (
    ConfigurationError,
    LlmError,
    LlmIncompleteError,
    LlmRefusalError,
    StructuredOutputUnsupportedError,
)
from vigie_pipeline.llm.base import NewsAnalysis
from vigie_pipeline.llm.openai_provider import OpenAIProvider
from vigie_pipeline.settings import Settings


class FakeResponses:
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
        self.responses = FakeResponses(response)


def response(
    parsed: object | None,
    *,
    status: str = "completed",
    content_type: str = "output_text",
    incomplete_reason: str = "max_output_tokens",
) -> SimpleNamespace:
    return SimpleNamespace(
        output_parsed=parsed,
        status=status,
        incomplete_details=SimpleNamespace(reason=incomplete_reason),
        output=[SimpleNamespace(content=[SimpleNamespace(type=content_type)])],
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
    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY"):
        OpenAIProvider(Settings(openai_api_key=None), project_config.pipeline.llm)


def test_native_structured_response_is_validated(project_config: ProjectConfig) -> None:
    client = FakeClient(response(valid_analysis()))
    provider = OpenAIProvider(Settings(), project_config.pipeline.llm, client=client)
    result = provider.summarize_news(
        title="Titre", content="Contenu", source_url="https://example.com"
    )
    assert result == valid_analysis()
    call = client.responses.calls[0]
    assert call["text_format"] is NewsAnalysis
    assert call["model"] == "gpt-5.6-luna"
    assert call["reasoning"] == {"effort": "none"}
    assert call["store"] is False
    assert "temperature" not in call


def test_incomplete_response_is_rejected(project_config: ProjectConfig) -> None:
    provider = OpenAIProvider(
        Settings(),
        project_config.pipeline.llm,
        client=FakeClient(response(None, status="incomplete")),
    )
    with pytest.raises(LlmIncompleteError, match="tronquée"):
        provider.summarize_news(title="Titre", content="Contenu", source_url="https://example.com")


def test_refusal_is_rejected(project_config: ProjectConfig) -> None:
    provider = OpenAIProvider(
        Settings(),
        project_config.pipeline.llm,
        client=FakeClient(response(None, content_type="refusal")),
    )
    with pytest.raises(LlmRefusalError, match="refusé"):
        provider.summarize_news(title="Titre", content="Contenu", source_url="https://example.com")


def test_missing_parsed_output_is_rejected(project_config: ProjectConfig) -> None:
    provider = OpenAIProvider(
        Settings(), project_config.pipeline.llm, client=FakeClient(response(None))
    )
    with pytest.raises(LlmIncompleteError, match="absente"):
        provider.summarize_news(title="Titre", content="Contenu", source_url="https://example.com")


def test_additional_pydantic_validation_rejects_wrong_shape(
    project_config: ProjectConfig,
) -> None:
    provider = OpenAIProvider(
        Settings(),
        project_config.pipeline.llm,
        client=FakeClient(response({"summary": "incomplet"})),
    )
    with pytest.raises(LlmError, match="non conforme"):
        provider.summarize_news(title="Titre", content="Contenu", source_url="https://example.com")


def test_sdk_parse_validation_error_is_a_controlled_incomplete_response(
    project_config: ProjectConfig,
) -> None:
    with pytest.raises(ValidationError) as captured:
        NewsAnalysis.model_validate({"summary": "incomplet"})
    provider = OpenAIProvider(
        Settings(),
        project_config.pipeline.llm,
        client=FakeClient(captured.value),
    )

    with pytest.raises(LlmIncompleteError, match="tronquée ou illisible"):
        provider.summarize_news(
            title="Titre",
            content="Contenu",
            source_url="https://example.com",
        )


def test_unsupported_structured_outputs_are_explicit(project_config: ProjectConfig) -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    error = openai.BadRequestError(
        "Model does not support structured text_format",
        response=httpx.Response(400, request=request),
        body=None,
    )
    provider = OpenAIProvider(Settings(), project_config.pipeline.llm, client=FakeClient(error))
    with pytest.raises(StructuredOutputUnsupportedError, match="non pris en charge"):
        provider.summarize_news(title="Titre", content="Contenu", source_url="https://example.com")


def test_complex_tasks_use_terra(project_config: ProjectConfig) -> None:
    client = FakeClient(response(valid_analysis()))
    provider = OpenAIProvider(Settings(), project_config.pipeline.llm, client=client)
    provider.extract_structured(
        content="tableau complexe",
        output_model=NewsAnalysis,
        task_name="complex_table",
        complex_task=True,
    )
    assert client.responses.calls[0]["model"] == "gpt-5.6-terra"
    assert client.responses.calls[0]["reasoning"] == {"effort": "none"}
