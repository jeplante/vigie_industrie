"""Fournisseurs LLM substituables."""

from vigie_pipeline.llm.anthropic_provider import AnthropicProvider
from vigie_pipeline.llm.no_llm_provider import NoLlmProvider

__all__ = ["AnthropicProvider", "NoLlmProvider"]
