import json
from copy import deepcopy
from pathlib import Path

import pytest

import vigie_pipeline.cli as cli_module
from vigie_pipeline.acquire import FinancialAcquisition
from vigie_pipeline.cli import command_publish, command_refresh
from vigie_pipeline.config import ProjectConfig
from vigie_pipeline.exceptions import FetchError, ValidationFailure
from vigie_pipeline.freshness import SourceCheck
from vigie_pipeline.models import (
    DatasetManifest,
    DiscoveredDocument,
    Period,
    QualityReport,
    VigieDataset,
)
from vigie_pipeline.news import NewsAcquisition
from vigie_pipeline.publish import build_manifest
from vigie_pipeline.quality import build_quality_report
from vigie_pipeline.settings import Settings


def test_quality_report_statuses() -> None:
    assert build_quality_report().status == "success"
    assert build_quality_report(sources_checked=2, sources_succeeded=1).status == "partial"


def test_last_known_good_is_preserved(
    dataset: VigieDataset, project_config: ProjectConfig, tmp_path: Path
) -> None:
    published = tmp_path / "data/published"
    generated = tmp_path / "data/generated"
    published.mkdir(parents=True)
    generated.mkdir(parents=True)
    good_payload = dataset.model_dump(mode="json", by_alias=True)
    (published / "vigie.json").write_text(json.dumps(good_payload), encoding="utf-8")
    invalid = deepcopy(dataset)
    invalid.observations[0].unit = "INVALID"
    (generated / "vigie.json").write_text(
        json.dumps(invalid.model_dump(mode="json", by_alias=True)), encoding="utf-8"
    )
    settings = Settings(root_dir=tmp_path)
    with pytest.raises(ValidationFailure):
        command_publish(settings, project_config)
    preserved = VigieDataset.model_validate_json(
        (published / "vigie.json").read_text(encoding="utf-8")
    )
    assert preserved.observations[0].unit != "INVALID"
    assert (generated / "quality-report.json").exists()


def test_offline_refresh_uses_seed_without_network(
    dataset: VigieDataset, project_config: ProjectConfig, tmp_path: Path
) -> None:
    seed = tmp_path / "data/seed"
    manual = tmp_path / "data/manual"
    seed.mkdir(parents=True)
    manual.mkdir(parents=True)
    (seed / "vigie-v1.json").write_text(
        json.dumps(dataset.model_dump(mode="json", by_alias=True)), encoding="utf-8"
    )
    (manual / "overrides.yaml").write_text("overrides: []\n", encoding="utf-8")
    settings = Settings(root_dir=tmp_path)
    assert command_refresh(settings, project_config, None, offline=True) == 0
    assert (tmp_path / "data/published/vigie.json").exists()
    assert (tmp_path / "app/public/data/manifest.json").exists()
    manifest = DatasetManifest.model_validate_json(
        (tmp_path / "data/published/manifest.json").read_text(encoding="utf-8")
    )
    report = QualityReport.model_validate_json(
        (tmp_path / "data/published/quality-report.json").read_text(encoding="utf-8")
    )
    assert manifest.mode == report.mode == "offline"
    assert manifest.last_attempt_at == report.generated_at
    assert manifest.last_successful_refresh == dataset.generated_at
    assert manifest.last_attempt_at != manifest.last_successful_refresh
    assert report.sources_checked == report.sources_succeeded == 0
    assert all(item.freshness_status == "unknown" for item in manifest.company_freshness)
    assert all(item.latest_available_period_id is None for item in manifest.company_freshness)
    assert all(item.latest_source_check_at is None for item in manifest.company_freshness)


def test_source_403_is_non_blocking_and_preserves_last_known_good(
    dataset: VigieDataset,
    project_config: ProjectConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published = tmp_path / "data/published"
    manual = tmp_path / "data/manual"
    published.mkdir(parents=True)
    manual.mkdir(parents=True)
    original = json.dumps(dataset.model_dump(mode="json", by_alias=True))
    (published / "vigie.json").write_text(original, encoding="utf-8")
    (manual / "overrides.yaml").write_text("overrides: []\n", encoding="utf-8")
    previous_manifest = build_manifest(
        dataset,
        dataset.generated_at,
        mode="live",
        financial_refresh_succeeded=True,
    )
    (published / "manifest.json").write_text(
        json.dumps(previous_manifest.model_dump(mode="json", by_alias=True)),
        encoding="utf-8",
    )

    def blocked(*_: object, **__: object) -> list[object]:
        raise FetchError("Erreur HTTP 403 pour Manuvie")

    monkeypatch.setattr(cli_module, "acquire_source", blocked)
    monkeypatch.setattr(cli_module, "acquire_news", blocked)
    settings = Settings(root_dir=tmp_path)
    assert command_refresh(settings, project_config, "MFC", offline=False) == 0
    refreshed = VigieDataset.model_validate_json(
        (published / "vigie.json").read_text(encoding="utf-8")
    )
    assert [item.id for item in refreshed.observations] == [
        item.id for item in dataset.observations
    ]
    report = json.loads((published / "quality-report.json").read_text(encoding="utf-8"))
    assert report["status"] == "partial"
    assert {warning["sourceId"] for warning in report["warnings"]} == {
        "mfc-results",
        "mfc-official-news",
    }
    manifest = json.loads((published / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["lastSuccessfulRefresh"] == dataset.generated_at.isoformat().replace(
        "+00:00", "Z"
    )
    assert manifest["lastAttemptAt"] != manifest["lastSuccessfulRefresh"]
    mfc = next(item for item in manifest["companyFreshness"] if item["companyId"] == "MFC")
    assert mfc["freshnessStatus"] == "unknown"


def test_official_news_sources_are_optional(project_config: ProjectConfig) -> None:
    news_sources = [
        source for source in project_config.sources if source.content_category == "official_news"
    ]
    assert news_sources
    assert all(source.required is False for source in news_sources)


def test_empty_financial_and_news_sources_are_non_blocking_warnings(
    dataset: VigieDataset,
    project_config: ProjectConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published = tmp_path / "data/published"
    manual = tmp_path / "data/manual"
    published.mkdir(parents=True)
    manual.mkdir(parents=True)
    (published / "vigie.json").write_text(
        json.dumps(dataset.model_dump(mode="json", by_alias=True)), encoding="utf-8"
    )
    (manual / "overrides.yaml").write_text("overrides: []\n", encoding="utf-8")

    def empty_financial(*_: object, **__: object) -> FinancialAcquisition:
        return FinancialAcquisition([], [], [], [], 0, dataset.generated_at)

    def empty_news(*_: object, **__: object) -> NewsAcquisition:
        return NewsAcquisition([], [], [], 0)

    monkeypatch.setattr(cli_module, "acquire_source", empty_financial)
    monkeypatch.setattr(cli_module, "acquire_news", empty_news)
    assert command_refresh(Settings(root_dir=tmp_path), project_config, "MFC", False) == 0
    report = QualityReport.model_validate_json(
        (published / "quality-report.json").read_text(encoding="utf-8")
    )
    results = {item.source_id: item for item in report.source_results}
    assert results["mfc-results"].status == "warning"
    assert results["mfc-official-news"].status == "warning"
    assert report.sources_succeeded == 0
    assert report.sources_failed == 2
    assert {(warning.code, warning.source_id) for warning in report.warnings} >= {
        ("no_documents_discovered", "mfc-results"),
        ("no_documents_discovered", "mfc-official-news"),
    }
    manifest = DatasetManifest.model_validate_json(
        (published / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest.last_successful_refresh == dataset.generated_at
    assert manifest.last_attempt_at is not None
    assert manifest.last_attempt_at > manifest.last_successful_refresh


def test_partial_refresh_preserves_other_company_freshness(
    dataset: VigieDataset,
    project_config: ProjectConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published = tmp_path / "data/published"
    manual = tmp_path / "data/manual"
    published.mkdir(parents=True)
    manual.mkdir(parents=True)
    (manual / "overrides.yaml").write_text("overrides: []\n", encoding="utf-8")
    (published / "vigie.json").write_text(
        json.dumps(dataset.model_dump(mode="json", by_alias=True)), encoding="utf-8"
    )
    annual = next(period for period in dataset.periods if period.period_id == "2025-AN")
    checks = {
        company.id: SourceCheck(
            company_id=company.id,
            source_id=f"{company.id.lower()}-results",
            checked_at=dataset.generated_at,
            latest_available_period=annual,
            verified=True,
        )
        for company in dataset.companies
    }
    prior = build_manifest(
        dataset,
        dataset.generated_at,
        checks,
        mode="live",
    )
    (published / "manifest.json").write_text(
        json.dumps(prior.model_dump(mode="json", by_alias=True)), encoding="utf-8"
    )

    def blocked(*_: object, **__: object) -> list[object]:
        raise FetchError("Source MFC inaccessible")

    monkeypatch.setattr(cli_module, "acquire_source", blocked)
    monkeypatch.setattr(cli_module, "acquire_news", blocked)
    assert command_refresh(Settings(root_dir=tmp_path), project_config, "MFC", False) == 0
    refreshed = DatasetManifest.model_validate_json(
        (published / "manifest.json").read_text(encoding="utf-8")
    )
    by_company = {item.company_id: item for item in refreshed.company_freshness}
    assert by_company["MFC"].freshness_status == "unknown"
    assert by_company["SLF"].freshness_status == "current"
    assert by_company["SLF"].latest_source_check_at == dataset.generated_at


def test_dry_run_writes_generated_artifacts_without_publishing(
    dataset: VigieDataset,
    project_config: ProjectConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    published = tmp_path / "data/published"
    manual = tmp_path / "data/manual"
    published.mkdir(parents=True)
    manual.mkdir(parents=True)
    original = json.dumps(dataset.model_dump(mode="json", by_alias=True))
    (published / "vigie.json").write_text(original, encoding="utf-8")
    (manual / "overrides.yaml").write_text("overrides: []\n", encoding="utf-8")
    period = Period(
        period_id="2026-T1",
        period_key="T1",
        type="quarter",
        year=2026,
        quarter=1,
        end_date=dataset.periods[0].end_date.replace(year=2026, month=3, day=31),
        label="T1 2026",
    )
    document = DiscoveredDocument.model_validate(
        {
            "sourceId": "mfc-results",
            "canonicalUrl": "https://example.com/q1-2026",
            "title": "Résultats T1 2026",
            "documentKind": "published_result",
        }
    )

    def financial(*_: object, **__: object) -> FinancialAcquisition:
        return FinancialAcquisition([], [period], [document], [], 0, dataset.generated_at)

    def news(*_: object, **__: object) -> NewsAcquisition:
        return NewsAcquisition([], [], [], 0)

    monkeypatch.setattr(cli_module, "acquire_source", financial)
    monkeypatch.setattr(cli_module, "acquire_news", news)
    settings = Settings(root_dir=tmp_path)
    assert command_refresh(settings, project_config, "MFC", False, dry_run=True) == 0
    assert (published / "vigie.json").read_text(encoding="utf-8") == original
    assert (tmp_path / "data/generated/vigie.json").exists()
    report = QualityReport.model_validate_json(
        (tmp_path / "data/generated/quality-report.json").read_text(encoding="utf-8")
    )
    assert report.mode == "live"
    assert report.dry_run is True
    assert "2026-T1" in capsys.readouterr().out
    with pytest.raises(ValidationFailure, match="dry-run"):
        command_publish(settings, project_config)
    assert (published / "vigie.json").read_text(encoding="utf-8") == original


def test_news_outage_does_not_block_valid_financial_update(
    dataset: VigieDataset,
    project_config: ProjectConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published = tmp_path / "data/published"
    manual = tmp_path / "data/manual"
    published.mkdir(parents=True)
    manual.mkdir(parents=True)
    (published / "vigie.json").write_text(
        json.dumps(dataset.model_dump(mode="json", by_alias=True)), encoding="utf-8"
    )
    (manual / "overrides.yaml").write_text("overrides: []\n", encoding="utf-8")
    period = Period(
        period_id="2026-T1",
        period_key="T1",
        type="quarter",
        year=2026,
        quarter=1,
        end_date=dataset.periods[0].end_date.replace(year=2026, month=3, day=31),
        label="T1 2026",
    )
    observation = deepcopy(
        next(
            item
            for item in dataset.observations
            if item.company_id == "MFC"
            and item.period.period_id == "2025-T1"
            and item.metric_id == "core_eps"
        )
    )
    observation.id = "MFC-2026-T1-core_eps"
    observation.period = period
    observation.comparison.period_id = "2025-T1"
    document = DiscoveredDocument.model_validate(
        {
            "sourceId": "mfc-results",
            "canonicalUrl": "https://example.com/q1-2026",
            "title": "Résultats T1 2026",
            "documentKind": "published_result",
        }
    )

    def financial(*_: object, **__: object) -> FinancialAcquisition:
        return FinancialAcquisition(
            [observation], [period], [document], [], 0, dataset.generated_at
        )

    def news_blocked(*_: object, **__: object) -> NewsAcquisition:
        raise FetchError("Salle de presse inaccessible")

    monkeypatch.setattr(cli_module, "acquire_source", financial)
    monkeypatch.setattr(cli_module, "acquire_news", news_blocked)
    assert command_refresh(Settings(root_dir=tmp_path), project_config, "MFC", False) == 0
    refreshed = VigieDataset.model_validate_json(
        (published / "vigie.json").read_text(encoding="utf-8")
    )
    assert "MFC-2026-T1-core_eps" in {item.id for item in refreshed.observations}
    report = QualityReport.model_validate_json(
        (published / "quality-report.json").read_text(encoding="utf-8")
    )
    assert report.status == "partial"
    assert any(item.source_id == "mfc-official-news" for item in report.warnings)
    manifest = DatasetManifest.model_validate_json(
        (published / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest.last_attempt_at == manifest.last_successful_refresh
