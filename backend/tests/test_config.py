"""Configuration loading tests."""

import pytest

from app.core.config import ConfigurationError, get_settings


def test_missing_required_setting_gives_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL")
    monkeypatch.chdir("/")  # make sure no .env file is picked up
    get_settings.cache_clear()
    try:
        with pytest.raises(ConfigurationError, match="DATABASE_URL"):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_invalid_log_level_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "LOUD")
    get_settings.cache_clear()
    try:
        with pytest.raises(ConfigurationError, match="LOG_LEVEL"):
            get_settings()
    finally:
        get_settings.cache_clear()
