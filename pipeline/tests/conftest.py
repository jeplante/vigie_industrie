from pathlib import Path

import pytest

from vigie_pipeline.models import VigieDataset


@pytest.fixture
def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def dataset(repository_root: Path) -> VigieDataset:
    return VigieDataset.model_validate_json(
        (repository_root / "data/seed/vigie-v1.json").read_text(encoding="utf-8")
    )
