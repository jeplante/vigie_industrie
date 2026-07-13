"""Adaptateurs d’extraction propres aux compagnies."""

from vigie_pipeline.sources.great_west import GreatWestAdapter
from vigie_pipeline.sources.ia import IaAdapter
from vigie_pipeline.sources.manulife import ManulifeAdapter
from vigie_pipeline.sources.sunlife import SunLifeAdapter

__all__ = ["GreatWestAdapter", "IaAdapter", "ManulifeAdapter", "SunLifeAdapter"]
