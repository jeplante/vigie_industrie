"""Commandes publiques du pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from vigie_pipeline.acquire import acquire_source
from vigie_pipeline.config import ProjectConfig, SourceConfig, load_project_config
from vigie_pipeline.discovery import discover_documents
from vigie_pipeline.exceptions import ConfigurationError, PipelineError, ValidationFailure
from vigie_pipeline.fetch import BoundedFetcher, FetchResult
from vigie_pipeline.freshness import SourceCheck, freshness_issues
from vigie_pipeline.merge import deduplicate_news
from vigie_pipeline.models import (
    CanonicalModel,
    DatasetManifest,
    Period,
    QualityIssue,
    QualityReport,
    SourceRunResult,
    VigieDataset,
)
from vigie_pipeline.news import acquire_news, discover_news_documents, period_for_date
from vigie_pipeline.overrides import apply_overrides
from vigie_pipeline.publish import build_manifest, publish_validated
from vigie_pipeline.publishers.github_pages import GitHubPagesPublisher
from vigie_pipeline.quality import build_quality_report
from vigie_pipeline.settings import Settings
from vigie_pipeline.validate import validate_artifact_set, validate_dataset

LOGGER = logging.getLogger("vigie_pipeline")


def _read_dataset(path: Path) -> VigieDataset:
    return VigieDataset.model_validate_json(path.read_text(encoding="utf-8"))


def _read_quality(path: Path) -> QualityReport:
    return QualityReport.model_validate_json(path.read_text(encoding="utf-8"))


def _read_manifest(path: Path) -> DatasetManifest:
    return DatasetManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _write_model(path: Path, model: CanonicalModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            model.model_dump(mode="json", by_alias=True, exclude_none=True),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_generated_artifacts(
    settings: Settings,
    dataset: VigieDataset,
    manifest: DatasetManifest,
    report: QualityReport,
) -> None:
    _write_model(settings.generated_dir / "vigie.json", dataset)
    _write_model(settings.generated_dir / "manifest.json", manifest)
    _write_model(settings.generated_dir / "quality-report.json", report)


def _write_failure_report(
    settings: Settings,
    errors: list[QualityIssue],
    *,
    mode: Literal["offline", "live", "migration"] = "live",
) -> None:
    report = build_quality_report(errors=errors, mode=mode)
    _write_model(settings.generated_dir / "quality-report.json", report)


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
    if candidate is None:
        manifest = _read_manifest(settings.published_dir / "manifest.json")
        report = _read_quality(settings.published_dir / "quality-report.json")
        errors.extend(validate_artifact_set(dataset, manifest, report))
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
    report = (
        _read_quality(report_path)
        if report_path.exists()
        else build_quality_report(mode="offline", generated_at=dataset.generated_at)
    )
    if report.dry_run:
        raise ValidationFailure(
            "Un rapport dry-run ne peut pas être publié; relancez refresh sans --dry-run."
        )
    previous_manifest_path = settings.published_dir / "manifest.json"
    previous_manifest = (
        _read_manifest(previous_manifest_path) if previous_manifest_path.exists() else None
    )
    financial_source_ids = {
        source.id for source in config.sources if source.content_category == "financial_results"
    }
    financial_refresh_succeeded = any(
        item.source_id in financial_source_ids and item.status != "failed" and bool(item.period_ids)
        for item in report.source_results
    )
    publisher = GitHubPagesPublisher(settings.published_dir, settings.root_dir / "app/public/data")
    publish_validated(
        dataset,
        report,
        publisher,
        previous_manifest=previous_manifest,
        financial_refresh_succeeded=financial_refresh_succeeded,
    )
    return 0


def command_sync_frontend(settings: Settings, config: ProjectConfig) -> int:
    """Valide puis copie le last-known-good sans aucun accès réseau."""

    command_validate(settings, config)
    destination = settings.root_dir / "app/public/data"
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("vigie.json", "manifest.json", "quality-report.json"):
        shutil.copy2(settings.published_dir / name, destination / name)
    return 0


def _selected_sources(config: ProjectConfig, company: str | None) -> list[SourceConfig]:
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


def _change_counts(before: Mapping[str, object], after: Mapping[str, object]) -> tuple[int, int]:
    added = len(set(after) - set(before))
    updated = sum(before[key] != after[key] for key in set(before) & set(after))
    return added, updated


def command_refresh(
    settings: Settings,
    config: ProjectConfig,
    company: str | None,
    offline: bool,
    dry_run: bool = False,
) -> int:
    if offline and dry_run:
        raise ConfigurationError(
            "--dry-run utilise les vraies sources et ne peut pas être offline."
        )
    mode: Literal["offline", "live", "migration"] = "offline" if offline else "live"
    published_path = settings.published_dir / "vigie.json"
    previous_manifest_path = settings.published_dir / "manifest.json"
    previous_manifest = (
        _read_manifest(previous_manifest_path) if previous_manifest_path.exists() else None
    )
    candidate = _read_dataset(
        settings.root_dir / "data/seed/vigie-v1.json" if offline else published_path
    )
    fallback_last_successful_refresh = candidate.generated_at
    before_observations = {
        item.id: item.model_dump(mode="json", by_alias=True) for item in candidate.observations
    }
    before_news = {item.id: item.model_dump(mode="json", by_alias=True) for item in candidate.news}
    warnings: list[QualityIssue] = []
    freshness_checks: dict[str, SourceCheck] = {}
    source_results: list[SourceRunResult] = []
    sources_succeeded = 0
    financial_refresh_succeeded = False
    sources = [] if offline else _selected_sources(config, company)

    for source in sources:
        try:
            if source.content_category == "financial_results":
                financial_acquisition = acquire_source(candidate, source, settings, config)
                by_id = {item.id: item for item in candidate.observations}
                by_id.update({item.id: item for item in financial_acquisition.observations})
                candidate.observations = list(by_id.values())
                _merge_periods(candidate, financial_acquisition.discovered_periods)
                latest = max(
                    financial_acquisition.discovered_periods,
                    key=lambda period: period.end_date,
                    default=None,
                )
                freshness_checks[source.company_id] = SourceCheck(
                    company_id=source.company_id,
                    source_id=source.id,
                    checked_at=financial_acquisition.checked_at,
                    latest_available_period=latest,
                    verified=latest is not None,
                )
                if latest is not None:
                    financial_refresh_succeeded = True
                for financial_failure in financial_acquisition.failures:
                    warnings.append(
                        QualityIssue(
                            code=(
                                "newer_document_not_ingested"
                                if financial_failure.is_newer
                                else "old_document_not_ingested"
                            ),
                            message=financial_failure.message,
                            source_id=source.id,
                        )
                    )
                empty_financial_discovery = not financial_acquisition.documents or latest is None
                no_document_message = None
                if empty_financial_discovery:
                    no_document_message = (
                        "Aucun document financier découvert."
                        if not financial_acquisition.documents
                        else "Aucune période financière découverte."
                    )
                    warnings.append(
                        QualityIssue(
                            code="no_documents_discovered",
                            message=no_document_message,
                            source_id=source.id,
                        )
                    )
                financial_messages = [item.message for item in financial_acquisition.failures]
                if no_document_message:
                    financial_messages.append(no_document_message)
                source_results.append(
                    SourceRunResult(
                        source_id=source.id,
                        company_id=source.company_id,
                        status=(
                            "warning"
                            if financial_acquisition.failures or empty_financial_discovery
                            else "success"
                        ),
                        documents_discovered=len(financial_acquisition.documents),
                        document_urls=[
                            str(item.canonical_url) for item in financial_acquisition.documents
                        ],
                        period_ids=sorted(
                            {item.period_id for item in financial_acquisition.discovered_periods}
                        ),
                        message="; ".join(financial_messages) or None,
                        anthropic_calls=financial_acquisition.anthropic_calls,
                    )
                )
            else:
                news_acquisition = acquire_news(candidate, source, settings, config)
                candidate.news.extend(news_acquisition.items)
                candidate.news = deduplicate_news(candidate.news)
                _merge_periods(
                    candidate,
                    [period_for_date(item.published_at) for item in news_acquisition.items],
                )
                for news_failure in news_acquisition.failures:
                    warnings.append(
                        QualityIssue(
                            code="news_article_failed",
                            message=news_failure.message,
                            source_id=source.id,
                        )
                    )
                degraded = [
                    item for item in news_acquisition.items if item.quality.status == "warning"
                ]
                if degraded:
                    warnings.append(
                        QualityIssue(
                            code="news_llm_degraded",
                            message=(
                                f"{len(degraded)} actualité(s) publiée(s) sans résumé Anthropic."
                            ),
                            source_id=source.id,
                        )
                    )
                no_news_documents = not news_acquisition.documents
                no_document_message = None
                if no_news_documents:
                    no_document_message = "Aucun document d’actualité découvert."
                    warnings.append(
                        QualityIssue(
                            code="no_documents_discovered",
                            message=no_document_message,
                            source_id=source.id,
                        )
                    )
                news_messages = [item.message for item in news_acquisition.failures]
                if no_document_message:
                    news_messages.append(no_document_message)
                source_results.append(
                    SourceRunResult(
                        source_id=source.id,
                        company_id=source.company_id,
                        status=(
                            "warning"
                            if news_acquisition.failures or degraded or no_news_documents
                            else "success"
                        ),
                        documents_discovered=len(news_acquisition.documents),
                        document_urls=[
                            str(item.canonical_url) for item in news_acquisition.documents
                        ],
                        period_ids=sorted({item.period_id for item in news_acquisition.items}),
                        message="; ".join(news_messages) or None,
                        anthropic_calls=news_acquisition.anthropic_calls,
                    )
                )
            if source_results[-1].status == "success":
                sources_succeeded += 1
        except PipelineError as error:
            warnings.append(
                QualityIssue(
                    code="source_refresh_failed",
                    message=str(error),
                    source_id=source.id,
                )
            )
            if source.content_category == "financial_results":
                freshness_checks[source.company_id] = SourceCheck(
                    company_id=source.company_id,
                    source_id=source.id,
                    checked_at=datetime.now(UTC),
                    latest_available_period=None,
                    verified=False,
                )
            source_results.append(
                SourceRunResult(
                    source_id=source.id,
                    company_id=source.company_id,
                    status="failed",
                    documents_discovered=0,
                    message=str(error),
                )
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
    previous_count = (
        len(_read_dataset(published_path).observations) if published_path.exists() else None
    )
    errors = _validation_errors(candidate, config, previous_count=previous_count)
    after_observations = {
        item.id: item.model_dump(mode="json", by_alias=True) for item in candidate.observations
    }
    after_news = {item.id: item.model_dump(mode="json", by_alias=True) for item in candidate.news}
    observations_added, observations_updated = _change_counts(
        before_observations, after_observations
    )
    news_added, news_updated = _change_counts(before_news, after_news)
    report = build_quality_report(
        errors=errors,
        warnings=warnings,
        sources_checked=len(sources),
        sources_succeeded=sources_succeeded,
        observations_added=observations_added,
        observations_updated=observations_updated,
        overrides_applied=len(applied),
        generated_at=candidate.generated_at,
        mode=mode,
        dry_run=dry_run,
        source_results=source_results,
    )
    manifest = build_manifest(
        candidate,
        report.generated_at,
        freshness_checks,
        mode=mode,
        previous_manifest=previous_manifest,
        financial_refresh_succeeded=financial_refresh_succeeded,
        fallback_last_successful_refresh=fallback_last_successful_refresh,
    )
    artifact_errors = validate_artifact_set(candidate, manifest, report)
    if artifact_errors:
        errors.extend(artifact_errors)
        report = build_quality_report(
            errors=errors,
            warnings=warnings,
            sources_checked=len(sources),
            sources_succeeded=sources_succeeded,
            observations_added=observations_added,
            observations_updated=observations_updated,
            overrides_applied=len(applied),
            generated_at=candidate.generated_at,
            mode=mode,
            dry_run=dry_run,
            source_results=source_results,
        )

    if dry_run or errors:
        _write_generated_artifacts(settings, candidate, manifest, report)
    if dry_run:
        print(
            json.dumps(
                {
                    "mode": mode,
                    "dryRun": True,
                    "sources": [
                        item.model_dump(mode="json", by_alias=True, exclude_none=True)
                        for item in source_results
                    ],
                    "periodsDetected": sorted(
                        {period for item in source_results for period in item.period_ids}
                    ),
                    "anthropicCalls": sum(item.anthropic_calls for item in source_results),
                    "wouldAdd": {
                        "observations": observations_added,
                        "news": news_added,
                    },
                    "wouldUpdate": {
                        "observations": observations_updated,
                        "news": news_updated,
                    },
                    "generatedDirectory": str(settings.generated_dir),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    if errors:
        raise ValidationFailure("Candidat invalide; dernière version valide conservée.")
    if not dry_run:
        publisher = GitHubPagesPublisher(
            settings.published_dir, settings.root_dir / "app/public/data"
        )
        publish_validated(
            candidate,
            report,
            publisher,
            freshness_checks,
            previous_manifest,
            financial_refresh_succeeded,
            fallback_last_successful_refresh,
        )
    LOGGER.info("refresh_success mode=%s dry_run=%s company=%s", mode, dry_run, company or "all")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m vigie_pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("refresh", "discover"):
        command = subparsers.add_parser(name)
        command.add_argument("--offline", action="store_true")
        command.add_argument("--company", choices=["MFC", "SLF", "GWO", "IAG"])
        if name == "refresh":
            command.add_argument("--dry-run", action="store_true")
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
            return command_refresh(settings, config, args.company, args.offline, args.dry_run)
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
