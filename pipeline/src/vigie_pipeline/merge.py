"""Fusion sans perte et déduplication contrôlée."""

from copy import deepcopy
from datetime import date

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
    """Déduplique les URL et les reprises du même communiqué sur un autre domaine."""

    by_url: dict[str, int] = {}
    unique_urls: list[NewsItem] = []
    for item in items:
        key = str(item.source.url).rstrip("/").lower()
        existing_index = by_url.get(key)
        if existing_index is None:
            by_url[key] = len(unique_urls)
            unique_urls.append(item)
        else:
            unique_urls[existing_index] = item

    by_release: dict[tuple[tuple[str, ...], date, str], int] = {}
    result: list[NewsItem] = []
    for item in unique_urls:
        release_key = (
            tuple(sorted(str(company_id) for company_id in item.company_ids)),
            item.published_at,
            " ".join(item.title.casefold().split()),
        )
        existing_index = by_release.get(release_key)
        if existing_index is None:
            by_release[release_key] = len(result)
            result.append(item)
        elif _news_preference(item) > _news_preference(result[existing_index]):
            result[existing_index] = item
    return result


def _news_preference(item: NewsItem) -> tuple[int, bool, bool]:
    quality_rank = {"rejected": 0, "warning": 1, "validated": 2}
    return (
        quality_rank[item.quality.status],
        item.generated_summary is not None,
        "newswire.ca" not in str(item.source.url).lower(),
    )
