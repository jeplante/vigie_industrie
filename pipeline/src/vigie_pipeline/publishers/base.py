"""Contrat de publication substituable (future cible SharePoint)."""

from typing import Protocol

from vigie_pipeline.models import DatasetManifest, QualityReport, VigieDataset


class Publisher(Protocol):
    def publish(
        self,
        *,
        dataset: VigieDataset,
        manifest: DatasetManifest,
        quality_report: QualityReport,
    ) -> None:
        """Publie atomiquement un jeu préalablement validé."""
        ...
