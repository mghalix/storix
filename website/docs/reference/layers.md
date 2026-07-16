# Layers

Backends that wrap backends. See the [Layers guide](../guide/layers.md) for the
concepts. All are importable from `storix` (and `storix.aio`).

## `SandboxLayer`

```python
SandboxLayer(backend, *, root: StrPathLike)
```

Confine a session beneath `root`, escape-proof. `to_real` / `to_virtual` are the
privileged audit handles. `removable = False`, so `without_layer` can never strip
it.

## `CacheLayer`

```python
CacheLayer(
    backend,
    *,
    metadata: bool | CacheOp = True,
    du: bool | CacheOp = False,
    read: bool | CacheOp = False,
    url: bool | CacheOp = False,
    store: CacheStore | None = None,
    ttl: float | None = None,
    namespace: str = "storix",
    environment: str | None = None,
)
```

Read-through cache. Each operation is `True` (defaults), a `cache(...)` spec, or
`False`. `metadata` is on by default; `du`, `read`, `url` are opt-in. Mutations
through the layer evict what they touch. `clear()` drops everything in the
layer's namespace.

### `cache`, `CacheOp`

```python
cache(*, ttl: float | None = None, store: CacheStore | None = None, max_bytes: int | None = None) -> CacheOp
```

Build a per-operation spec: `du=cache(ttl=60)`,
`read=cache(max_bytes=8 * 1024 * 1024)`.

### `CacheStore`, `InMemoryCacheStore`

```python
class CacheStore(Protocol):   # cashews-shaped: get / set / delete / delete_match
    ...

InMemoryCacheStore(*, maxsize: int | None = None)
```

The pluggable store protocol and its in-memory default (optional `maxsize` for LRU
eviction). A `cashews.Cache` directly satisfies the async flavor. The sync
flavor requires synchronous implementations of the same four methods.

## `ObservabilityLayer`

```python
ObservabilityLayer(backend, *, sink: Callable[[TransferEvent], Any] | None = None)
```

Emit a `TransferEvent` to `sink` for every chunk that moves through
`read_stream`/`write_stream`. The sink may be sync or async (a coroutine
result is awaited per event). With no sink the layer is a pure passthrough.
Removable; compose it outermost so it counts the full logical transfer.

### `TransferEvent`

```python
class TransferEvent:        # frozen, slotted, keyword-only
    op: Literal["read", "write"]
    path: PurePosixPath
    transferred: int        # cumulative bytes for this transfer
```

storix never invents a total: you produced the source, so you own the total
and any percentage. See the [progress bars recipe](../recipes/progress.md).

## `DataUrlLayer`, `MetadataLayer`

```python
DataUrlLayer(backend)
MetadataLayer(backend, *, serialize=..., deserialize=...)
```

Backfill capabilities on backends that lack them: `url()` via base64 `data:` URLs,
and custom metadata via a JSON sidecar. Both declare `provides`, so
`with_layer_missing` applies them only where the backend is not already native.

## `LayerBase`

```python
class LayerBase:
    provides: ClassVar[Capability | None] = None
    removable: ClassVar[bool] = True
```

The delegating base for custom layers. Subclass it, override the operations you
change, and reassign `capabilities` for any you add.
