"""Préparation du manifeste et publication validée."""

import json
from datetime import UTC, datetime

from vigie_pipeline.freshness import SourceCheck, build_company_freshness
from vigie_pipeline.hashing import sha256_text
from vigie_pipeline.models import DatasetManifest, QualityReport, VigieDataset
from vigie_pipeline.publishers.base import Publisher


def build_manifest(
    dataset: VigieDataset,
    generated_at: datetime | None = None,
    freshness_checks: dict[str, SourceCheck] | None = None,
) -> DatasetManifest:
    timestamp = generated_at or datetime.now(UTC)
    serialized = json.dumps(
        dataset.model_dump(mode="json", by_alias=True, exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
    )
    return DatasetManifest(
        generated_at=timestamp,
        dataset_hash=sha256_text(serialized),
        observation_count=len(dataset.observations),
        news_count=len(dataset.news),
        company_count=len(dataset.companies),
        last_successful_refresh=timestamp,
        company_freshness=build_company_freshness(
            dataset, freshness_checks, generated_at=timestamp
        ),
    )


def publish_validated(
    dataset: VigieDataset,
    quality_report: QualityReport,
    publisher: Publisher,
    freshness_checks: dict[str, SourceCheck] | None = None,
) -> DatasetManifest:
    manifest = build_manifest(dataset, quality_report.generated_at, freshness_checks)
    publisher.publish(dataset=dataset, manifest=manifest, quality_report=quality_report)
    return manifest
