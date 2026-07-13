from pathlib import Path

import pytest

import vigie_pipeline.acquire as acquire_module
from vigie_pipeline.acquire import acquire_source, publication_date
from vigie_pipeline.config import ProjectConfig
from vigie_pipeline.fetch import FetchResult
from vigie_pipeline.models import VigieDataset
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
    acquisition = acquire_source(dataset, source, Settings(anthropic_api_key=None), project_config)
    assert len(acquisition.observations) == 4
    assert {item.period.period_id for item in acquisition.observations} == {"2026-T1"}
    assert acquisition.failures == []
    assert {item.source.published_at.isoformat() for item in acquisition.observations} == {
        "2026-05-09"
    }


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
        lambda **_: FixtureFetcher(index, {"q2-2032-quarterly": metrics}),
    )
    source = next(item for item in project_config.sources if item.id == "gwo-results")
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
