from __future__ import annotations

import os

from collections.abc import AsyncIterable, Buffer, Iterable
from pathlib import PurePosixPath
from typing import IO, TYPE_CHECKING, Literal, Protocol, Self


if TYPE_CHECKING:
    from pydantic import GetCoreSchemaHandler
    from pydantic_core import core_schema


class StorixPath(PurePosixPath):
    """Base path used accross all storix filesystems."""

    @property
    def named_as_directory(self) -> bool:
        """Whether this path was written with a trailing separator.

        A trailing separator is how a shell says "this name is a
        directory", and it is the one thing a normalized path otherwise
        forgets: ``StorixPath('nodir/')`` prints as ``nodir``, so the
        question cannot be answered from ``str()``. pathlib keeps the
        segments as they were given, which is what makes this answerable
        at all, and only the last one can carry the separator.

        A derived path reports False, correctly: ``StorixPath('nodir/x')``
        has a parent of ``nodir`` that nobody wrote a separator on, and an
        assertion made about one path is not an assertion about another.

        False, rather than an error, when the segments are unavailable:
        this reads a pathlib internal (present in every Python storix
        supports), and a cosmetic assertion is not worth raising over.
        """
        # pathlib has no public accessor for the arguments as given, and
        # reconstructing one would mean shadowing every
        # constructor and operator on PurePosixPath
        raw: tuple[str, ...] = getattr(self, '_raw_paths', ())  # pyright: ignore[reportAssignmentType]
        if not raw:
            return False
        return os.fspath(raw[-1]).endswith(('/', os.sep))

    # positional bool mirrors pathlib.Path.resolve for drop-in parity
    def resolve(self, strict: bool = False) -> Self:  # noqa: FBT001, FBT002
        """Make the path absolute and normalized, resolving any symlinks.

        Resolves against the local filesystem, so it answers for a local
        session and not for a cloud one, where a path has no host to
        resolve symlinks against. Backends that need their own answer
        override it.
        """
        from pathlib import Path

        return self.__class__(Path(self).resolve(strict=strict))

    def maybe_file(self) -> bool:
        """Guess whether the path points to a file, judging by its shape."""
        from storix.utils.paths import is_file_approx

        return is_file_approx(self)

    def maybe_dir(self) -> bool:
        """Guess whether the path points to a directory, judging by its shape."""
        from storix.utils.paths import is_dir_approx

        return is_dir_approx(self)

    def guess_mimetype(self) -> str | None:
        """Guess mimetype from file extension using stdlib.

        Returns:
            None when type can't be determined.
        """
        from storix.utils import guess_mimetype_from_path

        return guess_mimetype_from_path(self)

    @property
    def kind(self) -> PathKindStr:
        """Guessed kind of the object at this path (file or directory)."""
        return 'file' if self.maybe_file() else 'directory'

    # allow pydantic to understand StorixPath useful for cases where you are returning
    # StorixPath as a response model in FastAPI as an example
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: type, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return handler(PurePosixPath)  # delegate entirely to parent's schema


os.PathLike.register(StorixPath)

type StrPathLike = os.PathLike[str] | str
type StorageProvider = Literal['local', 'memory', 'azure', 's3', 'gcs']
type EchoMode = Literal['w', 'a']

type WalkOrder = Literal['dfs', 'level']
"""Emission order of ``Storix.walk``. ``'dfs'`` (the default) yields exact
depth-first output, the sequential-walk contract; ``'level'`` yields each
traversal level whole, siblings contiguous in stable parent/listing order."""

type PathKindStr = Literal['file', 'directory']
"""The string form of ``PathKind``, for ergonomic keyword args (``kind='file'``)
that a type checker still guides. Kept in lockstep with the enum by
``test_path_kind_str_matches_enum`` - add a ``PathKind`` case and the test
fails until this Literal lists it too."""


class BinarySink(Protocol):
    """Anything ``download`` can write bytes into.

    Structural on purpose: the requirement is "accepts bytes", not "is an
    ``IO[bytes]``". A ``gzip.GzipFile``, a ``SpooledTemporaryFile``, a
    socket stream and a plain ``open(path, 'wb')`` all qualify, and a text
    stream deliberately does not - storage yields bytes, and a parallel
    download splits a file at byte offsets that can fall inside a
    multi-byte character.
    """

    def write(self, data: bytes, /) -> object:
        """Consume one chunk of the download."""
        ...


type DataBuffer[AnyStr: (str, bytes)] = (
    AnyStr | Buffer | Iterable[AnyStr | Buffer] | IO[AnyStr]
)
type AsyncDataBuffer[AnyStr: (str, bytes)] = (
    DataBuffer[AnyStr] | AsyncIterable[AnyStr | Buffer]
)
