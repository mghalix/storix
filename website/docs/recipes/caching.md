# Cache with Redis or disk

The `CacheLayer` store is a small protocol (`get` / `set` / `delete` /
`delete_match`) deliberately shaped like
[Cashews](https://github.com/Krukov/cashews), so a `cashews.Cache` plugs in with
no adapter. Configure Cashews with Redis for a cache shared across processes, or
with a disk backend for one that survives restarts. The raw
[redis-py](https://redis.io/docs/latest/develop/clients/redis-py/) API is not the
same protocol; use it through Cashews or provide a small adapter.

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
