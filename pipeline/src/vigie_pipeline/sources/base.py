"""Contrat minimal des adaptateurs de source."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class MetricCandidate:
    metric_id: str
    label: str
    raw_value: str
    value: float
    context: str


class SourceAdapter(Protocol):
    company_id: str

    def extract_metrics(self, content: str) -> list[MetricCandidate]:
        """Extrait seulement les valeurs accompagnées d’un contexte vérifiable."""
        ...
