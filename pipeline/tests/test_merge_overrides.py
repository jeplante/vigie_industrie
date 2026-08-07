from copy import deepcopy
from pathlib import Path

from vigie_pipeline.merge import deduplicate_news, merge_datasets
from vigie_pipeline.models import VigieDataset
from vigie_pipeline.overrides import apply_overrides


def test_merge_updates_by_id_without_dropping_base(dataset: VigieDataset) -> None:
    candidate = deepcopy(dataset)
    candidate.observations = candidate.observations[:1]
    candidate.observations[0].value = 99
    merged = merge_datasets(dataset, candidate)
    assert len(merged.observations) == 64
    assert merged.observations[0].value == 99


def test_deduplicate_news_by_url(dataset: VigieDataset) -> None:
    duplicate = deepcopy(dataset.news[0])
    duplicate.id = "another-id"
    assert len(deduplicate_news([dataset.news[0], duplicate])) == 1


def test_deduplicate_news_prefers_validated_direct_release(dataset: VigieDataset) -> None:
    direct = deepcopy(dataset.news[0])
    direct.source.url = "https://issuer.example.com/news/strategy"
    direct.quality.status = "validated"
    direct.generated_summary = "Résumé validé."
    syndicated = deepcopy(direct)
    syndicated.id = "syndicated-id"
    syndicated.source.url = "https://www.newswire.ca/news-releases/strategy-123.html"
    syndicated.quality.status = "warning"
    syndicated.generated_summary = None

    result = deduplicate_news([direct, syndicated])

    assert len(result) == 1
    assert result[0].id == direct.id


def test_manual_override_is_audited(dataset: VigieDataset, tmp_path: Path) -> None:
    observation = dataset.observations[0]
    override = tmp_path / "overrides.yaml"
    override.write_text(
        f"""overrides:
  - observationId: {observation.id}
    fields:
      value: 12.96
      displayValue: '12,96 $'
            unit: CAD_BILLION
    reason: Valeur annuelle officielle
    sourceUrl: https://example.com/official
    approvedBy: Jerome Plante
    approvedAt: '2026-07-11'
""",
        encoding="utf-8",
    )
    updated, applied = apply_overrides(dataset, override)
    assert updated.observations[0].value == 12.96
    assert updated.observations[0].unit == "CAD_BILLION"
    assert applied == [observation.id]
    assert "Correction manuelle" in updated.observations[0].quality.warnings[-1]
