# Backends and factory

The concrete backends a session runs over, and the factory that builds sessions
from configuration. See the [Backends guide](../guide/backends.md) for the
concepts.

## Backends

```python
from storix.backends import LocalBackend, MemoryBackend
from storix.backends import AzureBackend       # requires the 'azure' extra
from storix.backends import AzureBlobBackend   # 'azure' extra (or lean 'azblob')
from storix.backends import S3Backend          # requires the 's3' extra
from storix.backends import GcsBackend         # requires the 'gcs' extra
```

### `LocalBackend`

```python
LocalBackend(base: StrPathLike = "~/.storix")
```

Real files on disk, anchored at `base` (created if missing). Inside the session,
`/` is `base`.

### `MemoryBackend`

```python
MemoryBackend()
```

An in-process, dict-backed store. Touches nothing on disk. The reference backend,
ideal for tests.

### `AzureBackend`

```python
AzureBackend(
    container: str,
    *,
    account_name: str,
    credential: ...,
    read_chunk_size: int = 4 * 1024 * 1024,
    write_chunk_size: int = 4 * 1024 * 1024,
    read_prefetch_size: int = 32 * 1024 * 1024,
)
```

Azure Data Lake Gen2, hierarchical-namespace accounts only. Advertises the
`content_type`, `custom_metadata`, and `presigned_urls` capabilities. Transfer
sizes are bytes and must be positive. The read chunk size configures the SDK's
range requests and the backend's default consumer maximum; the prefetch size is
the SDK's initial download request. The write chunk size controls sequential
`append_data` request batches.

### `AzureBlobBackend`

```python
AzureBlobBackend(
    container: str,
    *,
    account_name: str,
    credential: str | None = None,
    endpoint: str | None = None,
    root: str = "/",
)
```

Azure Blob Storage over the plain blob endpoint: works on any storage account,
flat (portal-default) accounts included. For HNS accounts, `AzureBackend`
offers richer semantics (atomic renames, true appends) over the Data Lake
endpoint. `credential` takes a SAS token or an account key (distinguished
automatically); `None` means anonymous access for public containers.
Advertises `custom_metadata` and `content_type` always, and `presigned_urls`
when the credential is a SAS token (a bare account key cannot mint one here).
Construction is configuration-only; credentials are validated on first I/O.

### `S3Backend`

```python
S3Backend(
    bucket: str,
    *,
    region: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    endpoint: str | None = None,
    root: str = "/",
)
```

Amazon S3, and S3-compatible stores (MinIO, R2, ...) via `endpoint`. The bucket
anchors the session's `/`; `root` optionally narrows it to a key prefix, like
`LocalBackend`'s base directory. Credentials and region omitted here resolve
through the standard AWS chain (environment, profile, IAM role). Advertises the
`presigned_urls`, `custom_metadata`, and `content_type` capabilities.
Construction is configuration-only; credentials are validated on first I/O.

### `GcsBackend`

```python
GcsBackend(
    bucket: str,
    *,
    credential: str | None = None,
    credential_path: str | None = None,
    endpoint: str | None = None,
    root: str = "/",
)
```

Google Cloud Storage. `credential` takes service-account JSON as a string,
`credential_path` a path to the file; omitting both resolves through Google's
application default credentials. Advertises the same capabilities as
`S3Backend`, with the same construction-time behavior.

`AzureBlobBackend`, `S3Backend`, and `GcsBackend` are powered internally by
[Apache OpenDAL](https://opendal.apache.org); the `storix[azblob]`,
`storix[s3]`, and `storix[gcs]` extras install its engine wheel.

## Factory

```python
from storix import get_storage, register_backend, available_providers
```

### `get_storage`

```python
get_storage(provider: str | None = None, /, **overrides) -> Storix
```

Build a session. With no argument, the provider comes from `STORIX_PROVIDER`
(default `local`) and each backend reads its `STORIX_<PROVIDER>_*` environment
values. Keyword `overrides` win over the environment, and each key mirrors the
backend's constructor argument. The memory provider takes no overrides and has
no environment settings.

```python
get_storage()                         # env-driven
get_storage("local", base="~/storix-data")   # explicit + typed override
get_storage("memory")                 # zero-config, in-process, disposable
get_storage("azure")                  # reads STORIX_AZURE_*, detects the kind
get_storage("azure", kind="blob")     # same schema, detection skipped
get_storage("s3", bucket="my-bucket")        # reads STORIX_S3_*
get_storage("gcs", bucket="my-bucket")       # reads STORIX_GCS_*
```

The `azure` provider serves both Azure backends from one `STORIX_AZURE_*`
schema: container, account name, and credential are symmetric, and the
default `kind="auto"` (env `STORIX_AZURE_KIND`) reads the account
properties once to pick the surface - HNS accounts get `AzureBackend`,
flat accounts get `AzureBlobBackend` - and caches the result per account
for the life of the process, so only the first construction pays the
request. The request is synchronous; inside a running event loop, prefer
an explicit `kind` or build sessions at startup. Set `kind="adls"` or
`kind="blob"` to skip detection entirely; that is required when the
credential cannot read account properties (container-scoped SAS, anonymous
access to a public container). The blob kind additionally honors `endpoint`
(emulators, sovereign clouds) and tolerates a missing `credential`.

### `register_backend`, `available_providers`

```python
register_backend(name: str, builder: Callable[..., StorageBackend]) -> None
available_providers() -> tuple[str, ...]
```

Register a third-party backend builder so `get_storage("name", ...)` can build
it, and list the known providers. A backend class is itself a valid builder.
