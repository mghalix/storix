from collections.abc import AsyncIterable, Iterable, Iterator
from io import BytesIO, UnsupportedOperation
from typing import Any, Protocol, overload, runtime_checkable

from storix.typing import AsyncDataBuffer, DataBuffer


class _IReadableStreamBase(Protocol):
    def seekable(self) -> bool: ...
    def tell(self, *args: Any, **kwargs: Any) -> int: ...
    def seek(self, *args: Any, **kwargs: Any) -> int: ...


@runtime_checkable
class _ReadableStream(_IReadableStreamBase, Protocol):
    def read(self, size: int | None = ..., /) -> bytes: ...


@runtime_checkable
class _AsyncReadableStream(_IReadableStreamBase, Protocol):
    async def read(self, size: int | None = ..., /) -> bytes: ...


@overload
def normalize_data[AnyStr: (str, bytes)](
    data: DataBuffer[AnyStr],
    *,
    encoding: str = "utf-8",
) -> _ReadableStream: ...
@overload
def normalize_data[AnyStr: (str, bytes)](
    data: AsyncIterable[AnyStr],
    *,
    encoding: str = "utf-8",
) -> _AsyncReadableStream: ...


def normalize_data[AnyStr: (str, bytes)](
    data: AsyncDataBuffer[AnyStr],
    *,
    encoding: str = "utf-8",
) -> _ReadableStream | _AsyncReadableStream:
    """Normalize data into readable."""
    if isinstance(data, str):
        data = data.encode(encoding=encoding)  # type: ignore[assignment]

    # cover both mutable and immutable buffers
    if isinstance(data, bytes | bytearray):
        return BytesIO(data)

    if callable(getattr(data, "read", None)):
        return data  # type: ignore[return-value]

    if isinstance(data, Iterable):
        return _IterStreamer(data, encoding=encoding)

    if isinstance(data, AsyncIterable):
        return _AsyncIterStreamer(data, encoding=encoding)

    raise TypeError(f"Unsupported data type: {type(data)}")


class _BaseStreamer:
    def seekable(self) -> bool:
        return False

    def tell(self, *_: Any, **__: Any) -> int:
        raise UnsupportedOperation("Data generator does not support tell().")

    def seek(self, *_: Any, **__: Any) -> int:
        raise UnsupportedOperation("Data generator is not seekable().")


class _IterStreamer[AnyStr: (str, bytes)](_BaseStreamer):
    def __init__(self, generator: Iterable[AnyStr], *, encoding: str = "utf-8") -> None:
        self.generator = generator
        self.iterator = iter(generator)
        self.encoding = encoding
        self.leftover = b""

    def __len__(self) -> int:
        # ignore[attr-defined] because not all iterables implement __len__
        return self.generator.__len__()  # type: ignore[attr-defined]

    def __next__(self) -> AnyStr:
        return next(self.iterator)

    def __iter__(self) -> Iterator[AnyStr]:
        return self.iterator

    def read(self, size: int | None = None, /) -> bytes:
        size = size or 1024

        data: bytes = self.leftover
        count = len(data)
        try:
            while count < size:
                chunk = self.__next__()
                if isinstance(chunk, str):
                    chunk = chunk.encode(self.encoding)
                data += chunk
                count += len(chunk)

        except StopIteration:
            self.leftover = b""

        else:
            self.leftover = data[size:]

        return data[:size]


class _AsyncIterStreamer[AnyStr: (str, bytes)](_BaseStreamer):
    def __init__(
        self, generator: AsyncIterable[AnyStr], *, encoding: str = "utf-8"
    ) -> None:
        self.iterator = generator.__aiter__()
        self.encoding = encoding
        self.leftover = b""

    async def read(self, size: int | None = None, /) -> bytes:
        size = size or 1024

        data: bytes = self.leftover
        count = len(data)
        try:
            while count < size:
                chunk = await self.iterator.__anext__()
                if isinstance(chunk, str):
                    chunk = chunk.encode(self.encoding)
                data += chunk
                count += len(chunk)

        except StopAsyncIteration:
            self.leftover = b""

        else:
            self.leftover = data[size:]

        return data[:size]
