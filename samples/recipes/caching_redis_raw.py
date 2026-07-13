"""Adapt the synchronous redis-py client to storix CacheStore.

CacheLayer stores Python objects, not only byte strings. This compact example
uses pickle and therefore assumes Redis is private and trusted. Use a safer
application-specific serializer when cache writers are not fully trusted.
"""

from __future__ import annotations

import math
import pickle  # noqa: S403 - trusted-cache example, documented above

from typing import Any

from redis import Redis

from storix import CacheLayer, cache, get_storage


class RedisStore:
    """The four synchronous methods required by storix CacheStore."""

    def __init__(self, client: Redis) -> None:
        self._client = client

    def get(self, key: str, default: Any = None) -> Any:
        payload = self._client.get(key)
        if payload is None:
            return default
        return pickle.loads(payload)  # noqa: S301 - trusted-cache example

    def set(self, key: str, value: Any, *, expire: float | None = None) -> None:
        ttl_ms = None if expire is None else max(1, math.ceil(expire * 1000))
        self._client.set(key, pickle.dumps(value), px=ttl_ms)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def delete_match(self, pattern: str) -> None:
        batch_size = 500
        keys: list[bytes] = []
        for key in self._client.scan_iter(match=pattern, count=batch_size):
            keys.append(key)
            if len(keys) == batch_size:
                self._client.unlink(*keys)
                keys.clear()
        if keys:
            self._client.unlink(*keys)


def main() -> None:
    client = Redis.from_url('redis://localhost:6379')
    fs = get_storage('local', base='~/storix-data/cache-recipe').with_layer(
        CacheLayer,
        store=RedisStore(client),
        read=cache(ttl=60, max_bytes=8 * 1024 * 1024),
        environment='prod',
    )
    try:
        fs.echo('cached content', '/example.txt')
        fs.cat('/example.txt')
        fs.cat('/example.txt')
    finally:
        fs.close()
        client.close()


if __name__ == '__main__':
    main()
