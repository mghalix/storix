# Layers

A layer is a backend that wraps another backend. Because it implements the same
`StorageBackend` port, it composes with backends and with other layers, the way
middleware wraps a web app. Layers are how storix adds cross-cutting behavior
(sandboxing, caching, capability backfill) without touching the core or the
backends.

```python
from storix import Storix, SandboxLayer
from storix.backends import LocalBackend

backend = LocalBackend("~/storix-data")
host = Storix(backend)
host.mkdir("/tenant-42", parents=True)

fs = Storix(SandboxLayer(backend, root="/tenant-42"))
```

You can also add layers fluently, which returns a new session and leaves the
original untouched:

```python
fs = host.with_layer(SandboxLayer, root="/tenant-42")
```

The sandbox root must exist before the layer is composed. This is deliberate:
constructing a layer does not mutate its backend, and provisioning remains an
explicit operation on the unsandboxed session.

## Sandbox: chroot as middleware

`SandboxLayer` confines a session beneath a virtual root. Inside it, `/` means
the root, and traversal cannot escape, even if a caller tries to bypass the core
with `..`. Errors are re-scoped to the virtual namespace, so the real path prefix
never leaks. A sandboxed session simply cannot see or reach anything above its
root, which makes it a real security boundary, not a convenience.

```python
host.echo("outside the tenant", "/secrets.txt")
fs.touch("hi.txt")
fs.cat("../secrets.txt")  # raises PathNotFoundError, not a jailbreak
```

The real `/secrets.txt` exists outside `/tenant-42`. The `..` is clamped at the
sandbox root, so the lookup stays inside the tenant and cannot reach it.

## Cache: read-through, opt-in per operation

`CacheLayer` caches the operations that repeat. Metadata (`stat`/`ls`/`exists`)
is cached by default; the expensive tree walk (`du`), file content (`read`), and
presigned URLs are opt-in. Every write through the layer evicts what it touched,
so you always see your own changes.

```python
from storix import CacheLayer, cache, get_storage

fs = get_storage("azure").with_layer(
    CacheLayer,
    du=cache(ttl=60),                 # opt in; the tree walk is the big win
    read=cache(max_bytes=8 * 1024 * 1024),  # content, capped at 8 MiB per file
)
```

The store protocol deliberately matches
[Cashews](https://github.com/Krukov/cashews), so a `cashews.Cache` plugs into the
async flavor with no adapter and can use Redis or disk underneath. The raw
[redis-py](https://redis.io/docs/latest/develop/clients/redis-py/) client has a
different API; use it through Cashews or provide a small adapter. Correctness
assumes you are the only writer; pass a `ttl` to bound staleness. The
[cache recipe](../recipes/caching.md) covers both Cashews and raw redis-py.

## Progress: transfer events, not callbacks

`ObservabilityLayer` turns the byte streams into progress. Every chunk that
moves through `read_stream`/`write_stream` emits a `TransferEvent` (`op`,
`path`, cumulative `transferred`) to the sink you attach; the sink may be
sync or async:

```python
from storix import ObservabilityLayer, get_storage

fs = get_storage("local").with_layer(ObservabilityLayer, sink=print)
fs.echo(chunks, "/upload.bin")
# TransferEvent(op='write', path=StorixPath('/upload.bin'), transferred=65536)
# TransferEvent(op='write', path=StorixPath('/upload.bin'), transferred=131072)
# ...
```

The events deliberately carry no total and no percentage. A total is never
storix's to know: an arbitrary write stream has no knowable end. It is the
caller's knowledge of their own source (a local file's `stat().st_size`, an
HTTP upload's `Content-Length`), so you supply the total and do the division.
With no sink the layer is a pure passthrough. Compose it outermost so it
counts the full logical transfer. The
[progress bars recipe](../recipes/progress.md) drives a real bar from it.

## Portable capabilities

Some layers backfill a capability a backend lacks, so one code path spans
providers. `with_layer_missing` applies a layer only when the backend is not
already native, inferring the capability from the layer:

```python
from storix import DataUrlLayer, MetadataLayer, get_storage

fs = (
    get_storage("local")
    .with_layer_missing(DataUrlLayer)    # url() everywhere: SAS on azure, data: URL on local
    .with_layer_missing(MetadataLayer)   # custom metadata everywhere
)
```

Switch `local` to `azure` and the native capability wins, so the layer becomes a
no-op. No code changes.

## Bypassing a layer

`without_layer` returns a session with a layer type stripped, and `uncached` is
sugar for dropping the cache, which is handy for a guaranteed-fresh read:

```python
fs.uncached.ls("/live")                 # bypass the cache for this read
fs.without_layer(CacheLayer).du("/big")
```

A `SandboxLayer` is deliberately non-removable. You can always ask for less
caching; you can never ask your way out of a security boundary.

To build middleware of your own, see the runnable
[custom layer recipe](../recipes/custom-layer.md).
