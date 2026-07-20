"""Optional integration recipe: Stream yt-dlp output directly into cloud storage.

Streams media output from yt-dlp's stdout into Storix chunk by chunk without
saving intermediate files to local disk.

Requirements:
    - yt-dlp installed (`pip install yt-dlp` or binary on PATH)
    - Valid storage configuration (defaults to in-memory)

Usage:
    uv run python samples/recipes/ytdlp_streaming.py <URL> [DEST_PATH]
"""

from __future__ import annotations

import asyncio
import shutil
import sys

from typing import TYPE_CHECKING

from storix.aio import Storix, get_storage


if TYPE_CHECKING:
    from collections.abc import AsyncIterable


async def stream_ytdlp(url: str) -> AsyncIterable[bytes]:
    """Stream yt-dlp stdout in 64 KiB chunks."""
    cmd = [
        'yt-dlp',
        '--no-playlist',
        '-f',
        'b/best',  # select pre-merged format compatible with stdout
        '-o',
        '-',  # output to stdout
        url,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None

    try:
        while chunk := await proc.stdout.read(64 * 1024):
            yield chunk
    except Exception:
        proc.kill()
        await proc.wait()
        raise

    stderr = await proc.stderr.read()
    retcode = await proc.wait()
    if retcode != 0:
        err_text = stderr.decode('utf-8', errors='replace').strip()
        msg = f'yt-dlp failed with exit code {retcode}: {err_text}'
        raise RuntimeError(msg)


async def main() -> None:
    if shutil.which('yt-dlp') is None:
        print(
            'yt-dlp is not installed or not on PATH.\n'
            'Install it via `pip install yt-dlp` to run this optional recipe.',
            file=sys.stderr,
        )
        sys.exit(1)

    args = sys.argv[1:]
    url = args[0] if args else 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
    dest = args[1] if len(args) > 1 else '/media/video.mp4'

    print(f'Streaming {url} -> {dest} ...')
    fs: Storix = get_storage('memory')

    try:
        # Note: If the producer fails midway, a partial object may remain in storage.
        await fs.mkdir('/media', parents=True)
        await fs.echo(stream_ytdlp(url), dest)
        size = await fs.du(dest)
        print(f'Stream complete! Saved {dest} ({size} bytes).')
    except Exception as err:
        print(f'Streaming failed: {err}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
