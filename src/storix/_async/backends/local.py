"""Local filesystem backend (async flavor).

Hand-written twin pair: excluded from codegen because the sync sibling
uses different primitives (open/os/shutil vs aiofiles/to_thread). Keep
``storix._sync.backends.local`` in lockstep by hand; the conformance
suite is the drift guard.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import errno
import os
import shutil
import stat as stat_module

from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles
import aiofiles.os as aioos

from storix.constants import DEFAULT_WRITE_CHUNKSIZE
from storix.enums import PathKind
from storix.errors import PathNotFoundError, from_os_error
from storix.models import Entry, RawStat

from . import generic
from .base import BackendBase


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping
    from pathlib import PurePosixPath

    from storix.types import EchoMode, StrPathLike


def _ts(timestamp: float) -> dt.datetime:
    return dt.datetime.fromtimestamp(timestamp, tz=dt.UTC)


class LocalBackend(BackendBase):
    """Real-disk backend anchored at a base directory.

    The base directory is namespace configuration (the local analog of a
    cloud container): port path ``/x`` maps to ``<base>/x``. The base is
    created at construction if missing. Lexical containment is guaranteed
    by the core's normalization, but symlinks inside the base can still
    point outside it - pair with SandboxLayer when that matters.
    """

    def __init__(self, base: StrPathLike) -> None:
        self._base = Path(base).expanduser().resolve()
        self._base.mkdir(parents=True, exist_ok=True)

    def _to_os(self, path: PurePosixPath) -> Path:
        return self._base.joinpath(*path.parts[1:])

    async def read_stream(self, path: PurePosixPath) -> AsyncIterator[bytes]:
        """Stream a file's contents in chunks."""
        try:
            handle = await aiofiles.open(self._to_os(path), 'rb')
        except OSError as exc:
            raise from_os_error(exc, path) from exc
        try:
            while chunk := await handle.read(DEFAULT_WRITE_CHUNKSIZE):
                yield chunk
        finally:
            await handle.close()

    async def write(
        self,
        path: PurePosixPath,
        data: AsyncIterator[bytes],
        *,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Write a file from a chunk stream ('w' truncates, 'a' appends)."""
        del content_type, metadata  # capabilities not advertised; never sent
        flags = 'wb' if mode == 'w' else 'ab'
        try:
            handle = await aiofiles.open(self._to_os(path), flags)
        except OSError as exc:
            raise from_os_error(exc, path) from exc
        try:
            async for chunk in data:
                await handle.write(chunk)
        finally:
            await handle.close()

    async def delete(self, path: PurePosixPath) -> None:
        """Delete a leaf: a file or an empty directory."""
        raw = await self.stat(path)
        target = self._to_os(path)
        try:
            if raw.kind is PathKind.DIRECTORY:
                await aioos.rmdir(target)
            else:
                await aioos.remove(target)
        except OSError as exc:
            raise from_os_error(exc, path) from exc

    async def list_dir(self, path: PurePosixPath) -> AsyncIterator[Entry]:
        """Yield the direct children of a directory, sizes included."""
        target = self._to_os(path)

        def scan() -> list[Entry]:
            with os.scandir(target) as entries:
                return [
                    Entry(
                        name=entry.name,
                        is_dir=entry.is_dir(follow_symlinks=False),
                        size=None
                        if entry.is_dir(follow_symlinks=False)
                        else entry.stat(follow_symlinks=False).st_size,
                    )
                    for entry in entries
                ]

        try:
            listed = await asyncio.to_thread(scan)
        except OSError as exc:
            raise from_os_error(exc, path) from exc
        for entry in listed:
            yield entry

    async def stat(self, path: PurePosixPath) -> RawStat:
        """Return raw facts about a path (directory sizes are 0)."""
        try:
            st = await aioos.stat(self._to_os(path))
        except OSError as exc:
            raise from_os_error(exc, path) from exc
        is_dir = stat_module.S_ISDIR(st.st_mode)
        return RawStat(
            kind=PathKind.DIRECTORY if is_dir else PathKind.FILE,
            size=0 if is_dir else st.st_size,
            # st_ctime is inode-change time on POSIX - the closest portable
            # approximation of creation time without st_birthtime
            created=_ts(st.st_ctime),
            modified=_ts(st.st_mtime),
            accessed=_ts(st.st_atime),
        )

    async def make_dir(self, path: PurePosixPath, *, parents: bool) -> None:
        """Create a directory (``parents=True`` behaves like mkdir -p)."""
        target = self._to_os(path)
        try:
            if parents:
                await aioos.makedirs(target, exist_ok=True)
            else:
                await aioos.mkdir(target)
        except FileNotFoundError as exc:
            raise PathNotFoundError(path.parent) from exc
        except NotADirectoryError as exc:
            raise from_os_error(exc, path.parent) from exc
        except OSError as exc:
            raise from_os_error(exc, path) from exc

    async def exists(self, path: PurePosixPath) -> bool:
        """Whether anything lives at ``path`` (native fast path)."""
        return await aioos.path.exists(self._to_os(path))

    async def move(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Move via atomic rename, falling back across devices."""
        try:
            await aioos.rename(self._to_os(src), self._to_os(dst))
        except OSError as exc:
            if exc.errno == errno.EXDEV:
                await generic.move(self, src, dst)
                return
            raise from_os_error(exc, src) from exc

    async def copy(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Copy a single file natively (sendfile fast path via shutil)."""
        try:
            await asyncio.to_thread(shutil.copyfile, self._to_os(src), self._to_os(dst))
        except OSError as exc:
            raise from_os_error(exc, src) from exc

    async def delete_tree(self, path: PurePosixPath) -> None:
        """Delete ``path`` and everything below it natively."""
        try:
            await asyncio.to_thread(shutil.rmtree, self._to_os(path))
        except OSError as exc:
            raise from_os_error(exc, path) from exc
