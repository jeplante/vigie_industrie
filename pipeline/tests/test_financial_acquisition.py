from datetime import date
from pathlib import Path

import pytest

import vigie_pipeline.acquire as acquire_module
from vigie_pipeline.acquire import (
    acquire_source,
    historical_periods,
    infer_period,
    publication_date,
)
from vigie_pipeline.config import ProjectConfig
from vigie_pipeline.fetch import FetchResult
from vigie_pipeline.models import Period, VigieDataset
from vigie_pipeline.settings import Settings


class FixtureFetcher:
    def __init__(self, index: bytes, documents: dict[str, bytes]) -> None:
        self.index = index
        self.documents = documents

    def __enter__(self) -> "FixtureFetcher":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def fetch(self, url: str) -> FetchResult:
        content = next(
            (payload for marker, payload in self.documents.items() if marker in url),
            self.index,
        )
        return FetchResult(
            url=url,
            content=content,
            content_type="text/html",
            etag=None,
            last_modified=None,
        )


def test_explicit_document_date_wins_over_period_end() -> None:
    result = FetchResult(
        url="https://example.com/report",
        content=(
            b"For the period ended March 31, 2026. "
            b"Management's Discussion and Analysis DATED: MAY 6, 2026."
        ),
        content_type="text/html",
        etag=None,
        last_modified=None,
    )
    parsed = publication_date(result)
    assert parsed is not None
    assert parsed.isoformat() == "2026-05-06"


@pytest.mark.parametrize(
    ("slug", "period_id"),
    [
        ("manulife-reports-first-quarter-2026-results.html", "2026-T1"),
        ("sun-life-reports-second-quarter-2027-results.html", "2027-T2"),
        ("company-reports-third-quarter-2028-results.html", "2028-T3"),
        ("company-reports-fourth-quarter-and-full-year-2029-results.html", "2029-AN"),
        ("pa-e-q124-earnings.pdf", "2024-T1"),
        ("pa-e-q422-earnings.pdf", "2022-AN"),
        ("manulife-reports-1q23-net-income.html", "2023-T1"),
        ("manulife-reports-3q22-net-income.html", "2022-T3"),
        ("manulife-reports-2022-net-income.html", "2022-AN"),
        (
            "Feb 11 2026 Sun Life Reports Fourth Quarter and Full Year 2025 Results",
            "2025-AN",
        ),
    ],
)
def test_infer_period_accepts_hyphenated_release_slugs(
    slug: str,
    period_id: str,
) -> None:
    period = infer_period(slug)
    assert period is not None
    assert period.period_id == period_id


def test_historical_periods_cover_five_years_without_future_quarters() -> None:
    latest = Period(
        period_id="2026-T1",
        period_key="T1",
        type="quarter",
        year=2026,
        quarter=1,
        end_date=date(2026, 3, 31),
        label="T1 2026",
    )

    periods = historical_periods(latest, 5)

    assert periods[0].period_id == "2022-T1"
    assert periods[-1].period_id == "2026-T1"
    assert len(periods) == 17
    assert "2026-T2" not in {period.period_id for period in periods}


def test_annual_information_form_is_not_a_financial_results_document() -> None:
    document = acquire_module.DiscoveredDocument(
        source_id="iag-results",
        canonical_url=("https://ia.ca/reports/annual/2026/ann-2025-annual-information-form.pdf"),
        title="2025 Annual Information Form",
        content_type="application/pdf",
        document_kind="downloadable_report",
        is_published=True,
    )

    assert acquire_module._relevant_financial_document(document) is False


def test_index_metrics_are_acquired_and_future_conference_is_excluded(
    repository_root: Path,
    project_config: ProjectConfig,
    dataset: VigieDataset,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = (repository_root / "pipeline/tests/fixtures/financial-index-metrics.html").read_bytes()
    monkeypatch.setattr(
        acquire_module,
        "BoundedFetcher",
        lambda **_: FixtureFetcher(index, {}),
    )
    source = next(item for item in project_config.sources if item.id == "mfc-results")
    source = source.model_copy(update={"historical_document_urls": []})
    acquisition = acquire_source(dataset, source, Settings(anthropic_api_key=None), project_config)
    assert len(acquisition.observations) == 4
    assert {item.period.period_id for item in acquisition.observations} == {"2026-T1"}
    assert {item.source.published_at.isoformat() for item in acquisition.observations} == {
        "2026-05-08"
    }
    assert {item.document_kind for item in acquisition.documents} >= {
        "index_metrics",
        "future_event",
    }
    assert {item.period_id for item in acquisition.discovered_periods} == {"2026-T1"}


def test_old_invalid_document_does_not_cancel_new_valid_document(
    repository_root: Path,
    project_config: ProjectConfig,
    dataset: VigieDataset,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_dir = repository_root / "pipeline/tests/fixtures"
    fetcher = FixtureFetcher(
        (fixture_dir / "financial-index-mixed.html").read_bytes(),
        {
            "q1-2026": (fixture_dir / "financial-new-valid.html").read_bytes(),
            "annual-2024": (fixture_dir / "financial-old-invalid.html").read_bytes(),
        },
    )
    monkeypatch.setattr(acquire_module, "BoundedFetcher", lambda **_: fetcher)
    source = next(item for item in project_config.sources if item.id == "mfc-results")
    source = source.model_copy(update={"historical_document_urls": []})
    acquisition = acquire_source(dataset, source, Settings(anthropic_api_key=None), project_config)
    assert len(acquisition.observations) == 4
    assert {item.period.period_id for item in acquisition.observations} == {"2026-T1"}
    assert {item.period.period_id for item in acquisition.failures} == {"2024-AN"}
    assert {item.source.published_at.isoformat() for item in acquisition.observations} == {
        "2026-05-09"
    }


def test_new_period_does_not_reingest_latest_period_from_an_unknown_url(
    repository_root: Path,
    project_config: ProjectConfig,
    dataset: VigieDataset,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = b"""
    <html><body>
      <a href="/results/q1-2026">First quarter 2026 results</a>
      <a href="/results/fourth-quarter-and-full-year-2025-results">
        Fourth quarter and full year 2025 results
      </a>
    </body></html>
    """
    fixture_dir = repository_root / "pipeline/tests/fixtures"
    fetcher = FixtureFetcher(
        index,
        {
            "q1-2026": (fixture_dir / "financial-new-valid.html").read_bytes(),
            "full-year-2025": (fixture_dir / "financial-old-invalid.html").read_bytes(),
        },
    )
    monkeypatch.setattr(acquire_module, "BoundedFetcher", lambda **_: fetcher)
    source = next(item for item in project_config.sources if item.id == "mfc-results")
    source = source.model_copy(update={"historical_document_urls": []})

    acquisition = acquire_source(dataset, source, Settings(), project_config)

    assert {item.period.period_id for item in acquisition.observations} == {"2026-T1"}
    assert acquisition.failures == []
    assert all("full-year-2025" not in str(item.canonical_url) for item in acquisition.documents)


def test_document_template_tracks_discovered_year_and_quarter(
    project_config: ProjectConfig,
    dataset: VigieDataset,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = b"""
    <html><head><title>2nd quarter 2032 results</title></head>
    <body><h1>2nd quarter 2032 results</h1>
    <p>Great-West Lifeco released its second quarter 2032 results on August 5, 2032.</p>
    </body></html>
    """
    metrics = b"""
    Management's Discussion and Analysis DATED: AUGUST 5, 2032.
    Base EPS was $1.50. Base earnings were $1,400 million.
    The LICAT ratio was 131%. Total client assets reached $3.8 trillion.
    """
    monkeypatch.setattr(
        acquire_module,
        "BoundedFetcher",
        lambda **_: FixtureFetcher(
            index,
            {
                "q1-2032-quarterly": b"Document sans mesures.",
                "q2-2032-quarterly": metrics,
            },
        ),
    )
    source = next(item for item in project_config.sources if item.id == "gwo-results")
    project_config.pipeline.financial_history_years = 1
    acquisition = acquire_source(dataset, source, Settings(), project_config)
    assert {item.period.period_id for item in acquisition.observations} == {"2032-T2"}
    assert {str(item.source.url) for item in acquisition.observations} == {
        "https://www.greatwestlifeco.com/content/dam/lifeco/documents/"
        "investor-relations/reports/2032/q2/lifeco-q2-2032-quarterly-report-"
        "to-shareholders-en.pdf"
    }
    assert {item.source.published_at.isoformat() for item in acquisition.observations} == {
        "2032-08-05"
    }


def test_sun_life_financial_highlights_page_is_a_deterministic_source(
    project_config: ProjectConfig,
    dataset: VigieDataset,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = b"""
    <html><head><title>Q1 2026 financial results</title></head>
    <body>
      <h1>Financial highlights Q1 2026</h1>
      <p>Diluted underlying EPS 1.89 $</p>
      <p>Underlying net income 1 050 M$</p>
      <p>SLF Inc. LICAT ratio 143%</p>
      <p>Assets under management 1 575 G$</p>
      <p>Published May 6, 2026.</p>
    </body></html>
    """
    monkeypatch.setattr(
        acquire_module,
        "BoundedFetcher",
        lambda **_: FixtureFetcher(index, {}),
    )
    source = next(item for item in project_config.sources if item.id == "slf-results")
    source = source.model_copy(update={"historical_document_urls": []})
    assert str(source.url) == ("https://www.newswire.ca/search/news/?keyword=Sun%20Life%20Reports")

    acquisition = acquire_source(
        dataset,
        source,
        Settings(anthropic_api_key=None),
        project_config,
    )

    assert {item.metric_id for item in acquisition.observations} == {
        "core_eps",
        "net_income",
        "licat_ratio",
        "assets_under_management",
    }
    assert {item.period.period_id for item in acquisition.observations} == {"2026-T1"}
