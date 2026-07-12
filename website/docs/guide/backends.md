# Backends

A backend is what a session actually reads and writes. Storix ships three, and
the same session code runs over any of them.

| Backend | Import | Use it for |
| --- | --- | --- |
| `LocalBackend` | `storix.backends.LocalBackend` | real files on disk, anchored at a base directory |
| `MemoryBackend` | `storix.backends.MemoryBackend` | tests and scratch work; nothing touches disk |
| `AzureBackend` | `storix.backends.AzureBackend` | Azure Data Lake Gen2 (hierarchical namespace accounts) |

```python
from storix import Storix
from storix.backends import LocalBackend, MemoryBackend

Storix(LocalBackend("~/data"))   # '/' is ~/data
Storix(MemoryBackend())          # in-process, disposable
```

## The port

Every backend implements one small interface, the `StorageBackend` port (about
14 methods: read, write, list, stat, and friends). The core `Storix` engine owns
all the unix behavior (cwd, path resolution, `mv` as copy-plus-delete, and so on)
and calls only that port. Backends do no path logic and raise only
`storix.errors`.

That boundary is why swapping backends changes nothing above it, and why a new
provider is just a new class that implements the port. You can register your own:

```python
from storix import register_backend

register_backend("myprovider", MyBackend)
```

## Configuration and the factory

`get_storage` builds a session from the environment, so application code does not
hard-code a provider:

```python
from storix import get_storage

fs = get_storage()              # provider from STORIX_PROVIDER (default: local)
fs = get_storage("local", base="~/data")   # explicit, with typed overrides
fs = get_storage("azure")       # reads STORIX_AZURE_* from the environment
```

Configuration is namespaced under `STORIX_`:

```bash
STORIX_PROVIDER=azure
STORIX_AZURE_CONTAINER=raw
STORIX_AZURE_ACCOUNT_NAME=myaccount
STORIX_AZURE_CREDENTIAL=...
# for local:
STORIX_LOCAL_BASE=~/data
```

Overrides passed to `get_storage` win over the environment, and every backend
config field mirrors its constructor keyword, so the env key always matches the
argument name.

## Capabilities

Backends differ in what they can do. Azure can mint presigned URLs and store
custom metadata; local disk cannot. Storix makes those differences explicit
rather than silent: a backend advertises `capabilities`, and asking for one it
lacks raises `UnsupportedOperationError` naming the missing capability instead of
quietly dropping your argument.

```python
fs.url("/f.png", expires_in=600)   # presigned SAS on azure; raises on plain local
fs.data_url("/f.png")              # a base64 data: URL, works on any backend
```

[Layers](layers.md) can backfill some of these capabilities so one code path
works across providers.
