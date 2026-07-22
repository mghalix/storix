# Write a custom backend

A backend implements the 18-method `StorageBackend` port (read, write, list,
stat, and friends) and nothing else. The core `Storix` engine owns all the
unix behavior, so a backend does no path logic and raises only `storix.errors`.
That is why a new provider is just a new class, and everything above it (the CLI,
every layer, the whole session API) works over it unchanged.

Subclass `BackendBase` to inherit generic operations. Implement the four
structural methods (`delete`, `list_dir`, `stat`, and `make_dir`) plus at least
one method from each I/O pair:

- `read()` or `read_stream()`
- `write()` or `write_stream()`

Choose independently per direction. A simple database or dict backend can
implement whole-object `read()` and `write()`; the base supplies compatibility
stream fallbacks. A cloud or filesystem backend should implement its native
stream methods to keep memory bounded. If neither member of a pair is present,
the base raises a clear `NotImplementedError` instead of recursing.

`StorageBackend` itself is a `Protocol`, so inheritance is never required. A
class with the complete matching method surface can be passed to `Storix` or
returned by a registered builder through structural typing. `BackendBase` is
still the recommended starting point because it supplies the generic operations
and the whole-object/streaming fallbacks instead of making you implement all 18
methods.

`BackendBase.list_tree()` is an unsupported default, so subclasses do not
override it unless they can recursively list a directory cheaply. A backend
that provides that fast path implements `list_tree()`, advertises
`capabilities.bulk_listing`, and passes the capability-gated conformance tests.
The core otherwise uses its portable concurrent fallback. A structurally typed
backend that does not inherit `BackendBase` still needs the complete 18-method
surface, even when its `list_tree()` implementation only raises
`UnsupportedOperationError` and `bulk_listing` stays false.

Then register a builder so `get_storage` can construct it by name:

```python
from storix import register_backend
from storix.backends import BackendBase


class MyBackend(BackendBase):
    ...  # implement six methods; MemoryBackend is the streaming template


register_backend('myprovider', MyBackend)
```

The streaming signatures include the backend control explicitly:

```python
def read_stream(path, *, chunk_size: int | None = None) -> Iterator[bytes]: ...
def write_stream(
    path,
    data: Iterator[bytes],
    *,
    chunk_size: int | None = None,
    mode: EchoMode,
    content_type: str | None,
    metadata: Mapping[str, str] | None = None,
) -> None: ...
```

For reads, `chunk_size` is a maximum output size: split oversized provider
chunks but do not delay smaller chunks to fill it. For writes, it is the target
provider batch: combine tiny source yields and split oversized ones. `None`
selects the backend's preferred default, while zero and negative values raise
`ValueError`. Source iterator boundaries have no storage meaning.

See the runnable
[`samples/plugins/byo_backend.py`](https://github.com/mghalix/storix/blob/main/samples/plugins/byo_backend.py)
for a whole-object backend that gets both streaming forms from `BackendBase`.

```python
from storix import get_storage

fs = get_storage('myprovider', ...)   # your overrides map to MyBackend's kwargs
```

!!! note "Async and sync"

    storix generates its sync flavor from an async source of truth. A third-party
    backend can implement either flavor's port; the two are structurally identical
    apart from `async` and `await`. If you want both, keep the async version as the
    source and mirror it, the way storix does with `scripts/unasync.py`.
