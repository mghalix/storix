"""Standardized, namespaced configuration for storix backends.

One brand prefix, one model per backend: ``STORIX_PROVIDER`` picks the
backend, ``STORIX_<PROVIDER>_*`` configures it, and every field can be
overridden per-call through ``get_storage(**overrides)``. Values are
read from the environment and a local ``.env`` file.
"""

from typing import ClassVar, Literal

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


class S3Config(BaseSettings):
    """``STORIX_S3_*`` settings for the Amazon S3 backend."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix='STORIX_S3_', env_file='.env', extra='ignore'
    )

    bucket: str | None = None
    """Bucket anchoring the session; required."""

    region: str | None = None
    """Bucket region; defaults to the standard AWS environment/config chain."""

    access_key_id: str | None = None
    """Static access key; omitted means the standard AWS credential chain."""

    secret_access_key: str | None = None
    """Secret for ``access_key_id``."""

    endpoint: str | None = None
    """Custom endpoint URL for S3-compatible stores (MinIO, R2, ...)."""

    root: str = '/'
    """Key prefix anchoring the session's ``/`` inside the bucket."""


class GcsConfig(BaseSettings):
    """``STORIX_GCS_*`` settings for the Google Cloud Storage backend."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix='STORIX_GCS_', env_file='.env', extra='ignore'
    )

    bucket: str | None = None
    """Bucket anchoring the session; required."""

    credential: str | None = None
    """Service-account JSON as a string; omitted means Google's default chain."""

    credential_path: str | None = None
    """Path to a service-account JSON file."""

    endpoint: str | None = None
    """Custom endpoint URL for GCS-compatible stores and emulators."""

    root: str = '/'
    """Key prefix anchoring the session's ``/`` inside the bucket."""


class AzureConfig(BaseSettings):
    """``STORIX_AZURE_*`` settings for both Azure backends.

    One schema serves both account kinds: container, account name, and
    credential are all it takes. The default ``kind='auto'`` detects
    whether the account has hierarchical namespaces (one
    account-properties request at build time) and picks the surface:
    the native Data Lake Gen2 backend (atomic renames, true appends)
    for HNS accounts, the blob-endpoint backend for flat ones.
    """

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix='STORIX_AZURE_', env_file='.env', extra='ignore'
    )

    kind: Literal['auto', 'adls', 'blob'] = 'auto'
    """Which Azure surface to speak: detected from the account by
    default. Set ``'adls'`` or ``'blob'`` explicitly to skip the
    detection request - required when the credential cannot read
    account properties (container-scoped SAS, anonymous access)."""

    container: str | None = None
    """Container (filesystem) name; required."""

    account_name: str | None = None
    """Storage account name; required. The adls kind needs HNS enabled."""

    credential: str | None = None
    """SAS token or account key; required for adls, optional for blob
    (``None`` means anonymous access to a public container)."""

    endpoint: str | None = None
    """Custom blob endpoint URL (emulators, sovereign clouds); blob kind only."""

    read_chunk_size: int = Field(default=DEFAULT_AZURE_READ_CHUNK_SIZE, gt=0)
    """Default consumer and SDK range chunk size in bytes."""

    write_chunk_size: int = Field(default=DEFAULT_AZURE_WRITE_CHUNK_SIZE, gt=0)
    """Default append-request batch size in bytes."""

    read_prefetch_size: int = Field(default=DEFAULT_AZURE_READ_PREFETCH_SIZE, gt=0)
    """Initial SDK download request size in bytes."""
