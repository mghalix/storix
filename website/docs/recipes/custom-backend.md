# Write a custom backend

A backend implements the `StorageBackend` port (about 14 methods: read, write,
list, stat, and friends) and nothing else. The core `Storix` engine owns all the
unix behavior, so a backend does no path logic and raises only `storix.errors`.
That is why a new provider is just a new class, and everything above it (the CLI,
every layer, the whole session API) works over it unchanged.

The fastest way to write one is to copy `MemoryBackend`, the reference backend,
and swap its dict for your store. Then register it so `get_storage` can build it
by name:

```python
from storix import register_backend
from storix.backends import StorageBackend


class MyBackend(StorageBackend):
    ...  # implement the port; use storix.backends.MemoryBackend as the template


register_backend('myprovider', MyBackend)
```

```python
from storix import get_storage

fs = get_storage('myprovider', ...)   # your overrides map to MyBackend's kwargs
```

!!! note "Async and sync"

    storix generates its sync flavor from an async source of truth. A third-party
    backend can implement either flavor's port; the two are structurally identical
    apart from `async` and `await`. If you want both, keep the async version as the
    source and mirror it, the way storix does with `scripts/unasync.py`.
