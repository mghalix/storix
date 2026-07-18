"""Exercise the default Storix installation without optional extras."""

import asyncio
import os
import tempfile

from importlib.metadata import version

from pydantic import TypeAdapter, ValidationError

from storix import StorageProvider, Storix
from storix.aio import Storix as AsyncStorix
from storix.aio.backends import MemoryBackend as AsyncMemoryBackend
from storix.backends import LocalBackend, MemoryBackend


def check_sync() -> None:
    """Exercise the default sync memory and local backends."""
    memory = Storix(MemoryBackend())
    memory.echo(b'memory', '/value')
    assert memory.cat('/value') == b'memory'

    with tempfile.TemporaryDirectory() as directory:
        local = Storix(LocalBackend(directory))
        local.echo(b'local', '/value')
        assert local.cat('/value') == b'local'


async def check_async() -> None:
    """Exercise the default async memory backend."""
    memory = AsyncStorix(AsyncMemoryBackend())
    await memory.echo(b'async', '/value')
    assert await memory.cat('/value') == b'async'


def check_public_provider_type() -> None:
    """Verify Pydantic enforces the public Python 3.12 type alias."""
    adapter = TypeAdapter[StorageProvider](StorageProvider)
    assert adapter.validate_python('memory') == 'memory'
    try:
        adapter.validate_python('unsupported')
    except ValidationError:
        return
    msg = 'StorageProvider accepted an unsupported value'
    raise AssertionError(msg)


def main() -> None:
    """Run the default-runtime smoke checks."""
    expected_version = os.environ.get('STORIX_EXPECTED_VERSION')
    if expected_version is not None:
        assert version('storix') == expected_version
    check_sync()
    asyncio.run(check_async())
    check_public_provider_type()


if __name__ == '__main__':
    main()
