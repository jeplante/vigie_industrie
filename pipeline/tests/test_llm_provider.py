from types import SimpleNamespace

import pytest

from vigie_pipeline.exceptions import ConfigurationError, LlmError
from vigie_pipeline.llm.anthropic_provider import AnthropicProvider
from vigie_pipeline.llm.base import NewsAnalysis
from vigie_pipeline.settings import Settings


class FakeMessages:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(text=self.text)],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )


class FakeClient:
    def __init__(self, text: str) -> None:
        self.messages = FakeMessages(text)


def test_missing_api_key_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider(Settings(anthropic_api_key=None))


def test_structured_response_is_validated() -> None:
    raw = (
        '{"summary":"Résumé","categories":["financial_results"],'
        '"importance":"high","themes":["BPA"],"confidence":0.9,"warnings":[]}'
    )
    client = FakeClient(raw)
    provider = AnthropicProvider(Settings(), client=client)
    result = provider.summarize_news(
        title="Titre", content="Contenu", source_url="https://example.com"
    )
    assert result == NewsAnalysis.model_validate_json(raw)
    assert client.messages.calls[0]["temperature"] == 0


def test_nonconforming_llm_response_is_rejected() -> None:
    provider = AnthropicProvider(Settings(), client=FakeClient("pas du JSON"))
    with pytest.raises(LlmError, match="non conforme"):
        provider.summarize_news(title="Titre", content="Contenu", source_url="https://example.com")
