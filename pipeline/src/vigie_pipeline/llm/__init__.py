"""Fournisseurs LLM substituables."""

from vigie_pipeline.llm.no_llm_provider import NoLlmProvider
from vigie_pipeline.llm.openai_provider import OpenAIProvider

__all__ = ["NoLlmProvider", "OpenAIProvider"]
