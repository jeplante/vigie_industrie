"""Validation métier bloquante avant toute publication."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta

from vigie_pipeline.models import QualityIssue, VigieDataset
from vigie_pipeline.normalize import calculate_change, direction_for

HTML_PATTERN = re.compile(r"<\s*(script|iframe|object|embed|style|img|a)\b", re.IGNORECASE)


def _duplicate_issues(values: list[str], kind: str) -> list[QualityIssue]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return [
        QualityIssue(code=f"duplicate_{kind}", message=f"Identifiant dupliqué: {value}")
        for value in sorted(duplicates)
    ]


def validate_dataset(
    dataset: VigieDataset,
    *,
    minimum_observations: int = 1,
    previous_count: int | None = None,
    maximum_volume_drop: float = 0.1,
    delta_tolerance: float = 0.03,
    known_units: set[str],
    known_metrics: set[str],
    now: datetime | None = None,
) -> list[QualityIssue]:
    """Retourne toutes les erreurs critiques; une liste vide autorise la publication."""

    errors = _duplicate_issues([item.id for item in dataset.observations], "observation_id")
    errors.extend(_duplicate_issues([item.id for item in dataset.news], "news_id"))
    company_ids = {company.id for company in dataset.companies}
    period_ids = {period.period_id for period in dataset.periods}
    errors.extend(_duplicate_issues([period.period_id for period in dataset.periods], "period_id"))
    reference_now = now or datetime.now(UTC)

    if len(dataset.observations) < minimum_observations:
        errors.append(
            QualityIssue(
                code="insufficient_observations",
                message=(
                    f"{len(dataset.observations)} observations; minimum {minimum_observations}."
                ),
            )
        )
    if previous_count and len(dataset.observations) < previous_count * (1 - maximum_volume_drop):
        errors.append(
            QualityIssue(
                code="abnormal_volume_drop",
                message=f"Volume réduit de {previous_count} à {len(dataset.observations)}.",
            )
        )

    for item in dataset.observations:
        prefix = item.id
        if item.company_id not in company_ids:
            errors.append(QualityIssue(code="unknown_company", message=prefix))
        if item.period.period_id not in period_ids:
            errors.append(QualityIssue(code="unknown_period", message=prefix))
        if not math.isfinite(item.value):
            errors.append(QualityIssue(code="invalid_number", message=prefix))
        if item.unit not in known_units:
            errors.append(QualityIssue(code="unknown_unit", message=f"{prefix}: {item.unit}"))
        if item.metric_id not in known_metrics:
            errors.append(
                QualityIssue(code="unknown_metric", message=f"{prefix}: {item.metric_id}")
            )
        if item.source.priority != "primary":
            errors.append(QualityIssue(code="non_primary_financial_source", message=prefix))
        if item.source.published_at > (reference_now + timedelta(days=2)).date():
            errors.append(QualityIssue(code="impossible_future_date", message=prefix))
        text_fields = [item.label, item.note, item.display_value, item.source.title]
        if any(HTML_PATTERN.search(value) for value in text_fields):
            errors.append(QualityIssue(code="html_injection", message=prefix))
        if item.quality.extraction_method == "anthropic" and item.quality.llm_trace is None:
            errors.append(QualityIssue(code="missing_llm_trace", message=prefix))
        if item.quality.extraction_method != "anthropic" and item.quality.llm_trace is not None:
            errors.append(QualityIssue(code="unexpected_llm_trace", message=prefix))

        previous = item.comparison.value
        extracted_change = item.comparison.change
        expected_comparison_period = f"{item.period.year - 1}-{item.period.period_key}"
        if (
            item.comparison.period_id is not None
            and item.comparison.period_id != expected_comparison_period
        ):
            errors.append(
                QualityIssue(
                    code="invalid_comparison_period",
                    message=(
                        f"{prefix}: {item.comparison.period_id}; "
                        f"attendu {expected_comparison_period}."
                    ),
                )
            )
        if previous is not None and item.comparison.change_unit == "PERCENT":
            calculated = calculate_change(item.value, previous)
            if (
                calculated is not None
                and extracted_change is not None
                and abs(calculated - extracted_change) > delta_tolerance
            ):
                errors.append(
                    QualityIssue(
                        code="inconsistent_delta",
                        message=(
                            f"{prefix}: calculé {calculated:.4f}, fourni {extracted_change:.4f}."
                        ),
                    )
                )
        if previous is not None and item.metric_id not in {"licat_ratio", "solvency_ratio"}:
            calculated_direction = direction_for(
                item.value, previous, tolerance=abs(previous) * 0.01
            )
            if calculated_direction != "neutral" and item.direction != calculated_direction:
                errors.append(QualityIssue(code="inconsistent_direction", message=prefix))

    for news_item in dataset.news:
        if any(company_id not in company_ids for company_id in news_item.company_ids):
            errors.append(QualityIssue(code="unknown_news_company", message=news_item.id))
        if news_item.period_id not in period_ids:
            errors.append(QualityIssue(code="unknown_news_period", message=news_item.id))
        fields = [
            news_item.title,
            news_item.original_summary or "",
            news_item.generated_summary or "",
        ]
        if any(HTML_PATTERN.search(value) for value in fields):
            errors.append(QualityIssue(code="html_injection", message=news_item.id))
        if news_item.published_at > (reference_now + timedelta(days=2)).date():
            errors.append(QualityIssue(code="impossible_future_date", message=news_item.id))
        if (
            news_item.quality.extraction_method == "anthropic"
            and news_item.quality.llm_trace is None
        ):
            errors.append(QualityIssue(code="missing_llm_trace", message=news_item.id))
        if news_item.quality.extraction_method == "anthropic" and not news_item.generated_summary:
            errors.append(QualityIssue(code="missing_generated_summary", message=news_item.id))
    return errors
