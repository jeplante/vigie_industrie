"""Préparation du manifeste et publication validée."""

from datetime import UTC, datetime
from typing import Literal

from vigie_pipeline.exceptions import ValidationFailure
from vigie_pipeline.freshness import SourceCheck, build_company_freshness
from vigie_pipeline.hashing import dataset_hash
from vigie_pipeline.models import DatasetManifest, QualityReport, VigieDataset
from vigie_pipeline.publishers.base import Publisher
from vigie_pipeline.validate import validate_artifact_set


def build_manifest(
    dataset: VigieDataset,
    generated_at: datetime | None = None,
    freshness_checks: dict[str, SourceCheck] | None = None,
    *,
    mode: Literal["offline", "live", "migration"] = "live",
    previous_manifest: DatasetManifest | None = None,
    financial_refresh_succeeded: bool = False,
    fallback_last_successful_refresh: datetime | None = None,
) -> DatasetManifest:
    timestamp = generated_at or datetime.now(UTC)
    last_successful_refresh = (
        previous_manifest.last_successful_refresh
        if previous_manifest is not None
        else fallback_last_successful_refresh or dataset.generated_at
    )
    if mode == "offline" and previous_manifest is not None:
        if previous_manifest.mode == "offline" and previous_manifest.last_attempt_at is None:
            last_successful_refresh = fallback_last_successful_refresh or dataset.generated_at
    elif mode == "live" and financial_refresh_succeeded:
        last_successful_refresh = timestamp
    return DatasetManifest(
        generated_at=timestamp,
        mode=mode,
        dataset_hash=dataset_hash(dataset),
        observation_count=len(dataset.observations),
        news_count=len(dataset.news),
        company_count=len(dataset.companies),
        last_attempt_at=timestamp,
        last_successful_refresh=last_successful_refresh,
        company_freshness=build_company_freshness(
            dataset,
            freshness_checks,
            generated_at=timestamp,
            previous=previous_manifest.company_freshness if previous_manifest else None,
            mode=mode,
        ),
    )


def publish_validated(
    dataset: VigieDataset,
    quality_report: QualityReport,
    publisher: Publisher,
    freshness_checks: dict[str, SourceCheck] | None = None,
    previous_manifest: DatasetManifest | None = None,
    financial_refresh_succeeded: bool = False,
    fallback_last_successful_refresh: datetime | None = None,
) -> DatasetManifest:
    manifest = build_manifest(
        dataset,
        quality_report.generated_at,
        freshness_checks,
        mode=quality_report.mode,
        previous_manifest=previous_manifest,
        financial_refresh_succeeded=financial_refresh_succeeded,
        fallback_last_successful_refresh=fallback_last_successful_refresh,
    )
    artifact_errors = validate_artifact_set(dataset, manifest, quality_report)
    if artifact_errors:
        raise ValidationFailure(
            f"Artefacts incohérents: {', '.join(item.code for item in artifact_errors)}"
        )
    publisher.publish(dataset=dataset, manifest=manifest, quality_report=quality_report)
    return manifest
