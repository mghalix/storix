from __future__ import annotations

import asyncio
import contextlib
import os
import shutil

from typing import TYPE_CHECKING, Final

from rich.console import Console

from storix.aio import Storix, get_storage


if TYPE_CHECKING:
    from collections.abc import AsyncIterator


DESTINATION: Final[str] = '/launch/one-stream-three-backends.mp4'
CHUNK_SIZE: Final[int] = 64 * 1024
WRITE_CHUNK_SIZE: Final[int] = 4 * 1024 * 1024
DURATION_SECONDS: Final[int] = 7

console = Console()


async def ffmpeg_stream() -> AsyncIterator[bytes]:
    """Generate a fragmented MP4 and yield it directly from FFmpeg stdout."""
    command = [
        'ffmpeg',
        '-hide_banner',
        '-loglevel',
        'error',
        '-nostdin',
        '-re',
        '-f',
        'lavfi',
        '-i',
        'testsrc2=size=1280x720:rate=30',
        '-re',
        '-f',
        'lavfi',
        '-i',
        'sine=frequency=880:sample_rate=48000',
        '-t',
        str(DURATION_SECONDS),
        '-shortest',
        '-c:v',
        'libx264',
        '-preset',
        'veryfast',
        '-tune',
        'zerolatency',
        '-pix_fmt',
        'yuv420p',
        '-g',
        '30',
        '-keyint_min',
        '30',
        '-sc_threshold',
        '0',
        '-c:a',
        'aac',
        '-b:a',
        '128k',
        '-movflags',
        '+frag_keyframe+empty_moov+default_base_moof',
        '-f',
        'mp4',
        'pipe:1',
    ]

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    assert process.stdout is not None
    assert process.stderr is not None

    try:
        while chunk := await process.stdout.read(CHUNK_SIZE):
            yield chunk
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise

    stderr = await process.stderr.read()
    return_code = await process.wait()

    if return_code != 0:
        detail = stderr.decode('utf-8', errors='replace').strip()
        message = detail or f'FFmpeg exited with status {return_code}'
        raise RuntimeError(message)


def provider_label(provider: str) -> str:
    """Return the concise display name used by the recording."""
    return {
        'local': 'LOCAL',
        'azure': 'AZURE',
        's3': 'R2',
    }.get(provider, provider.upper())


def backend_name(fs: Storix) -> str:
    """Return the real provider beneath any Storix layers."""
    return type(fs.base_backend).__name__


def format_size(size: int) -> str:
    """Format a byte count as a compact binary size."""
    return f'{size / (1024 * 1024):.2f} MiB'


async def main() -> None:
    """Generate one video and stream it into the configured provider."""
    if shutil.which('ffmpeg') is None:
        console.print('[red]ffmpeg is not installed or available on PATH.[/red]')
        raise SystemExit(1)

    provider = os.getenv('STORIX_PROVIDER', 'local').lower()
    label = provider_label(provider)

    base = get_storage()
    backend = backend_name(base)

    console.print('cleaning...')
    # Same code.
    # The provider comes from STORIX_PROVIDER.
    async with base as fs:
        with contextlib.suppress(FileNotFoundError):
            await fs.rm('/launch', recursive=True)

    console.print(f'[green]DONE[/green]  {label:<7} {backend:<18} ')


if __name__ == '__main__':
    asyncio.run(main())
