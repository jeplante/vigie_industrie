"""Publication atomique des fichiers statiques consommés par GitHub Pages."""

import json
import os
import shutil
import tempfile
from pathlib import Path

from vigie_pipeline.models import CanonicalModel, DatasetManifest, QualityReport, VigieDataset


def _write_model(path: Path, model: CanonicalModel) -> None:
    path.write_text(
        json.dumps(model.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


class GitHubPagesPublisher:
    """Écrit les trois fichiers ensemble et ne touche pas au dernier jeu valide en cas d’erreur."""

    def __init__(self, published_dir: Path, frontend_data_dir: Path | None = None) -> None:
        self.published_dir = published_dir
        self.frontend_data_dir = frontend_data_dir

    def publish(
        self,
        *,
        dataset: VigieDataset,
        manifest: DatasetManifest,
        quality_report: QualityReport,
    ) -> None:
        self.published_dir.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="vigie-publish-", dir=self.published_dir.parent))
        try:
            _write_model(temp_dir / "vigie.json", dataset)
            _write_model(temp_dir / "manifest.json", manifest)
            _write_model(temp_dir / "quality-report.json", quality_report)
            self.published_dir.mkdir(parents=True, exist_ok=True)
            for name in ("vigie.json", "manifest.json", "quality-report.json"):
                os.replace(temp_dir / name, self.published_dir / name)
            if self.frontend_data_dir is not None:
                self.frontend_data_dir.mkdir(parents=True, exist_ok=True)
                for name in ("vigie.json", "manifest.json", "quality-report.json"):
                    shutil.copy2(self.published_dir / name, self.frontend_data_dir / name)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
