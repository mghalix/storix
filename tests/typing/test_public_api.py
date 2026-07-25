"""Static type assertions for the public sync and async APIs."""

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from typing import assert_type

    from storix import Storix, get_storage
    from storix.aio import Storix as AsyncStorix
    from storix.aio.backends import MemoryBackend as AsyncMemoryBackend
    from storix.backends import MemoryBackend
    from storix.models import DirEntry

    sync_fs = Storix(MemoryBackend())
    assert_type(sync_fs.cat('/value'), bytes)
    assert_type(sync_fs.empty_children('/'), dict[str, bool])
    assert_type(sync_fs.scandir('/'), Iterator[DirEntry])

    async_fs = AsyncStorix(AsyncMemoryBackend())

    async def check_async_api() -> None:
        """Assert the public async return types."""
        assert_type(await async_fs.cat('/value'), bytes)
        assert_type(await async_fs.empty_children('/'), dict[str, bool])
        assert_type(async_fs.scandir('/'), AsyncIterator[DirEntry])

    # a profile names its own provider, so the usual call names none (ADR 0031)
    assert_type(get_storage(profile='media'), Storix)
    assert_type(get_storage(profile='media', environment='prod'), Storix)
    assert_type(get_storage(profile='media', read_chunk_size='8MiB'), Storix)
    # naming the provider is optional, and buys typed completion for its keys
    assert_type(get_storage('azure', profile='media', container='other'), Storix)
    assert_type(get_storage('local', base='./data'), Storix)
