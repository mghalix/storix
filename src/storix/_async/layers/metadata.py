"""MetadataLayer: custom metadata via a hidden sidecar."""
# ruff: noqa: A004 - storix error classes intentionally shadow stdlib names

from __future__ import annotations

import dataclasses

from typing import TYPE_CHECKING

from storix._async._stream import validate_chunk_size
from storix.enums import Capability, PathKind
from storix.errors import IsADirectoryError, PathNotFoundError
from storix.serialization import json_dumpb, json_loadb
from storix.types import StorixPath

from .base import LayerBase


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Mapping
    from pathlib import PurePosixPath
    from typing import Any

    from storix.models import Entry, RawStat
    from storix.types import EchoMode

    from ..backends import StorageBackend


class MetadataLayer(LayerBase):
    """Custom metadata for backends without native support, via a sidecar.

    Upgrades ``custom_metadata`` by keeping a hidden JSON table
    (``/.storix-meta.json``) *inside the wrapped backend itself*, so it
    works over any backend and travels with the data. Port semantics are
    preserved exactly (replace; ``{}`` clears; ``None`` preserves on
    append) - the conformance suite runs against this layer.

    Honest limits: the sidecar is last-writer-wins under concurrent
    writers; every stat/metadata operation costs one extra sidecar read;
    external writes that bypass the layer leave stale entries (a delete
    through the layer cleans up). ``copy`` does not carry metadata, per
    the port contract. Prefer native metadata when available::

        fs.with_layer_missing(MetadataLayer)  # capability inferred

    ``serialize``/``deserialize`` swap the sidecar codec (default: stdlib
    json). They are object<->*bytes* callables (not str), so pass
    ``orjson.dumps``/``orjson.loads`` or a custom ``.dumpb``/``.loads`` -
    NOT ``json.dumps`` (which returns str).
    """

    provides = Capability.CUSTOM_METADATA
    _SIDECAR = StorixPath('/.storix-meta.json')

    def __init__(
        self,
        backend: StorageBackend,
        *,
        serialize: Callable[[Any], bytes] = json_dumpb,
        deserialize: Callable[[bytes], Any] = json_loadb,
    ) -> None:
        super().__init__(backend)
        self.capabilities = dataclasses.replace(
            backend.capabilities, custom_metadata=True
        )
        self._serialize = serialize
        self._deserialize = deserialize

    async def _load(self) -> dict[str, dict[str, str]]:
        try:
            raw = await self._inner.read(self._SIDECAR)
        except PathNotFoundError:
            return {}
        return self._deserialize(raw) if raw else {}

    async def _save(self, table: dict[str, dict[str, str]]) -> None:
        if table:
            payload = self._serialize(table)
            await self._inner.write(self._SIDECAR, payload, mode='w', content_type=None)
        elif await self._inner.exists(self._SIDECAR):
            await self._inner.delete(self._SIDECAR)

    async def write_stream(
        self,
        path: PurePosixPath,
        data: AsyncIterator[bytes],
        *,
        chunk_size: int | None = None,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Write content, then maintain the sidecar per port semantics.

        Raises:
            ValueError: If ``chunk_size`` is zero or negative.
        """
        validate_chunk_size(chunk_size)
        await self._inner.write_stream(
            path,
            data,
            chunk_size=chunk_size,
            mode=mode,
            content_type=content_type,
        )
        key = str(path)
        if metadata is None and mode == 'a':
            return  # None preserves on append
        table = await self._load()
        if metadata:
            table[key] = dict(metadata)
        else:  # create/truncate without metadata, or explicit {} clear
            table.pop(key, None)
        await self._save(table)

    async def stat(self, path: PurePosixPath) -> RawStat:
        """Merge sidecar metadata into the inner stat."""
        if path == self._SIDECAR:  # the sidecar is invisible to consumers
            raise PathNotFoundError(path)
        raw = await self._inner.stat(path)
        if raw.kind is not PathKind.FILE:
            return raw
        table = await self._load()
        stored = table.get(str(path))
        return dataclasses.replace(raw, metadata=dict(stored) if stored else None)

    async def read(self, path: PurePosixPath) -> bytes:
        """Read file contents while keeping the sidecar unreadable.

        Raises:
            PathNotFoundError: If ``path`` is the hidden sidecar or is missing.
        """
        if path == self._SIDECAR:
            raise PathNotFoundError(path)
        return await self._inner.read(path)

    async def exists(self, path: PurePosixPath) -> bool:
        """Whether anything lives at ``path`` (the sidecar reads absent)."""
        if path == self._SIDECAR:
            return False
        return await self._inner.exists(path)

    async def read_stream(
        self, path: PurePosixPath, *, chunk_size: int | None = None
    ) -> AsyncIterator[bytes]:
        """Stream file contents while keeping the sidecar unreadable.

        Raises:
            PathNotFoundError: If ``path`` is the hidden sidecar or is missing.
            ValueError: If ``chunk_size`` is zero or negative.
        """
        validate_chunk_size(chunk_size)
        if path == self._SIDECAR:
            raise PathNotFoundError(path)
        async for chunk in self._inner.read_stream(path, chunk_size=chunk_size):
            yield chunk

    async def list_dir(self, path: PurePosixPath) -> AsyncIterator[Entry]:
        """Yield children, hiding the sidecar from its parent directory."""
        async for entry in self._inner.list_dir(path):
            if path / entry.name != self._SIDECAR:
                yield entry

    async def du(self, path: PurePosixPath) -> int:
        """Tree size excluding the sidecar (walks via this layer)."""
        from ..backends import generic

        return await generic.du(self, path)

    async def set_metadata(
        self, path: PurePosixPath, metadata: Mapping[str, str]
    ) -> None:
        """Replace a file's metadata in the sidecar."""
        raw = await self._inner.stat(path)  # raises for missing paths
        if raw.kind is not PathKind.FILE:
            raise IsADirectoryError(path)
        table = await self._load()
        if metadata:
            table[str(path)] = dict(metadata)
        else:
            table.pop(str(path), None)
        await self._save(table)

    async def delete(self, path: PurePosixPath) -> None:
        """Delete the leaf and drop its sidecar entry."""
        await self._inner.delete(path)
        table = await self._load()
        if table.pop(str(path), None) is not None:
            await self._save(table)

    async def delete_tree(self, path: PurePosixPath) -> None:
        """Delete the tree and every sidecar entry beneath it."""
        await self._inner.delete_tree(path)
        prefix = str(path).rstrip('/') + '/'
        table = await self._load()
        kept = {
            key: value
            for key, value in table.items()
            if key != str(path) and not key.startswith(prefix)
        }
        if kept != table:
            await self._save(kept)

    async def move(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Move content and re-key sidecar entries (trees included)."""
        await self._inner.move(src, dst)
        src_key, dst_key = str(src), str(dst)
        src_prefix = src_key.rstrip('/') + '/'
        table = await self._load()
        moved: dict[str, dict[str, str]] = {}
        for key in list(table):
            if key == src_key:
                moved[dst_key] = table.pop(key)
            elif key.startswith(src_prefix):
                moved[dst_key + key.removeprefix(src_key)] = table.pop(key)
        if moved:
            table.update(moved)
            await self._save(table)
