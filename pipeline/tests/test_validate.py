from copy import deepcopy

from vigie_pipeline.config import ProjectConfig
from vigie_pipeline.models import VigieDataset
from vigie_pipeline.publish import build_manifest
from vigie_pipeline.quality import build_quality_report
from vigie_pipeline.validate import validate_artifact_set, validate_dataset


def test_seed_is_valid(dataset: VigieDataset, project_config: ProjectConfig) -> None:
    assert (
        validate_dataset(
            dataset,
            minimum_observations=64,
            known_units=project_config.known_units,
            known_metrics=set(project_config.metrics),
        )
        == []
    )


def test_rejects_unknown_unit_duplicate_and_volume_drop(
    dataset: VigieDataset, project_config: ProjectConfig
) -> None:
    candidate = deepcopy(dataset)
    candidate.observations[0].unit = "BITCOIN"
    candidate.observations[1].id = candidate.observations[0].id
    errors = validate_dataset(
        candidate,
        minimum_observations=65,
        previous_count=100,
        known_units=project_config.known_units,
        known_metrics=set(project_config.metrics),
    )
    codes = {error.code for error in errors}
    assert {
        "unknown_unit",
        "duplicate_observation_id",
        "insufficient_observations",
        "abnormal_volume_drop",
    } <= codes


def test_rejects_html_and_non_primary_financial_source(
    dataset: VigieDataset, project_config: ProjectConfig
) -> None:
    candidate = deepcopy(dataset)
    candidate.observations[0].note = "<script>alert(1)</script>"
    candidate.observations[0].source.priority = "secondary"
    codes = {
        error.code
        for error in validate_dataset(
            candidate,
            known_units=project_config.known_units,
            known_metrics=set(project_config.metrics),
        )
    }
    assert "html_injection" in codes
    assert "non_primary_financial_source" in codes


def test_rejects_cross_period_comparison(
    dataset: VigieDataset, project_config: ProjectConfig
) -> None:
    candidate = deepcopy(dataset)
    candidate.observations[0].comparison.period_id = "2024-AN"
    codes = {
        error.code
        for error in validate_dataset(
            candidate,
            known_units=project_config.known_units,
            known_metrics=set(project_config.metrics),
        )
    }
    assert "invalid_comparison_period" in codes


def test_cross_validates_dataset_manifest_and_quality_report(dataset: VigieDataset) -> None:
    report = build_quality_report(mode="migration", generated_at=dataset.generated_at)
    manifest = build_manifest(dataset, dataset.generated_at, mode="migration")
    assert validate_artifact_set(dataset, manifest, report) == []
    manifest.dataset_hash = f"sha256:{'0' * 64}"
    manifest.observation_count += 1
    report.sources_checked = 4
    report.sources_succeeded = 4
    codes = {item.code for item in validate_artifact_set(dataset, manifest, report)}
    assert {
        "dataset_hash_mismatch",
        "artifact_count_mismatch",
        "offline_source_claim",
    } <= codes
