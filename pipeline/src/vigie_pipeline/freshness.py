"""Évaluation de fraîcheur fondée sur les documents officiels réellement découverts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from vigie_pipeline.models import CompanyFreshness, Period, QualityIssue, VigieDataset


@dataclass(frozen=True)
class SourceCheck:
    company_id: str
    source_id: str
    checked_at: datetime
    latest_available_period: Period | None
    verified: bool


def latest_published_period(dataset: VigieDataset, company_id: str) -> Period | None:
    periods = [item.period for item in dataset.observations if item.company_id == company_id]
    return max(periods, key=lambda period: period.end_date, default=None)


def build_company_freshness(
    dataset: VigieDataset,
    checks: dict[str, SourceCheck] | None = None,
    *,
    generated_at: datetime | None = None,
    previous: list[CompanyFreshness] | None = None,
    mode: Literal["offline", "live", "migration"] = "live",
) -> list[CompanyFreshness]:
    checks = checks or {}
    previous_by_company = {item.company_id: item for item in previous or []}
    result: list[CompanyFreshness] = []
    for company in dataset.companies:
        published = latest_published_period(dataset, company.id)
        check = checks.get(company.id)
        prior = previous_by_company.get(company.id)
        if mode != "live":
            available = None
            status: Literal["current", "stale", "unknown"] = "unknown"
            checked_at = None
        elif check is None and prior is not None:
            result.append(
                CompanyFreshness(
                    company_id=company.id,
                    latest_available_period_id=prior.latest_available_period_id,
                    latest_published_period_id=(published.period_id if published else None),
                    latest_source_check_at=prior.latest_source_check_at,
                    freshness_status=prior.freshness_status,
                )
            )
            continue
        elif check is None:
            available = None
            status = "unknown"
            checked_at = None
        elif not check.verified:
            available = check.latest_available_period
            status = "unknown"
            checked_at = check.checked_at
        else:
            available = check.latest_available_period
            status = (
                "stale"
                if available is not None
                and (published is None or available.end_date > published.end_date)
                else "current"
            )
            checked_at = check.checked_at
        result.append(
            CompanyFreshness(
                company_id=company.id,
                latest_available_period_id=available.period_id if available else None,
                latest_published_period_id=published.period_id if published else None,
                latest_source_check_at=checked_at,
                freshness_status=status,
            )
        )
    return result


def freshness_issues(dataset: VigieDataset, checks: dict[str, SourceCheck]) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for company_id, check in checks.items():
        published = latest_published_period(dataset, company_id)
        available = check.latest_available_period
        if (
            check.verified
            and available is not None
            and (published is None or available.end_date > published.end_date)
        ):
            issues.append(
                QualityIssue(
                    code="newer_document_not_ingested",
                    message=(
                        f"{company_id}: document officiel {available.period_id} découvert; "
                        f"dernière période intégrée "
                        f"{published.period_id if published else 'aucune'}."
                    ),
                    source_id=check.source_id,
                )
            )
    return issues
