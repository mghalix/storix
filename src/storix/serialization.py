"""Default serialization for layers that persist structured data.

Layers take ``dumps``/``loads`` *callables* rather than a shaped
serializer object, so anything plugs in without matching a method
contract: ``orjson.dumps``/``orjson.loads``, a custom ``serializer.dumpb``
/ ``serializer.loads``, stdlib json, etc. The defaults below use stdlib
json. Shared (flavor-agnostic, not codegen'd).
"""

from __future__ import annotations

import json

from typing import Any


def json_dumpb(obj: Any) -> bytes:
    """Default ``dumps``: serialize to compact UTF-8 JSON bytes."""
    return json.dumps(obj, separators=(',', ':')).encode()


def json_loadb(data: bytes) -> Any:
    """Default ``loads``: deserialize JSON bytes (``json.loads`` accepts bytes)."""
    return json.loads(data)
