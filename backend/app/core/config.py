"""Application settings, loaded from environment variables (or a `.env` file).

Every setting the app needs is declared here, with validation. If a required
setting is missing or invalid, the app stops at startup with a clear message
instead of failing later in a confusing way.
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(StrEnum):
    """Where the app is running. Controls safety defaults."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """All runtime configuration. Field names map to UPPER_CASE env variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "GeoInfraLens AI"
    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")

    # Required: there is no safe default for where the data lives.
    database_url: str = Field(
        min_length=1,
        description="SQLAlchemy URL, e.g. postgresql+psycopg://user:pass@db:5432/geoinfralens",
    )
    redis_url: str = Field(
        min_length=1,
        description="Valkey/Redis URL for the job queue, e.g. redis://queue:6379/0",
    )

    # Private folder for uploaded photos and generated exports. Never served directly.
    storage_dir: Path = Path("/data/storage")

    # Seconds to wait when checking whether the database / queue is reachable.
    dependency_check_timeout_seconds: int = Field(default=3, ge=1, le=30)

    # --- Sign-in and security ---
    # The address people use to open the app. Used to build invite/reset links and to
    # reject data-changing requests that come from other websites (Origin check).
    public_app_url: str = Field(default="http://localhost:5173", pattern=r"^https?://[^/]+$")
    session_cookie_name: str = "geoinfralens_session"
    # Browsers treat http://localhost as secure, so this can stay true in development.
    session_cookie_secure: bool = True
    # A session ends after this many hours without activity.
    session_idle_hours: int = Field(default=12, ge=1, le=24 * 30)
    invitation_lifetime_days: int = Field(default=7, ge=1, le=30)
    password_reset_lifetime_minutes: int = Field(default=60, ge=5, le=24 * 60)
    # Sign-in lockout: this many failed attempts for one email within the window blocks
    # further attempts until the window passes.
    sign_in_max_failures: int = Field(default=5, ge=1, le=100)
    sign_in_failure_window_minutes: int = Field(default=15, ge=1, le=24 * 60)

    # --- Photo uploads (placeholder values until the customer confirms PI-03, PI-15) ---
    max_upload_mb: int = Field(default=20, ge=1, le=200)
    # Sharpness below this (variance of the Laplacian) is flagged "blurry".
    blur_threshold: float = Field(default=100.0, ge=0)
    # Average brightness (0-255) below this is flagged "too_dark".
    darkness_threshold: float = Field(default=40.0, ge=0, le=255)
    # Longest side of the smaller preview image shown on screens.
    preview_max_px: int = Field(default=1024, ge=128, le=4096)
    # AI model version used for new analyses (app/ai/registry.py). "stand-in-0.1" is the
    # labelled test detector until a real model passes its accuracy check (PI-17).
    analysis_model_version: str = Field(default="stand-in-0.1", min_length=1, max_length=60)
    # Folder with trained model files (read-only). A trial or real model is used only when
    # ANALYSIS_MODEL_VERSION names it; "stand-in-0.1" (the test detector) needs no file.
    ai_models_dir: Path = Path("/models")

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnvironment.PRODUCTION


class ConfigurationError(RuntimeError):
    """Raised when settings are missing or invalid at startup."""


@lru_cache
def get_settings() -> Settings:
    """Return the settings, loaded once and cached.

    Raises:
        ConfigurationError: if a required variable is missing or invalid. The
            message lists each problem so it can be fixed in `.env`.
    """
    try:
        return Settings()  # values come from the environment
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in err['loc']).upper()}: {err['msg']}"
            for err in exc.errors()
        )
        raise ConfigurationError(
            f"Invalid configuration. Check your .env file. Problems: {problems}"
        ) from exc
