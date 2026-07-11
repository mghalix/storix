"""Generic fallback implementations for the native-fast-path port operations.

Free functions taking the backend as first argument, so backends that do
not subclass :class:`~storix._async.backends.BackendBase` can still
delegate: ``await generic.move(self, src, dst)``. They speak only through
the port's primitives and rely on its error contract (storix errors only).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from storix._async._stream import collect
from storix.enums import PathKind
from storix.errors import PathNotFoundError


if TYPE_CHECKING:
    from pathlib import PurePosixPath

    from ._proto import StorageBackend


async def read(backend: StorageBackend, path: PurePosixPath) -> bytes:
    """Collect ``read_stream`` into the full file contents."""
    return await collect(backend.read_stream(path))


async def move(backend: StorageBackend, src: PurePosixPath, dst: PurePosixPath) -> None:
    """Move a single file as copy-then-delete."""
    await backend.copy(src, dst)
    await backend.delete(src)


async def copy(backend: StorageBackend, src: PurePosixPath, dst: PurePosixPath) -> None:
    """Copy a single file by streaming its chunks into a truncating write."""
    data = backend.read_stream(src)
    await backend.write(dst, data, mode='w', content_type=None)


async def delete_tree(backend: StorageBackend, path: PurePosixPath) -> None:
    """Delete ``path`` and everything below it, children first."""
    # TODO(codegen): parallelize via _compat.gather once the shim exists
    async for entry in backend.list_dir(path):
        item = path / entry.name
        delete_fn = backend.delete_tree if entry.is_dir else backend.delete
        await delete_fn(item)

    await backend.delete(path)


async def du(backend: StorageBackend, path: PurePosixPath) -> int:
    """Sum the sizes of the tree rooted at ``path``.

    Uses listing-provided sizes when available; falls back to a per-file
    ``stat`` otherwise.
    """
    props = await backend.stat(path)
    if props.kind is PathKind.FILE:
        return props.size

    size = 0
    # TODO(codegen): parallelize via _compat.gather once the shim exists
    async for entry in backend.list_dir(path):
        child = path / entry.name
        if entry.is_dir:
            size += await backend.du(child)
        else:
            size += (
                entry.size
                if entry.size is not None
                else (await backend.stat(child)).size
            )
    return size


async def exists(backend: StorageBackend, path: PurePosixPath) -> bool:
    """Derive existence from ``stat`` and the port's error contract."""
    try:
        await backend.stat(path)
    except PathNotFoundError:
        return False
    return True
