"""Configure storix from settings.

get_storage is already settings-driven: it reads STORIX_PROVIDER and the
STORIX_<PROVIDER>_* variables (or a .env file) through pydantic-settings, so the
zero-code path is environment variables. To keep storage config next to the rest
of your app config, wrap it in your own BaseSettings and pass overrides, which
win over the environment.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from storix import Storix, get_storage


def from_env() -> Storix:
    # Set STORIX_PROVIDER=azure, STORIX_AZURE_CONTAINER=..., etc. (or a .env
    # file), and get_storage picks them up with no code.
    return get_storage()


class Settings(BaseSettings):
    """Storage config kept alongside the rest of the app's settings."""

    model_config = SettingsConfigDict(env_prefix='APP_', env_file='.env')

    storage_base: str = '~/app-data'


@lru_cache
def get_settings() -> Settings:
    """Build application settings once per process."""
    return Settings()


@lru_cache
def get_fs() -> Storix:
    """Build one shared storage session from the application settings."""
    settings = get_settings()
    # Overrides beat the environment; each key mirrors the backend's kwarg.
    return get_storage('local', base=settings.storage_base)
