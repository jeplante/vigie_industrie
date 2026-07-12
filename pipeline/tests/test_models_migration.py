from vigie_pipeline.models import VigieDataset


def test_v1_migration_preserves_all_records(dataset: VigieDataset) -> None:
    assert {company.id for company in dataset.companies} == {"MFC", "SLF", "GWO", "IAG"}
    assert {period.key for period in dataset.periods} == {"T1", "T2", "T3", "AN"}
    assert len(dataset.observations) == 64
    assert len(dataset.news) == 48
    assert len({item.id for item in dataset.observations}) == 64
    assert len({item.id for item in dataset.news}) == 48


def test_models_round_trip_aliases(dataset: VigieDataset) -> None:
    payload = dataset.model_dump(mode="json", by_alias=True)
    assert payload["observations"][0]["companyId"]
    assert VigieDataset.model_validate(payload) == dataset
