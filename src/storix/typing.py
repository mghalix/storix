import os
from collections.abc import AsyncIterable, Iterable
from typing import IO, Literal

type StrPathLike = os.PathLike[str] | str
type _AvailableProviders = Literal["local", "azure"]
type _EchoMode = Literal["w", "a"]

type DataBuffer[AnyStr: (str, bytes)] = AnyStr | Iterable[AnyStr] | IO[AnyStr]
type AsyncDataBuffer[AnyStr: (str, bytes)] = DataBuffer[AnyStr] | AsyncIterable[AnyStr]
