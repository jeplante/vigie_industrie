"""Corrections manuelles auditées, appliquées avant validation finale."""

from pathlib import Path
from typing import Any

import yaml

from vigie_pipeline.exceptions import ConfigurationError
from vigie_pipeline.models import VigieDataset

ALLOWED_FIELDS = {"value", "displayValue", "note", "direction"}


def apply_overrides(dataset: VigieDataset, path: Path) -> tuple[VigieDataset, list[str]]:
    if not path.exists():
        return dataset, []
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    applied: list[str] = []
    by_id = {item.id: item for item in dataset.observations}
    for override in raw.get("overrides", []):
        observation_id = str(override.get("observationId", ""))
        fields = override.get("fields", {})
        if observation_id not in by_id:
            raise ConfigurationError(
                f"Correction visant une observation inconnue: {observation_id}"
            )
        if not override.get("reason") or not override.get("sourceUrl"):
            raise ConfigurationError(f"Correction sans justification ou source: {observation_id}")
        unknown = set(fields) - ALLOWED_FIELDS
        if unknown:
            raise ConfigurationError(f"Champs de correction interdits: {sorted(unknown)}")
        updated = by_id[observation_id].model_copy(
            update={
                "value"
                if key == "value"
                else "display_value"
                if key == "displayValue"
                else key: value
                for key, value in fields.items()
            }
        )
        approver = override.get("approvedBy", "approbateur non indiqué")
        updated.quality.warnings.append(f"Correction manuelle: {override['reason']} ({approver}).")
        by_id[observation_id] = updated
        applied.append(observation_id)
    dataset.observations = [by_id[item.id] for item in dataset.observations]
    return dataset, applied
