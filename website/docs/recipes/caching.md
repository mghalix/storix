# Cache with Redis or disk

The `CacheLayer` store is a structural four-method protocol: `get`, `set`,
`delete`, and `delete_match`. Use [Cashews](https://github.com/Krukov/cashews)
directly with async storix, or adapt an existing cache client in a few methods.

## Cashews with async storix

`cashews.Cache` already has the asynchronous method shapes required by
`storix.aio.CacheStore`, so it needs no adapter. Configure it with Redis for a
cache shared across processes or with disk storage for a cache that survives
restarts:

```bash
uv add "cashews[redis]"
```

```python
--8<-- "samples/recipes/caching_redis.py"
```

Cashews is asynchronous. Its object does not directly satisfy the synchronous
`storix.CacheStore`, whose methods are called rather than awaited.

## Raw redis-py with sync storix

The raw [redis-py](https://redis.io/docs/latest/develop/clients/redis-py/) API
uses different names and signatures (`ex`/`px`, no `default`, and no
`delete_match`). If your project already uses it, this small adapter is the
complete boundary:

```bash
uv add redis
```

```python
--8<-- "samples/recipes/caching_redis_raw.py"
```

The async equivalent uses `redis.asyncio.Redis` and makes the same four methods
coroutines. The example uses `pickle` because cache values include typed storix
objects as well as bytes and strings. Only unpickle data from a private,
trusted cache; otherwise use an application-specific safe serializer.

## Adapt any cache

Your store does not inherit from a storix class. It only provides these four
methods, synchronously for `storix` or as coroutines for `storix.aio`:

```python
get(key, default=None)
set(key, value, *, expire=None)
delete(key)
delete_match(glob_pattern)
```

`expire` is seconds or `None`; return values are ignored. `delete_match` is used
to evict path subtrees and to clear the layer's namespace. Implement it with a
cursor or scan operation rather than a blocking full key listing.

The store is the only thing that changes; the per-operation options
(`metadata` / `du` / `read` / `url`, each `True` or a `cache(...)` spec) work the
same over any store. See [Layers](../guide/layers.md) for the full set.

!!! warning "Single writer"

    A cache cannot see writes made outside the layer (another process, the cloud
    console). Every write through the layer evicts what it touched, so your own
    session stays consistent, but pass a `ttl` to bound staleness whenever a store
    is shared with writers storix does not control.
