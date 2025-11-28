import abc
import os
from collections.abc import AsyncIterable, Buffer, Iterable
from pathlib import PurePath
from typing import IO, Literal, Self


class StorixPath(PurePath, abc.ABC):
    """Base path used accross all storix filesystems."""

    # TODO(mghalix): override in cloud-based filesystems
    def resolve(self, strict: bool = False) -> Self:
        """Make the path absolute, resolving all symlinks on the way and also normalizing it."""
        from pathlib import Path

        return self.__class__(Path(self).resolve(strict=strict))

    # TODO(mghalix): Implement this per sync/async
    # @abc.abstractmethod
    # def open(self) -> IO[Any]: ...


os.PathLike.register(StorixPath)

type StrPathLike = os.PathLike[str] | str
type AvailableProviders = Literal["local", "azure"]
type EchoMode = Literal["w", "a"]

type DataBuffer[AnyStr: (str, bytes)] = (
    AnyStr | Buffer | Iterable[AnyStr | Buffer] | IO[AnyStr]
)
type AsyncDataBuffer[AnyStr: (str, bytes)] = (
    DataBuffer[AnyStr] | AsyncIterable[AnyStr | Buffer]
)
