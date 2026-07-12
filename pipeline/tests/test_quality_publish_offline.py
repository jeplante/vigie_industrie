import json
from copy import deepcopy
from pathlib import Path

import pytest

from vigie_pipeline.cli import command_publish, command_refresh
from vigie_pipeline.exceptions import ValidationFailure
from vigie_pipeline.models import VigieDataset
from vigie_pipeline.quality import build_quality_report
from vigie_pipeline.settings import Settings


def test_quality_report_statuses() -> None:
    assert build_quality_report().status == "success"
    assert build_quality_report(sources_checked=2, sources_succeeded=1).status == "partial"


def test_last_known_good_is_preserved(dataset: VigieDataset, tmp_path: Path) -> None:
    published = tmp_path / "data/published"
    generated = tmp_path / "data/generated"
    published.mkdir(parents=True)
    generated.mkdir(parents=True)
    good_payload = dataset.model_dump(mode="json", by_alias=True)
    (published / "vigie.json").write_text(json.dumps(good_payload), encoding="utf-8")
    invalid = deepcopy(dataset)
    invalid.observations[0].unit = "INVALID"
    (generated / "vigie.json").write_text(
        json.dumps(invalid.model_dump(mode="json", by_alias=True)), encoding="utf-8"
    )
    settings = Settings(root_dir=tmp_path, minimum_observations=1)
    with pytest.raises(ValidationFailure):
        command_publish(settings)
    preserved = VigieDataset.model_validate_json(
        (published / "vigie.json").read_text(encoding="utf-8")
    )
    assert preserved.observations[0].unit != "INVALID"
    assert (generated / "quality-report.json").exists()


def test_offline_refresh_uses_seed_without_network(dataset: VigieDataset, tmp_path: Path) -> None:
    seed = tmp_path / "data/seed"
    manual = tmp_path / "data/manual"
    seed.mkdir(parents=True)
    manual.mkdir(parents=True)
    (seed / "vigie-v1.json").write_text(
        json.dumps(dataset.model_dump(mode="json", by_alias=True)), encoding="utf-8"
    )
    (manual / "overrides.yaml").write_text("overrides: []\n", encoding="utf-8")
    settings = Settings(root_dir=tmp_path, minimum_observations=1)
    assert command_refresh(settings, None, offline=True) == 0
    assert (tmp_path / "data/published/vigie.json").exists()
    assert (tmp_path / "app/public/data/manifest.json").exists()
