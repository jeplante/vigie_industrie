"""Commandes publiques du pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from vigie_pipeline.acquire import acquire_source
from vigie_pipeline.config import load_sources
from vigie_pipeline.discovery import discover_documents
from vigie_pipeline.exceptions import PipelineError, ValidationFailure
from vigie_pipeline.fetch import BoundedFetcher
from vigie_pipeline.hashing import sha256_text
from vigie_pipeline.models import (
    NewsItem,
    NewsSource,
    Observation,
    ObservationQuality,
    QualityIssue,
    QualityReport,
    VigieDataset,
)
from vigie_pipeline.overrides import apply_overrides
from vigie_pipeline.publish import publish_validated
from vigie_pipeline.publishers.github_pages import GitHubPagesPublisher
from vigie_pipeline.quality import build_quality_report
from vigie_pipeline.settings import Settings
from vigie_pipeline.validate import validate_dataset

LOGGER = logging.getLogger("vigie_pipeline")


def _read_dataset(path: Path) -> VigieDataset:
    return VigieDataset.model_validate_json(path.read_text(encoding="utf-8"))


def _read_quality(path: Path) -> QualityReport:
    return QualityReport.model_validate_json(path.read_text(encoding="utf-8"))


def _write_failure_report(settings: Settings, errors: list[QualityIssue]) -> None:
    settings.generated_dir.mkdir(parents=True, exist_ok=True)
    report = build_quality_report(errors=errors)
    (settings.generated_dir / "quality-report.json").write_text(
        json.dumps(report.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


def command_validate(settings: Settings, candidate: Path | None = None) -> int:
    path = candidate or settings.published_dir / "vigie.json"
    dataset = _read_dataset(path)
    errors = validate_dataset(
        dataset,
        minimum_observations=settings.minimum_observations,
        delta_tolerance=settings.delta_tolerance,
    )
    if errors:
        _write_failure_report(settings, errors)
        raise ValidationFailure(f"Validation refusée: {len(errors)} erreur(s).")
    LOGGER.info(
        "validation_success observations=%d news=%d", len(dataset.observations), len(dataset.news)
    )
    return 0


def command_publish(settings: Settings) -> int:
    candidate_path = settings.generated_dir / "vigie.json"
    dataset = _read_dataset(
        candidate_path if candidate_path.exists() else settings.published_dir / "vigie.json"
    )
    errors = validate_dataset(dataset, minimum_observations=settings.minimum_observations)
    if errors:
        _write_failure_report(settings, errors)
        raise ValidationFailure("Le candidat est invalide; dernière version valide conservée.")
    report_path = settings.generated_dir / "quality-report.json"
    report = _read_quality(report_path) if report_path.exists() else build_quality_report()
    publisher = GitHubPagesPublisher(settings.published_dir, settings.root_dir / "app/public/data")
    publish_validated(dataset, report, publisher)
    return 0


def command_discover(settings: Settings, company: str | None, offline: bool) -> int:
    sources = [
        source
        for source in load_sources(settings.config_dir / "sources.yaml")
        if source.enabled and (company is None or source.company_id == company)
    ]
    if offline:
        fixture = settings.root_dir / "pipeline/tests/fixtures/source-index.html"
        from vigie_pipeline.fetch import FetchResult

        result = FetchResult(
            url="https://example.invalid/investors/",
            content=fixture.read_bytes(),
            content_type="text/html",
            etag='"offline"',
            last_modified=None,
        )
        documents = discover_documents("offline-fixture", result)
    else:
        documents = []
        for source in sources:
            with BoundedFetcher(
                timeout=source.timeout_seconds,
                attempts=source.attempts,
                max_bytes=settings.max_download_bytes,
            ) as fetcher:
                documents.extend(discover_documents(source.id, fetcher.fetch(str(source.url))))
    print(
        json.dumps(
            [item.model_dump(mode="json", by_alias=True) for item in documents],
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_refresh(settings: Settings, company: str | None, offline: bool) -> int:
    if offline:
        candidate = _read_dataset(settings.root_dir / "data/seed/vigie-v1.json")
        sources_checked = 4
        sources_succeeded = 4
    else:
        candidate = _read_dataset(settings.published_dir / "vigie.json")
        sources = [
            source
            for source in load_sources(settings.config_dir / "sources.yaml")
            if source.enabled and (company is None or source.company_id == company)
        ]
        acquisition_errors: list[QualityIssue] = []
        sources_succeeded = 0
        for source in sources:
            try:
                extracted = acquire_source(candidate, source, settings)
                by_id = {item.id: item for item in candidate.observations}
                by_id.update({item.id: item for item in extracted})
                candidate.observations = list(by_id.values())
                _append_financial_news(candidate, extracted)
                sources_succeeded += 1
            except PipelineError as error:
                acquisition_errors.append(
                    QualityIssue(
                        code="source_refresh_failed",
                        message=str(error),
                        source_id=source.id,
                    )
                )
        sources_checked = len(sources)
        if acquisition_errors:
            _write_failure_report(settings, acquisition_errors)
            raise ValidationFailure(
                "Une source n’a pas pu être extraite; dernière version valide conservée."
            )
    candidate.generated_at = datetime.now(UTC)
    candidate, applied = apply_overrides(
        candidate, settings.root_dir / "data/manual/overrides.yaml"
    )
    previous_count = None
    published = settings.published_dir / "vigie.json"
    if published.exists():
        previous_count = len(_read_dataset(published).observations)
    errors = validate_dataset(
        candidate,
        minimum_observations=settings.minimum_observations,
        previous_count=previous_count,
        maximum_volume_drop=settings.maximum_volume_drop,
        delta_tolerance=settings.delta_tolerance,
    )
    if errors:
        _write_failure_report(settings, errors)
        raise ValidationFailure("Candidat invalide; dernière version valide conservée.")
    report = build_quality_report(
        sources_checked=sources_checked,
        sources_succeeded=sources_succeeded,
        overrides_applied=len(applied),
        generated_at=candidate.generated_at,
    )
    settings.generated_dir.mkdir(parents=True, exist_ok=True)
    publisher = GitHubPagesPublisher(settings.published_dir, settings.root_dir / "app/public/data")
    publish_validated(candidate, report, publisher)
    LOGGER.info("refresh_success offline=%s company=%s", offline, company or "all")
    return 0


def _append_financial_news(dataset: VigieDataset, observations: list[Observation]) -> None:
    if not observations:
        return
    first = observations[0]
    source_url = str(first.source.url)
    news_id = f"news-{sha256_text(source_url)[7:27]}"
    if any(item.id == news_id for item in dataset.news):
        return
    summary = "; ".join(f"{item.label}: {item.display_value}" for item in observations)
    dataset.news.append(
        NewsItem(
            id=news_id,
            company_ids=[first.company_id],
            period_key=first.period.key,
            published_at=first.source.published_at,
            source=NewsSource(
                type="official_ir",
                name=first.source.title,
                url=first.source.url,
            ),
            title=first.source.title,
            original_summary=summary,
            generated_summary=None,
            categories=["financial_results"],
            importance="high",
            themes=[item.label for item in observations],
            quality=ObservationQuality(
                status="validated",
                extraction_method="deterministic",
                confidence=1,
                warnings=[],
            ),
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m vigie_pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("refresh", "discover"):
        command = subparsers.add_parser(name)
        command.add_argument("--offline", action="store_true")
        command.add_argument("--company", choices=["MFC", "SLF", "GWO", "IAG"])
    validate = subparsers.add_parser("validate")
    validate.add_argument("--candidate", type=Path)
    subparsers.add_parser("publish")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    settings = Settings()
    try:
        if args.command == "refresh":
            return command_refresh(settings, args.company, args.offline)
        if args.command == "discover":
            return command_discover(settings, args.company, args.offline)
        if args.command == "validate":
            return command_validate(settings, args.candidate)
        return command_publish(settings)
    except (PipelineError, ValidationError, OSError) as error:
        LOGGER.error("pipeline_failed type=%s message=%s", error.__class__.__name__, error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
