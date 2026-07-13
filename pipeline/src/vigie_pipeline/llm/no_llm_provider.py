"""Mode explicite sans LLM, utilisé hors ligne et dans les tests."""

from vigie_pipeline.exceptions import LlmError
from vigie_pipeline.llm.base import NewsAnalysis, T


class NoLlmProvider:
    def extract_structured(
        self,
        *,
        content: str,
        output_model: type[T],
        task_name: str,
        complex_task: bool = False,
    ) -> T:
        del content, output_model, complex_task
        raise LlmError(f"LLM désactivé pour la tâche {task_name}")

    def summarize_news(self, *, title: str, content: str, source_url: str) -> NewsAnalysis:
        del title, content, source_url
        raise LlmError("LLM désactivé")
