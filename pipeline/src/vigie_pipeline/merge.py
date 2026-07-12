"""Fusion sans perte et déduplication contrôlée."""

from copy import deepcopy

from vigie_pipeline.models import NewsItem, Observation, VigieDataset


def merge_datasets(base: VigieDataset, candidate: VigieDataset) -> VigieDataset:
    """Fusionne par identifiant; le candidat remplace seulement un objet complet valide."""

    result = deepcopy(base)
    observations: dict[str, Observation] = {item.id: item for item in result.observations}
    observations.update({item.id: item for item in candidate.observations})
    news: dict[str, NewsItem] = {item.id: item for item in result.news}
    news.update({item.id: item for item in candidate.news})
    result.observations = list(observations.values())
    result.news = list(news.values())
    periods = {period.period_id: period for period in result.periods}
    periods.update({period.period_id: period for period in candidate.periods})
    result.periods = sorted(periods.values(), key=lambda period: period.end_date, reverse=True)
    result.generated_at = candidate.generated_at
    for company in candidate.companies:
        if company.id not in {item.id for item in result.companies}:
            result.companies.append(company)
    return result


def deduplicate_news(items: list[NewsItem]) -> list[NewsItem]:
    """Conserve le premier item de chaque URL normalisée, de façon stable."""

    seen: set[str] = set()
    result: list[NewsItem] = []
    for item in items:
        key = str(item.source.url).rstrip("/").lower()
        if key not in seen:
            result.append(item)
            seen.add(key)
    return result
