"""Commandes publiques du pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from vigie_pipeline.acquire import acquire_source
from vigie_pipeline.config import ProjectConfig, SourceConfig, load_project_config
from vigie_pipeline.discovery import discover_documents
from vigie_pipeline.exceptions import (
    DocumentNotIngestedError,
    PipelineError,
    ValidationFailure,
)
from vigie_pipeline.fetch import BoundedFetcher, FetchResult
from vigie_pipeline.freshness import SourceCheck, freshness_issues, latest_published_period
from vigie_pipeline.merge import deduplicate_news
from vigie_pipeline.models import Period, QualityIssue, QualityReport, VigieDataset
from vigie_pipeline.news import acquire_news, discover_news_documents, period_for_date
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


def _validation_errors(
    dataset: VigieDataset,
    config: ProjectConfig,
    *,
    previous_count: int | None = None,
) -> list[QualityIssue]:
    validation = config.pipeline.validation
    return validate_dataset(
        dataset,
        minimum_observations=validation.minimum_observations,
        previous_count=previous_count,
        maximum_volume_drop=validation.maximum_volume_drop,
        delta_tolerance=validation.delta_tolerance,
        known_units=config.known_units,
        known_metrics=set(config.metrics),
    )


def command_validate(
    settings: Settings,
    config: ProjectConfig,
    candidate: Path | None = None,
) -> int:
    path = candidate or settings.published_dir / "vigie.json"
    dataset = _read_dataset(path)
    errors = _validation_errors(dataset, config)
    if errors:
        _write_failure_report(settings, errors)
        raise ValidationFailure(f"Validation refusée: {len(errors)} erreur(s).")
    LOGGER.info(
        "validation_success observations=%d news=%d", len(dataset.observations), len(dataset.news)
    )
    return 0


def command_publish(settings: Settings, config: ProjectConfig) -> int:
    candidate_path = settings.generated_dir / "vigie.json"
    dataset = _read_dataset(
        candidate_path if candidate_path.exists() else settings.published_dir / "vigie.json"
    )
    errors = _validation_errors(dataset, config)
    if errors:
        _write_failure_report(settings, errors)
        raise ValidationFailure("Le candidat est invalide; dernière version valide conservée.")
    report_path = settings.generated_dir / "quality-report.json"
    report = _read_quality(report_path) if report_path.exists() else build_quality_report()
    publisher = GitHubPagesPublisher(settings.published_dir, settings.root_dir / "app/public/data")
    publish_validated(dataset, report, publisher)
    return 0


def command_sync_frontend(settings: Settings, config: ProjectConfig) -> int:
    """Valide puis copie le last-known-good sans aucun accès réseau."""

    command_validate(settings, config)
    destination = settings.root_dir / "app/public/data"
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("vigie.json", "manifest.json", "quality-report.json"):
        shutil.copy2(settings.published_dir / name, destination / name)
    return 0


def _selected_sources(
    config: ProjectConfig,
    company: str | None,
) -> list[SourceConfig]:
    return [
        source
        for source in config.sources
        if source.enabled and (company is None or source.company_id == company)
    ]


def _merge_periods(dataset: VigieDataset, periods: list[Period]) -> None:
    by_id = {period.period_id: period for period in dataset.periods}
    by_id.update({period.period_id: period for period in periods})
    dataset.periods = sorted(by_id.values(), key=lambda period: period.end_date, reverse=True)


def command_discover(
    settings: Settings,
    config: ProjectConfig,
    company: str | None,
    offline: bool,
) -> int:
    sources = _selected_sources(config, company)
    if offline:
        fixture = settings.root_dir / "pipeline/tests/fixtures/source-index.html"
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
                max_bytes=config.pipeline.http.max_download_bytes,
            ) as fetcher:
                index = fetcher.fetch(str(source.url))
                if source.content_category == "financial_results":
                    documents.extend(discover_documents(source.id, index))
                else:
                    documents.extend(discover_news_documents(source, index))
    print(
        json.dumps(
            [item.model_dump(mode="json", by_alias=True) for item in documents],
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_refresh(
    settings: Settings,
    config: ProjectConfig,
    company: str | None,
    offline: bool,
) -> int:
    if offline:
        candidate = _read_dataset(settings.root_dir / "data/seed/vigie-v1.json")
        sources_checked = len(config.companies)
        sources_succeeded = sources_checked
        warnings: list[QualityIssue] = []
        freshness_checks: dict[str, SourceCheck] = {}
    else:
        candidate = _read_dataset(settings.published_dir / "vigie.json")
        sources = _selected_sources(config, company)
        acquisition_errors: list[QualityIssue] = []
        warnings = []
        freshness_checks = {}
        sources_succeeded = 0
        for source in sources:
            try:
                if source.content_category == "financial_results":
                    acquisition = acquire_source(candidate, source, settings, config)
                    by_id = {item.id: item for item in candidate.observations}
                    by_id.update({item.id: item for item in acquisition.observations})
                    candidate.observations = list(by_id.values())
                    _merge_periods(candidate, acquisition.discovered_periods)
                    latest = max(
                        acquisition.discovered_periods,
                        key=lambda period: period.end_date,
                        default=None,
                    )
                    freshness_checks[source.company_id] = SourceCheck(
                        company_id=source.company_id,
                        source_id=source.id,
                        checked_at=acquisition.checked_at,
                        latest_available_period=latest,
                        verified=latest is not None,
                    )
                else:
                    news = acquire_news(candidate, source, settings, config)
                    candidate.news.extend(news)
                    candidate.news = deduplicate_news(candidate.news)
                    _merge_periods(candidate, [period_for_date(item.published_at) for item in news])
                sources_succeeded += 1
            except DocumentNotIngestedError as error:
                period = error.period
                if not isinstance(period, Period):
                    raise
                published_period = latest_published_period(candidate, source.company_id)
                is_newer = published_period is None or period.end_date > published_period.end_date
                freshness_checks[source.company_id] = SourceCheck(
                    company_id=source.company_id,
                    source_id=source.id,
                    checked_at=datetime.now(UTC),
                    latest_available_period=period,
                    verified=True,
                )
                warnings.append(
                    QualityIssue(
                        code=(
                            "newer_document_not_ingested" if is_newer else "source_refresh_failed"
                        ),
                        message=str(error),
                        source_id=source.id,
                    )
                )
            except PipelineError as error:
                issue = QualityIssue(
                    code="source_refresh_failed",
                    message=str(error),
                    source_id=source.id,
                )
                if source.content_category == "financial_results":
                    freshness_checks[source.company_id] = SourceCheck(
                        company_id=source.company_id,
                        source_id=source.id,
                        checked_at=datetime.now(UTC),
                        latest_available_period=None,
                        verified=False,
                    )
                    warnings.append(issue)
                elif source.required:
                    acquisition_errors.append(issue)
                else:
                    warnings.append(issue)
        sources_checked = len(sources)
        if acquisition_errors:
            _write_failure_report(settings, acquisition_errors)
            raise ValidationFailure(
                "Une source obligatoire n’a pas pu être traitée; dernière version valide conservée."
            )
        existing_issue_keys = {(issue.code, issue.source_id) for issue in warnings}
        warnings.extend(
            issue
            for issue in freshness_issues(candidate, freshness_checks)
            if (issue.code, issue.source_id) not in existing_issue_keys
        )
    candidate.generated_at = datetime.now(UTC)
    candidate, applied = apply_overrides(
        candidate, settings.root_dir / "data/manual/overrides.yaml"
    )
    published = settings.published_dir / "vigie.json"
    previous_count = len(_read_dataset(published).observations) if published.exists() else None
    errors = _validation_errors(candidate, config, previous_count=previous_count)
    if errors:
        _write_failure_report(settings, errors)
        raise ValidationFailure("Candidat invalide; dernière version valide conservée.")
    report = build_quality_report(
        warnings=warnings,
        sources_checked=sources_checked,
        sources_succeeded=sources_succeeded,
        overrides_applied=len(applied),
        generated_at=candidate.generated_at,
    )
    publisher = GitHubPagesPublisher(settings.published_dir, settings.root_dir / "app/public/data")
    publish_validated(candidate, report, publisher, freshness_checks)
    LOGGER.info("refresh_success offline=%s company=%s", offline, company or "all")
    return 0


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
    subparsers.add_parser("sync-frontend")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    settings = Settings()
    try:
        config = load_project_config(settings.root_dir, settings)
        if args.command == "refresh":
            return command_refresh(settings, config, args.company, args.offline)
        if args.command == "discover":
            return command_discover(settings, config, args.company, args.offline)
        if args.command == "validate":
            return command_validate(settings, config, args.candidate)
        if args.command == "sync-frontend":
            return command_sync_frontend(settings, config)
        return command_publish(settings, config)
    except (PipelineError, ValidationError, OSError) as error:
        LOGGER.error("pipeline_failed type=%s message=%s", error.__class__.__name__, error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
