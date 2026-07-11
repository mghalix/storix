"""Generic fallback implementations for the native-fast-path port operations.

Free functions taking the backend as first argument, so backends that do
not subclass :class:`~storix._async.backends.BackendBase` can still
delegate: ``await generic.move(self, src, dst)``. They speak only through
the port's primitives and rely on its error contract (storix errors only).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from storix._async._compat import gather
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
    """Move a file or a directory tree as copy-then-delete."""
    props = await backend.stat(src)
    if props.kind is PathKind.DIRECTORY:
        await copy_tree(backend, src, dst)
        await backend.delete_tree(src)
        return
    await backend.copy(src, dst)
    await backend.delete(src)


async def copy(backend: StorageBackend, src: PurePosixPath, dst: PurePosixPath) -> None:
    """Copy a single file by streaming its chunks into a truncating write."""
    data = backend.read_stream(src)
    await backend.write(dst, data, mode='w', content_type=None)


async def copy_tree(
    backend: StorageBackend, src: PurePosixPath, dst: PurePosixPath
) -> None:
    """Recursively copy a directory tree, fanning out per level.

    Merge-friendly: existing destination directories are reused
    (``mkdir -p`` semantics), so copying into a populated tree overlays
    rather than fails; an existing *file* at a directory's destination
    still raises ``AlreadyExistsError``.
    """
    await backend.make_dir(dst, parents=True)

    files: list[str] = []
    subdirs: list[str] = []
    async for entry in backend.list_dir(src):
        (subdirs if entry.is_dir else files).append(entry.name)

    await gather(
        *(copy_tree(backend, src / subdir, dst / subdir) for subdir in subdirs),
        *(backend.copy(src / file, dst / file) for file in files),
    )


async def delete_tree(backend: StorageBackend, path: PurePosixPath) -> None:
    """Delete ``path`` and everything below it, children first.

    Siblings are deleted concurrently (bounded per tree level by the
    ``gather`` shim); the directory itself goes last, once empty.
    """
    files: list[PurePosixPath] = []
    subdirs: list[PurePosixPath] = []
    async for entry in backend.list_dir(path):
        (subdirs if entry.is_dir else files).append(path / entry.name)

    await gather(
        *(backend.delete_tree(subdir) for subdir in subdirs),
        *(backend.delete(file) for file in files),
    )
    await backend.delete(path)


async def du(backend: StorageBackend, path: PurePosixPath) -> int:
    """Sum the sizes of the tree rooted at ``path``.

    Uses listing-provided sizes when available, falling back to per-file
    ``stat`` calls; stats and subtree walks fan out concurrently (bounded
    per tree level by the ``gather`` shim).
    """
    props = await backend.stat(path)
    if props.kind is PathKind.FILE:
        return props.size

    size = 0
    stat_targets: list[PurePosixPath] = []
    subdirs: list[PurePosixPath] = []
    async for entry in backend.list_dir(path):
        child = path / entry.name
        if entry.is_dir:
            subdirs.append(child)
        elif entry.size is not None:
            size += entry.size
        else:
            stat_targets.append(child)

    stats = await gather(*(backend.stat(target) for target in stat_targets))
    subtotals = await gather(*(backend.du(subdir) for subdir in subdirs))
    return size + sum(s.size for s in stats) + sum(subtotals)


async def exists(backend: StorageBackend, path: PurePosixPath) -> bool:
    """Derive existence from ``stat`` and the port's error contract."""
    try:
        await backend.stat(path)
    except PathNotFoundError:
        return False
    return True
