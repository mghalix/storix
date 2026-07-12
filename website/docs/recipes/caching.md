# Cache with Redis or disk

The `CacheLayer` store is a small cashews-shaped protocol (`get` / `set` /
`delete` / `delete_match`), so a `cashews.Cache` plugs in with no adapter. Use
Redis for a cache shared across processes, or a disk backend for one that
survives restarts.

```python
--8<-- "samples/recipes/caching_redis.py"
```

The store is the only thing that changes; the per-operation options
(`metadata` / `du` / `read` / `url`, each `True` or a `cache(...)` spec) work the
same over any store. See [Layers](../guide/layers.md) for the full set.

!!! warning "Single writer"

    A cache cannot see writes made outside the layer (another process, the cloud
    console). Every write through the layer evicts what it touched, so your own
    session stays consistent, but pass a `ttl` to bound staleness whenever a store
    is shared with writers storix does not control.
