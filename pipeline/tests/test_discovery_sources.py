from pathlib import Path

from vigie_pipeline.discovery import discover_documents
from vigie_pipeline.fetch import FetchResult
from vigie_pipeline.sources.great_west import GreatWestAdapter
from vigie_pipeline.sources.ia import IaAdapter
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
    assert documents[0].published_at is None


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


def test_ia_adapter_prefers_values_over_deltas_and_normalizes_millions() -> None:
    content = """
    Core EPS of $3.25 (+12% YoY).
    Core earnings (in millions) 298 273 9%.
    The solvency ratio was 134% as at March 31, 2026.
    Total assets under management and assets under administration up 31%
    over the last 12 months to exceed $346 billion.
    """
    candidates = {item.metric_id: item for item in IaAdapter().extract_metrics(content)}
    assert candidates["core_eps"].value == 3.25
    assert candidates["core_earnings"].value == 0.298
    assert candidates["solvency_ratio"].value == 134
    assert candidates["assets_under_administration"].value == 346


def test_great_west_adapter_normalizes_report_units() -> None:
    content = """
    Base EPS was $1.37 compared with $1.11.
    Base earnings were $1,239 million, up 20%.
    The LICAT ratio was 135%.
    Total client assets reached $3.4 trillion.
    """
    candidates = {item.metric_id: item for item in GreatWestAdapter().extract_metrics(content)}
    assert candidates["core_eps"].value == 1.37
    assert candidates["core_earnings"].value == 1.239
    assert candidates["licat_ratio"].value == 135
    assert candidates["total_client_assets"].value == 3.4
