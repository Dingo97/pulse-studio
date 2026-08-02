from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env")

    name: str = "Pulse Studio"
    data_dir: Path = Path("data")
    max_upload_mb: int = 800
    render_concurrency: int = 1
    models_dir: Path = Path("models")
    whisper_model: str = "large-v3"
    whisper_language: str = "it"
    demucs_model: str = "htdemucs"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "pulse-studio.db"

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


settings = Settings()
