"""Remove the showcase output from the configured Storix backend."""

from __future__ import annotations

import asyncio
import contextlib
import os

from typing import Final

from rich.console import Console

from storix.aio import get_storage


LAUNCH_DIRECTORY: Final[str] = '/launch'

console = Console()


def provider_label(provider: str) -> str:
    """Return the concise display name used by the recording."""
    return {
        'local': 'LOCAL',
        'azure': 'AZURE',
        's3': 'R2',
    }.get(provider, provider.upper())


async def main() -> None:
    """Delete the showcase directory when it exists."""
    provider = os.getenv('STORIX_PROVIDER', 'local').lower()
    label = provider_label(provider)

    session = get_storage()
    backend = type(session.base_backend).__name__

    async with session as fs:
        with contextlib.suppress(FileNotFoundError):
            await fs.rm(LAUNCH_DIRECTORY, recursive=True)

    console.print(f'[green]CLEAN[/green] {label:<7} {backend:<18}')


if __name__ == '__main__':
    asyncio.run(main())
