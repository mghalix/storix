"""Standardized, namespaced configuration for storix backends.

One brand prefix, one model per backend: ``STORIX_PROVIDER`` picks the
backend, ``STORIX_<PROVIDER>_*`` configures it, and every field can be
overridden per-call through ``get_storage(**overrides)``. Values are
read from the environment and a local ``.env`` file.
"""

from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from storix.constants import (
    DEFAULT_AZURE_READ_CHUNK_SIZE,
    DEFAULT_AZURE_READ_PREFETCH_SIZE,
    DEFAULT_AZURE_WRITE_CHUNK_SIZE,
)
from storix.types import StorageProvider


class StorixSettings(BaseSettings):
    """Top-level selection: which backend ``get_storage()`` builds."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix='STORIX_', env_file='.env', extra='ignore'
    )

    provider: StorageProvider = 'local'


class LocalConfig(BaseSettings):
    """``STORIX_LOCAL_*`` settings for the real-disk backend."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix='STORIX_LOCAL_', env_file='.env', extra='ignore'
    )

    base: str = '~/.storix'
    """Base directory anchoring the filesystem (created if missing)."""


class AzureConfig(BaseSettings):
    """``STORIX_AZURE_*`` settings for the ADLS Gen2 backend."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix='STORIX_AZURE_', env_file='.env', extra='ignore'
    )

    container: str | None = None
    """Container (filesystem) name; required."""

    account_name: str | None = None
    """Storage account name; required. Must have HNS enabled."""

    credential: str | None = None
    """SAS token or account key; required."""

    read_chunk_size: int = Field(default=DEFAULT_AZURE_READ_CHUNK_SIZE, gt=0)
    """Default consumer and SDK range chunk size in bytes."""

    write_chunk_size: int = Field(default=DEFAULT_AZURE_WRITE_CHUNK_SIZE, gt=0)
    """Default append-request batch size in bytes."""

    read_prefetch_size: int = Field(default=DEFAULT_AZURE_READ_PREFETCH_SIZE, gt=0)
    """Initial SDK download request size in bytes."""
