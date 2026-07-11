"""Pluggable serialization for layers that persist structured data.

Shared (flavor-agnostic, not codegen'd). The default is stdlib ``json``;
users who want speed pass ``orjson`` (or any object exposing bytes-based
``dumps``/``loads``) directly.
"""

from __future__ import annotations

import json

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Serializer(Protocol):
    """Bytes-based ``dumps``/``loads``.

    Bytes, not str, because the storage port speaks bytes. The stdlib
    ``json`` *module* does NOT satisfy this (its ``dumps`` returns str) -
    use :data:`json_serializer`. The ``orjson`` module *does* satisfy it
    and can be passed straight through: ``MetadataLayer(be,
    serializer=orjson)``.
    """

    def dumps(self, obj: Any) -> bytes:
        """Serialize an object to bytes."""
        ...

    def loads(self, data: bytes) -> Any:
        """Deserialize bytes to an object."""
        ...


class JSONSerializer:
    """Default serializer over stdlib ``json`` (str<->bytes bridged)."""

    def dumps(self, obj: Any) -> bytes:
        """Serialize to compact UTF-8 JSON bytes."""
        return json.dumps(obj, separators=(',', ':')).encode()

    def loads(self, data: bytes) -> Any:
        """Deserialize JSON bytes."""
        return json.loads(data)


json_serializer = JSONSerializer()
