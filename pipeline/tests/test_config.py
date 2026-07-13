import shutil
from pathlib import Path

from vigie_pipeline.config import load_project_config
from vigie_pipeline.settings import Settings


def test_all_yaml_files_drive_runtime_behavior(repository_root: Path, tmp_path: Path) -> None:
    shutil.copytree(repository_root / "config", tmp_path / "config")
    pipeline_path = tmp_path / "config/pipeline.yaml"
    pipeline_path.write_text(
        pipeline_path.read_text(encoding="utf-8").replace(
            "maxDownloadBytes: 15000000", "maxDownloadBytes: 4321"
        ),
        encoding="utf-8",
    )
    metrics_path = tmp_path / "config/metrics.yaml"
    metrics_path.write_text(
        metrics_path.read_text(encoding="utf-8").replace(
            "label: BPA activités de base", "label: BPA configuré par YAML", 1
        ),
        encoding="utf-8",
    )
    companies_path = tmp_path / "config/companies.yaml"
    companies_path.write_text(
        companies_path.read_text(encoding="utf-8").replace(
            "name: Manuvie", "name: Manuvie YAML", 1
        ),
        encoding="utf-8",
    )
    sources_path = tmp_path / "config/sources.yaml"
    sources_path.write_text(
        sources_path.read_text(encoding="utf-8").replace("maxArticles: 5", "maxArticles: 3", 1),
        encoding="utf-8",
    )
    config = load_project_config(
        tmp_path,
        Settings(
            root_dir=tmp_path,
            anthropic_standard_model="standard-env",
            anthropic_complex_model="complex-env",
        ),
    )
    assert config.pipeline.http.max_download_bytes == 4321
    assert config.metrics["core_eps"].label == "BPA configuré par YAML"
    assert config.pipeline.llm.standard_model == "standard-env"
    assert config.pipeline.llm.complex_model == "complex-env"
    assert config.companies["MFC"].name == "Manuvie YAML"
    assert (
        next(source for source in config.sources if source.id == "mfc-official-news").max_articles
        == 3
    )
    assert set(config.companies) == {"MFC", "SLF", "GWO", "IAG"}
    assert {source.content_category for source in config.sources} >= {
        "financial_results",
        "official_news",
    }


def test_required_anthropic_defaults_come_from_yaml(repository_root: Path) -> None:
    config = load_project_config(repository_root)
    assert config.pipeline.llm.standard_model == "claude-haiku-4-5"
    assert config.pipeline.llm.complex_model == "claude-sonnet-5"
