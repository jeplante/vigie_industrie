"""Empreintes stables utilisées pour la découverte et les manifestes."""

import hashlib
import json
from typing import Any

from vigie_pipeline.models import VigieDataset


def sha256_bytes(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def sha256_text(content: str) -> str:
    return sha256_bytes(content.encode("utf-8"))


def dataset_hash(dataset: VigieDataset) -> str:
    serialized = json.dumps(
        _normalize_numbers(dataset.model_dump(mode="json", by_alias=True, exclude_none=True)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_text(serialized)


def _normalize_numbers(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [_normalize_numbers(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_numbers(item) for key, item in value.items()}
    return value
