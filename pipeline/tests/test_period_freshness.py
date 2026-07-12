import json
from copy import deepcopy
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import vigie_pipeline.acquire as acquire_module
from vigie_pipeline.acquire import _previous, acquire_source, infer_period
from vigie_pipeline.config import ProjectConfig
from vigie_pipeline.exceptions import DocumentNotIngestedError
from vigie_pipeline.fetch import FetchResult
from vigie_pipeline.freshness import SourceCheck, build_company_freshness, freshness_issues
from vigie_pipeline.merge import merge_datasets
from vigie_pipeline.models import Period, VigieDataset
from vigie_pipeline.settings import Settings


class _ExtractionFailureFetcher:
    def __init__(self, index: bytes, document: bytes) -> None:
        self.index = index
        self.document = document

    def __enter__(self) -> "_ExtractionFailureFetcher":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def fetch(self, url: str) -> FetchResult:
        return FetchResult(
            url=url,
            content=self.document if "/docs/" in url else self.index,
            content_type="text/html",
            etag=None,
            last_modified=None,
        )


def _fixture(repository_root: Path) -> dict[str, object]:
    return json.loads(
        (repository_root / "pipeline/tests/fixtures/multi-year-periods.json").read_text(
            encoding="utf-8"
        )
    )


def _multi_year_dataset(dataset: VigieDataset, repository_root: Path) -> VigieDataset:
    candidate = deepcopy(dataset)
    fixture = _fixture(repository_root)
    periods = {
        period.period_id: period
        for payload in fixture["periods"]  # type: ignore[index]
        if (period := Period.model_validate(payload))
    }
    candidate.periods = list(periods.values())
    for period_id in ("2026-T1", "2026-T2"):
        period = periods[period_id]
        base = next(
            item
            for item in dataset.observations
            if item.company_id == "MFC"
            and item.period.period_key == period.period_key
            and item.metric_id == "core_eps"
        )
        observation = deepcopy(base)
        observation.id = f"MFC-{period.period_id}-core_eps"
        observation.period = period
        observation.value += 1
        observation.comparison.period_id = f"2025-{period.period_key}"
        observation.comparison.period_label = f"{period.period_key} 2025"
        candidate.observations.append(observation)
    return candidate


def test_future_period_ids_are_composite_and_not_hard_coded() -> None:
    period = infer_period("Résultats du deuxième trimestre 2032")
    assert period is not None
    assert period.period_id == "2032-T2"
    assert period.period_key == "T2"
    assert period.year == 2032


def test_2025_is_preserved_when_2026_is_merged(
    dataset: VigieDataset, repository_root: Path
) -> None:
    candidate = _multi_year_dataset(dataset, repository_root)
    only_new = deepcopy(candidate)
    only_new.periods = [period for period in candidate.periods if period.year == 2026]
    only_new.observations = [item for item in candidate.observations if item.period.year == 2026]
    merged = merge_datasets(dataset, only_new)
    ids = {period.period_id for period in merged.periods}
    assert {"2025-T1", "2025-T2", "2025-T3", "2025-AN"} <= ids
    assert {"2026-T1", "2026-T2"} <= ids
    assert len([item for item in merged.observations if item.id == "MFC-2025-T1-core_eps"]) == 1


def test_comparison_uses_same_period_key_in_previous_year(
    dataset: VigieDataset, repository_root: Path
) -> None:
    candidate = _multi_year_dataset(dataset, repository_root)
    period = next(item for item in candidate.periods if item.period_id == "2026-T2")
    previous = _previous(candidate, "MFC", period, "core_eps")
    assert previous is not None
    assert previous.period.period_id == "2025-T2"
    assert previous.period.period_key == period.period_key


def test_company_freshness_distinguishes_current_stale_and_unknown(
    dataset: VigieDataset, repository_root: Path
) -> None:
    candidate = _multi_year_dataset(dataset, repository_root)
    periods = {period.period_id: period for period in candidate.periods}
    checked_at = datetime(2026, 7, 12, tzinfo=UTC)
    checks = {
        "MFC": SourceCheck("MFC", "mfc-results", checked_at, periods["2026-T2"], True),
        "SLF": SourceCheck("SLF", "slf-results", checked_at, periods["2026-T1"], True),
        "GWO": SourceCheck("GWO", "gwo-results", checked_at, None, False),
    }
    freshness = {item.company_id: item for item in build_company_freshness(candidate, checks)}
    assert freshness["MFC"].freshness_status == "current"
    assert freshness["MFC"].latest_published_period_id == "2026-T2"
    assert freshness["SLF"].freshness_status == "stale"
    assert freshness["SLF"].latest_available_period_id == "2026-T1"
    assert freshness["SLF"].latest_published_period_id == "2025-AN"
    assert freshness["GWO"].freshness_status == "unknown"
    assert freshness["GWO"].latest_published_period_id == "2025-AN"
    assert freshness["IAG"].freshness_status == "unknown"
    issues = freshness_issues(candidate, checks)
    assert [(issue.code, issue.source_id) for issue in issues] == [
        ("newer_document_not_ingested", "slf-results")
    ]


def test_discovered_2026_document_with_failed_extraction_is_stale(
    dataset: VigieDataset,
    repository_root: Path,
    project_config: ProjectConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetcher = _ExtractionFailureFetcher(
        (repository_root / "pipeline/tests/fixtures/source-index.html").read_bytes(),
        (repository_root / "pipeline/tests/fixtures/metrics.html").read_bytes(),
    )
    monkeypatch.setattr(acquire_module, "BoundedFetcher", lambda **_: fetcher)
    source = next(item for item in project_config.sources if item.id == "mfc-results")
    with pytest.raises(DocumentNotIngestedError) as captured:
        acquire_source(
            dataset,
            source,
            Settings(anthropic_api_key=None),
            project_config,
        )
    failed_period = captured.value.period
    assert isinstance(failed_period, Period)
    assert failed_period.period_id == "2026-T1"
    check = SourceCheck(
        company_id="MFC",
        source_id=source.id,
        checked_at=datetime(2026, 7, 12, tzinfo=UTC),
        latest_available_period=failed_period,
        verified=True,
    )
    assert build_company_freshness(dataset, {"MFC": check})[0].freshness_status == "stale"
    assert freshness_issues(dataset, {"MFC": check})[0].code == ("newer_document_not_ingested")


def test_news_period_ids_do_not_collide_between_years(dataset: VigieDataset) -> None:
    first = deepcopy(next(item for item in dataset.news if item.period_key == "T1"))
    second = deepcopy(first)
    second.id = f"{first.id}-2026"
    second.period_id = "2026-T1"
    second.published_at = date(2026, 2, 1)
    assert {item.period_id for item in (first, second)} == {"2025-T1", "2026-T1"}
