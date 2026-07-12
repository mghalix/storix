"""Cache with Redis (or disk) through cashews.

CacheLayer's store is a small cashews-shaped protocol (get / set / delete /
delete_match), so a cashews.Cache plugs in directly. Point it at Redis for a
cache shared across processes, or at a disk backend for one that survives
restarts. Keys are namespaced, so environments never collide in a shared store.
"""

from __future__ import annotations

from cashews import Cache

from storix import CacheLayer, cache, get_storage


store = Cache()
store.setup('redis://localhost:6379')  # or 'disk://.cache' for a local disk cache

fs = get_storage('azure').with_layer(
    CacheLayer,
    store=store,  # a cashews.Cache satisfies the CacheStore protocol as-is
    du=cache(ttl=60),
    read=cache(max_bytes=8 << 20),
    environment='prod',
)
