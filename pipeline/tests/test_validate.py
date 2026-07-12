from copy import deepcopy

from vigie_pipeline.models import VigieDataset
from vigie_pipeline.validate import validate_dataset


def test_seed_is_valid(dataset: VigieDataset) -> None:
    assert validate_dataset(dataset, minimum_observations=64) == []


def test_rejects_unknown_unit_duplicate_and_volume_drop(dataset: VigieDataset) -> None:
    candidate = deepcopy(dataset)
    candidate.observations[0].unit = "BITCOIN"
    candidate.observations[1].id = candidate.observations[0].id
    errors = validate_dataset(candidate, minimum_observations=65, previous_count=100)
    codes = {error.code for error in errors}
    assert {
        "unknown_unit",
        "duplicate_observation_id",
        "insufficient_observations",
        "abnormal_volume_drop",
    } <= codes


def test_rejects_html_and_non_primary_financial_source(dataset: VigieDataset) -> None:
    candidate = deepcopy(dataset)
    candidate.observations[0].note = "<script>alert(1)</script>"
    candidate.observations[0].source.priority = "secondary"
    codes = {error.code for error in validate_dataset(candidate)}
    assert "html_injection" in codes
    assert "non_primary_financial_source" in codes
