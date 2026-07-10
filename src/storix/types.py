from __future__ import annotations

import os

from collections.abc import AsyncIterable, Buffer, Iterable
from pathlib import PurePosixPath
from typing import IO, TYPE_CHECKING, Literal, Self


if TYPE_CHECKING:
    from pydantic import GetCoreSchemaHandler
    from pydantic_core import core_schema


class StorixPath(PurePosixPath):
    """Base path used accross all storix filesystems."""

    # TODO: override in cloud-based filesystems
    # positional bool mirrors pathlib.Path.resolve for drop-in parity
    def resolve(self, strict: bool = False) -> Self:  # noqa: FBT001, FBT002
        """Make the path absolute and normalized, resolving any symlinks."""
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
    def kind(self) -> Literal['file', 'directory']:
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
type AvailableProviders = Literal['local', 'azure']
type EchoMode = Literal['w', 'a']

type DataBuffer[AnyStr: (str, bytes)] = (
    AnyStr | Buffer | Iterable[AnyStr | Buffer] | IO[AnyStr]
)
type AsyncDataBuffer[AnyStr: (str, bytes)] = (
    DataBuffer[AnyStr] | AsyncIterable[AnyStr | Buffer]
)
