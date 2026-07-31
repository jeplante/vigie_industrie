from pathlib import Path
from typing import TypeVar

import pytest
from pydantic import BaseModel

import vigie_pipeline.news as news_module
from vigie_pipeline.config import ProjectConfig
from vigie_pipeline.exceptions import LlmError
from vigie_pipeline.fetch import FetchResult
from vigie_pipeline.llm.base import NewsAnalysis
from vigie_pipeline.models import VigieDataset
from vigie_pipeline.news import (
    acquire_news,
    canonicalize_url,
    discover_news_documents,
    fetch_news_index,
)
from vigie_pipeline.settings import Settings

T = TypeVar("T", bound=BaseModel)


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    def summarize_news(self, *, title: str, content: str, source_url: str) -> NewsAnalysis:
        self.calls += 1
        assert "responsible AI" in title
        assert "governance" in content
        assert "utm_" not in source_url
        return NewsAnalysis(
            summary="Sun Life lance une initiative canadienne de gouvernance responsable de l’IA.",
            categories=["artificial_intelligence", "risk"],
            importance="high",
            themes=["gouvernance de l’IA", "gestion des risques"],
            company_ids=["SLF", "UNKNOWN"],
            confidence=0.94,
            warnings=[],
        )

    def extract_structured(
        self,
        *,
        content: str,
        output_model: type[T],
        task_name: str,
        complex_task: bool = False,
    ) -> T:
        raise AssertionError("L’extraction financière ne doit pas être appelée")


class FakeFetcher:
    def __init__(self, index: bytes, article: bytes) -> None:
        self.index = index
        self.article = article

    def __enter__(self) -> "FakeFetcher":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def fetch(self, url: str) -> FetchResult:
        is_article = "official-ai-news" in url
        return FetchResult(
            url=url,
            content=self.article if is_article else self.index,
            content_type="text/html",
            etag=None,
            last_modified=None,
        )


class FailingProvider(FakeProvider):
    def summarize_news(self, *, title: str, content: str, source_url: str) -> NewsAnalysis:
        self.calls += 1
        raise LlmError("OpenAI indisponible")


class IaIndexFetcher:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def fetch(self, url: str) -> FetchResult:
        self.urls.append(url)
        if "getSallePresseMois" in url:
            content = b"""
                <table><tr><td><time>July 21, 2026</time>
                <a href="/newsroom/2026/july/quarterly-results-date">
                iA Financial Group announces its results date</a></td></tr></table>
            """
        else:
            content = b"""
                <div class="salle-presse">
                  <div class="tuile-contenu" id="2025" data-item-id="older"></div>
                  <div class="tuile-contenu" id="2026" data-item-id="latest"></div>
                </div>
            """
        return FetchResult(
            url=url,
            content=content,
            content_type="text/html",
            etag=None,
            last_modified=None,
        )


def test_ia_news_fetches_latest_year_fragment(project_config: ProjectConfig) -> None:
    source = next(item for item in project_config.sources if item.id == "iag-official-news")
    fetcher = IaIndexFetcher()
    index = fetch_news_index(source, fetcher)  # type: ignore[arg-type]
    documents = discover_news_documents(source, index)

    assert "anneeItemId=latest" in fetcher.urls[-1]
    assert "sc_lang=fr" in fetcher.urls[-1]
    assert len(documents) == 1
    assert str(documents[0].canonical_url) == (
        "https://ia.ca/newsroom/2026/july/quarterly-results-date"
    )
    assert documents[0].published_at is not None
    assert documents[0].published_at.isoformat() == "2026-07-21"


def test_cision_abbreviated_date_is_used_instead_of_a_future_event_date(
    project_config: ProjectConfig,
) -> None:
    source = next(item for item in project_config.sources if item.id == "mfc-official-news")
    index = FetchResult(
        url=str(source.url),
        content=b"""
          <a href="/news-releases/manulife-results-date-123456789.html">
            <small>Jul 21, 2026, 08:00 ET</small>
            Manulife to release results after markets close on August 5, 2026.
          </a>
        """,
        content_type="text/html",
        etag=None,
        last_modified=None,
    )

    documents = discover_news_documents(source, index)

    assert len(documents) == 1
    assert documents[0].published_at is not None
    assert documents[0].published_at.isoformat() == "2026-07-21"


def test_news_discovery_and_canonicalization(
    repository_root: Path, project_config: ProjectConfig
) -> None:
    source = next(item for item in project_config.sources if item.id == "slf-official-news")
    index = FetchResult(
        url=str(source.url),
        content=(repository_root / "pipeline/tests/fixtures/news-index.html").read_bytes(),
        content_type="text/html",
        etag=None,
        last_modified=None,
    )
    documents = discover_news_documents(source, index)
    assert len(documents) == 1
    assert documents[0].published_at is not None
    assert documents[0].published_at.isoformat() == "2026-07-07"
    assert canonicalize_url("https://EXAMPLE.com/a/?utm_source=x&id=2#top") == (
        "https://example.com/a?id=2"
    )


def test_official_news_is_summarized_and_traced(
    repository_root: Path,
    project_config: ProjectConfig,
    dataset: VigieDataset,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = next(item for item in project_config.sources if item.id == "slf-official-news")
    fake_fetcher = FakeFetcher(
        (repository_root / "pipeline/tests/fixtures/news-index.html").read_bytes(),
        (repository_root / "pipeline/tests/fixtures/news-article.html").read_bytes(),
    )
    monkeypatch.setattr(news_module, "BoundedFetcher", lambda **_: fake_fetcher)
    provider = FakeProvider()
    acquisition = acquire_news(
        dataset,
        source,
        Settings(),
        project_config,
        llm_provider=provider,
    )
    assert len(acquisition.items) == 1
    item = acquisition.items[0]
    assert item.company_ids == ["SLF"]
    assert item.period_id == "2026-T3"
    assert item.period_key == "T3"
    assert item.generated_summary is not None
    assert item.generated_summary.startswith("Sun Life lance")
    assert item.source.source_id == "slf-official-news"
    assert item.source.document_hash is not None
    assert item.quality.extraction_method == "openai"
    assert item.quality.llm_trace is not None
    assert item.quality.llm_trace.model == "gpt-5.6-luna"
    assert provider.calls == 1


def test_existing_canonical_url_is_not_summarized_twice(
    repository_root: Path,
    project_config: ProjectConfig,
    dataset: VigieDataset,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = next(item for item in project_config.sources if item.id == "slf-official-news")
    fake_fetcher = FakeFetcher(
        (repository_root / "pipeline/tests/fixtures/news-index.html").read_bytes(),
        (repository_root / "pipeline/tests/fixtures/news-article.html").read_bytes(),
    )
    monkeypatch.setattr(news_module, "BoundedFetcher", lambda **_: fake_fetcher)
    first = acquire_news(dataset, source, Settings(), project_config, FakeProvider())
    dataset.news.extend(first.items)
    provider = FakeProvider()
    assert acquire_news(dataset, source, Settings(), project_config, provider).items == []
    assert provider.calls == 0


def test_existing_url_with_changed_hash_is_updated(
    repository_root: Path,
    project_config: ProjectConfig,
    dataset: VigieDataset,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = next(item for item in project_config.sources if item.id == "slf-official-news")
    index = (repository_root / "pipeline/tests/fixtures/news-index.html").read_bytes()
    article = (repository_root / "pipeline/tests/fixtures/news-article.html").read_bytes()
    monkeypatch.setattr(news_module, "BoundedFetcher", lambda **_: FakeFetcher(index, article))
    first = acquire_news(dataset, source, Settings(), project_config, FakeProvider())
    dataset.news.extend(first.items)
    changed = article.replace(b"governance", b"updated governance")
    monkeypatch.setattr(news_module, "BoundedFetcher", lambda **_: FakeFetcher(index, changed))
    provider = FakeProvider()
    updated = acquire_news(dataset, source, Settings(), project_config, provider)
    assert len(updated.items) == 1
    assert updated.items[0].id == first.items[0].id
    assert updated.items[0].source.document_hash != first.items[0].source.document_hash
    assert provider.calls == 1


def test_openai_failure_keeps_official_news_valid_with_fallback(
    repository_root: Path,
    project_config: ProjectConfig,
    dataset: VigieDataset,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = next(item for item in project_config.sources if item.id == "slf-official-news")
    fetcher = FakeFetcher(
        (repository_root / "pipeline/tests/fixtures/news-index.html").read_bytes(),
        (repository_root / "pipeline/tests/fixtures/news-article.html").read_bytes(),
    )
    monkeypatch.setattr(news_module, "BoundedFetcher", lambda **_: fetcher)
    acquisition = acquire_news(dataset, source, Settings(), project_config, FailingProvider())
    item = acquisition.items[0]
    assert item.quality.status == "validated"
    assert item.quality.extraction_method == "deterministic_fallback"
    assert item.quality.warnings
    assert item.generated_summary is None
    assert item.original_summary
    assert item.categories == ["other"]
    assert item.importance == "medium"
    assert acquisition.llm_calls == 1
