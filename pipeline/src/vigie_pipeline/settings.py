"""Configuration d’exécution provenant de l’environnement et des YAML."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Paramètres sûrs; aucune valeur secrète n’est journalisée."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    anthropic_api_key: str | None = Field(default=None, repr=False)
    anthropic_standard_model: str = "claude-sonnet-4-20250514"
    anthropic_complex_model: str = "claude-opus-4-20250514"
    request_timeout_seconds: float = 20.0
    request_attempts: int = 3
    max_download_bytes: int = 15_000_000
    llm_max_input_chars: int = 80_000
    delta_tolerance: float = 0.03
    minimum_observations: int = 64
    maximum_volume_drop: float = 0.1
    root_dir: Path = Field(default_factory=repository_root)

    @field_validator("anthropic_standard_model", "anthropic_complex_model", mode="before")
    @classmethod
    def use_default_model_for_empty_variable(cls, value: object, info: object) -> object:
        if value != "":
            return value
        field_name = getattr(info, "field_name", "")
        if field_name == "anthropic_standard_model":
            return "claude-sonnet-4-20250514"
        return "claude-opus-4-20250514"

    @property
    def config_dir(self) -> Path:
        return self.root_dir / "config"

    @property
    def published_dir(self) -> Path:
        return self.root_dir / "data" / "published"

    @property
    def generated_dir(self) -> Path:
        return self.root_dir / "data" / "generated"
