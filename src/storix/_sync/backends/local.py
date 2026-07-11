"""Local filesystem backend (sync flavor).

Hand-written twin of ``storix._async.backends.local`` - NOT generated.
Same semantics over plain open/os/shutil; keep in lockstep by hand. The
conformance suite is the drift guard.
"""

from __future__ import annotations

import datetime as dt
import errno
import os
import shutil
import stat as stat_module

from pathlib import Path
from typing import TYPE_CHECKING

from storix.constants import DEFAULT_WRITE_CHUNKSIZE
from storix.enums import PathKind
from storix.errors import PathNotFoundError, from_os_error
from storix.models import Entry, RawStat

from . import generic
from .base import BackendBase


if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
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

    @property
    def base(self) -> Path:
        """The real OS directory where port path ``/`` is anchored.

        This is namespace configuration, not session state: the backend
        stays stateless. A session's ``pwd``/``home`` (which start at the
        virtual ``/``) live on ``Storix``, deliberately independent of
        where that ``/`` physically resolves.
        """
        return self._base

    def _to_os(self, path: PurePosixPath) -> Path:
        return self._base.joinpath(*path.parts[1:])

    def read_stream(self, path: PurePosixPath) -> Iterator[bytes]:
        """Stream a file's contents in chunks."""
        try:
            handle = open(self._to_os(path), 'rb')  # noqa: SIM115, PTH123
        except OSError as exc:
            raise from_os_error(exc, path) from exc
        try:
            while chunk := handle.read(DEFAULT_WRITE_CHUNKSIZE):
                yield chunk
        finally:
            handle.close()

    def write(
        self,
        path: PurePosixPath,
        data: Iterator[bytes],
        *,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Write a file from a chunk stream ('w' truncates, 'a' appends)."""
        del content_type, metadata  # capabilities not advertised; never sent
        try:
            handle = open(self._to_os(path), 'wb' if mode == 'w' else 'ab')  # noqa: SIM115, PTH123
        except OSError as exc:
            raise from_os_error(exc, path) from exc
        try:
            handle.writelines(data)
        finally:
            handle.close()

    def delete(self, path: PurePosixPath) -> None:
        """Delete a leaf: a file or an empty directory."""
        raw = self.stat(path)
        target = self._to_os(path)
        try:
            if raw.kind is PathKind.DIRECTORY:
                os.rmdir(target)  # noqa: PTH106
            else:
                os.remove(target)  # noqa: PTH107
        except OSError as exc:
            raise from_os_error(exc, path) from exc

    def list_dir(self, path: PurePosixPath) -> Iterator[Entry]:
        """Yield the direct children of a directory, sizes included."""
        target = self._to_os(path)
        try:
            with os.scandir(target) as entries:
                listed = [
                    Entry(
                        name=entry.name,
                        is_dir=entry.is_dir(follow_symlinks=False),
                        size=None
                        if entry.is_dir(follow_symlinks=False)
                        else entry.stat(follow_symlinks=False).st_size,
                    )
                    for entry in entries
                ]
        except OSError as exc:
            raise from_os_error(exc, path) from exc
        yield from listed

    def stat(self, path: PurePosixPath) -> RawStat:
        """Return raw facts about a path (directory sizes are 0)."""
        try:
            st = os.stat(self._to_os(path))  # noqa: PTH116
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

    def make_dir(self, path: PurePosixPath, *, parents: bool) -> None:
        """Create a directory (``parents=True`` behaves like mkdir -p)."""
        target = self._to_os(path)
        try:
            if parents:
                os.makedirs(target, exist_ok=True)  # noqa: PTH103
            else:
                os.mkdir(target)  # noqa: PTH102
        except FileNotFoundError as exc:
            raise PathNotFoundError(path.parent) from exc
        except NotADirectoryError as exc:
            raise from_os_error(exc, path.parent) from exc
        except OSError as exc:
            raise from_os_error(exc, path) from exc

    def exists(self, path: PurePosixPath) -> bool:
        """Whether anything lives at ``path`` (native fast path)."""
        return self._to_os(path).exists()

    def move(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Move via atomic rename, falling back across devices."""
        try:
            os.rename(self._to_os(src), self._to_os(dst))  # noqa: PTH104
        except OSError as exc:
            if exc.errno == errno.EXDEV:
                generic.move(self, src, dst)
                return
            raise from_os_error(exc, src) from exc

    def copy(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Copy a single file natively (sendfile fast path via shutil)."""
        try:
            shutil.copyfile(self._to_os(src), self._to_os(dst))
        except OSError as exc:
            raise from_os_error(exc, src) from exc

    def delete_tree(self, path: PurePosixPath) -> None:
        """Delete ``path`` and everything below it natively."""
        try:
            shutil.rmtree(self._to_os(path))
        except OSError as exc:
            raise from_os_error(exc, path) from exc
