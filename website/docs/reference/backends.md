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
AzureBackend(container: str, *, account_name: str, credential: ...)
```

Azure Data Lake Gen2, hierarchical-namespace accounts only. Advertises the
`content_type`, `custom_metadata`, and `presigned_urls` capabilities.

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
backend's constructor argument.

```python
get_storage()                         # env-driven
get_storage("local", base="~/data")   # explicit + typed override
get_storage("azure")                  # reads STORIX_AZURE_*
```

### `register_backend`, `available_providers`

```python
register_backend(name: str, backend: type[StorageBackend]) -> None
available_providers() -> tuple[str, ...]
```

Register a third-party backend so `get_storage("name", ...)` can build it, and
list the known providers.
