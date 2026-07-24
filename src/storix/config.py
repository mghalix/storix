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
    DEFAULT_READ_CHUNK_SIZE,
    DEFAULT_TRANSFER_RANGES,
    DEFAULT_WRITE_CHUNK_SIZE,
)
from storix.types import StorageProvider


class StorixSettings(BaseSettings):
    """Top-level selection: which backend ``get_storage()`` builds."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix='STORIX_', env_file='.env', extra='ignore'
    )

    provider: StorageProvider = 'local'
    """Which backend ``get_storage()`` builds when none is named."""

    max_transfer_ranges: int = Field(default=DEFAULT_TRANSFER_RANGES, ge=1)
    """Ceiling on how many ranges of one file a bulk transfer may open.

    Range parallelism makes a single large file transfer at more than one
    connection's speed, at the cost of one request per range (ADR 0032).
    Set ``STORIX_MAX_TRANSFER_RANGES=1`` to keep every transfer on one
    stream per file, which is what a provider quota or a
    transaction-sensitive bill may prefer."""


class TransferConfig(BaseSettings):
    """Transfer sizes every provider understands.

    Inherited by each provider's settings, so the same two knobs are
    spelled ``STORIX_LOCAL_READ_CHUNK_SIZE``, ``STORIX_S3_READ_CHUNK_SIZE``,
    and so on. Sizes are in bytes and must be positive. What they trade
    against each other (memory per in-flight transfer against requests per
    byte) is documented in the Tune transfers recipe.
    """

    read_chunk_size: int = Field(default=DEFAULT_READ_CHUNK_SIZE, gt=0)
    """Maximum chunk a read yields, and the engine's read request size."""

    write_chunk_size: int = Field(default=DEFAULT_WRITE_CHUNK_SIZE, gt=0)
    """Batch size a write accumulates before sending a request."""


class RemoteTransferConfig(TransferConfig):
    """Transfer sizes for providers that fetch over the network."""

    read_prefetch_size: int | None = Field(default=None, gt=0)
    """Size of a stream's opening read, which is the buffer a download holds
    before it yields anything. ``None`` means the read chunk size, so a
    stream costs one chunk; a larger value trades resident memory per
    in-flight transfer for fewer round trips on a lone stream."""


class LocalConfig(TransferConfig):
    """``STORIX_LOCAL_*`` settings for the real-disk backend."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix='STORIX_LOCAL_', env_file='.env', extra='ignore'
    )

    base: str = '~/.storix'
    """Base directory anchoring the filesystem (created if missing)."""


class S3Config(RemoteTransferConfig):
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


class GcsConfig(RemoteTransferConfig):
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


class AzureConfig(RemoteTransferConfig):
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
    """Default consumer and SDK range chunk size in bytes (4 MiB, the SDK's
    own native download chunk)."""

    write_chunk_size: int = Field(default=DEFAULT_AZURE_WRITE_CHUNK_SIZE, gt=0)
    """Default append-request batch size in bytes (4 MiB)."""

    read_prefetch_size: int | None = Field(
        default=DEFAULT_AZURE_READ_PREFETCH_SIZE, gt=0
    )
    """Initial SDK download request size in bytes (8 MiB)."""
