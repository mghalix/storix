# Backends and factory

The concrete backends a session runs over, and the factory that builds sessions
from configuration. See the [Backends guide](../guide/backends.md) for the
concepts.

## Backends

```python
from storix.backends import LocalBackend, MemoryBackend
from storix.backends import AzureBackend   # requires the 'azure' extra
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
get_storage("azure")                  # reads STORIX_AZURE_*
```

### `register_backend`, `available_providers`

```python
register_backend(name: str, builder: Callable[..., StorageBackend]) -> None
available_providers() -> tuple[str, ...]
```

Register a third-party backend builder so `get_storage("name", ...)` can build
it, and list the known providers. A backend class is itself a valid builder.
