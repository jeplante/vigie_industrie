"""Variables d’environnement sensibles ou propres à l’exécution."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Les seuils métier restent dans les YAML; seuls les secrets et remplacements vivent ici."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", env_ignore_empty=True)

    anthropic_api_key: str | None = Field(default=None, repr=False)
    anthropic_standard_model: str | None = None
    anthropic_complex_model: str | None = None
    root_dir: Path = Field(default_factory=repository_root)

    @property
    def config_dir(self) -> Path:
        return self.root_dir / "config"

    @property
    def published_dir(self) -> Path:
        return self.root_dir / "data" / "published"

    @property
    def generated_dir(self) -> Path:
        return self.root_dir / "data" / "generated"
