"""Static type assertions for the public sync and async APIs."""

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from typing import assert_type

    from storix import Storix
    from storix.aio import Storix as AsyncStorix
    from storix.aio.backends import MemoryBackend as AsyncMemoryBackend
    from storix.backends import MemoryBackend
    from storix.models import DirEntry

    sync_fs = Storix(MemoryBackend())
    assert_type(sync_fs.cat('/value'), bytes)
    assert_type(sync_fs.scandir('/'), Iterator[DirEntry])

    async_fs = AsyncStorix(AsyncMemoryBackend())

    async def check_async_api() -> None:
        """Assert the public async return types."""
        assert_type(await async_fs.cat('/value'), bytes)
        assert_type(async_fs.scandir('/'), AsyncIterator[DirEntry])
