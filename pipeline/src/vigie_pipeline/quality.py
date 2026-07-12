"""Construction normalisée du rapport de qualité."""

from datetime import UTC, datetime
from typing import Literal

from vigie_pipeline.models import QualityIssue, QualityReport


def build_quality_report(
    *,
    errors: list[QualityIssue] | None = None,
    warnings: list[QualityIssue] | None = None,
    sources_checked: int = 0,
    sources_succeeded: int = 0,
    observations_added: int = 0,
    observations_updated: int = 0,
    overrides_applied: int = 0,
    generated_at: datetime | None = None,
) -> QualityReport:
    errors = errors or []
    warnings = warnings or []
    sources_failed = max(0, sources_checked - sources_succeeded)
    status: Literal["success", "partial", "failed"] = (
        "failed" if errors else "partial" if warnings or sources_failed else "success"
    )
    return QualityReport(
        generated_at=generated_at or datetime.now(UTC),
        status=status,
        sources_checked=sources_checked,
        sources_succeeded=sources_succeeded,
        sources_failed=sources_failed,
        observations_added=observations_added,
        observations_updated=observations_updated,
        overrides_applied=overrides_applied,
        warnings=warnings,
        errors=errors,
    )
