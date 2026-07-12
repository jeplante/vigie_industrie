from pathlib import Path

from vigie_pipeline.discovery import discover_documents
from vigie_pipeline.fetch import FetchResult
from vigie_pipeline.sources.manulife import ManulifeAdapter


def _result(path: Path) -> FetchResult:
    return FetchResult(
        url="https://example.com/investors/",
        content=path.read_bytes(),
        content_type="text/html",
        etag='"abc"',
        last_modified="Fri, 11 Jul 2026 10:00:00 GMT",
    )


def test_discovers_new_pdf_and_ignores_unrelated_link(repository_root: Path) -> None:
    documents = discover_documents(
        "test", _result(repository_root / "pipeline/tests/fixtures/source-index.html")
    )
    assert [str(item.canonical_url) for item in documents] == [
        "https://example.com/docs/results-2026-03-31.pdf"
    ]
    assert documents[0].published_at.isoformat() == "2026-03-31"


def test_discovery_survives_modified_html(repository_root: Path) -> None:
    documents = discover_documents(
        "test", _result(repository_root / "pipeline/tests/fixtures/source-index-modified.html")
    )
    assert len(documents) == 1
    assert documents[0].title == "Résultats annuels 2025"


def test_company_adapter_extracts_deterministic_metrics(repository_root: Path) -> None:
    html = (repository_root / "pipeline/tests/fixtures/metrics.html").read_text(encoding="utf-8")
    candidates = ManulifeAdapter().extract_metrics(html)
    assert {item.metric_id for item in candidates} == {"core_eps", "core_earnings", "licat_ratio"}
