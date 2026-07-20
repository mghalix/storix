"""Stream data from a subprocess producer directly into Storix without temp files.

Demonstrates streaming an external producer (e.g. a compression utility,
data generator, or shell pipeline) through stdout directly into storage.

Run:  uv run python samples/recipes/deterministic_streaming.py
"""

from __future__ import annotations

import asyncio
import sys

from typing import TYPE_CHECKING

from storix.aio import Storix, get_storage


if TYPE_CHECKING:
    from collections.abc import AsyncIterable


async def stream_from_subprocess(cmd: list[str]) -> AsyncIterable[bytes]:
    """Yield stdout chunks from a subprocess without buffering full output."""
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
        msg = stderr.decode('utf-8', errors='replace').strip() or f'exit code {retcode}'
        err_msg = f'Producer subprocess failed: {msg}'
        raise RuntimeError(err_msg)


async def main() -> None:
    # Use MemoryBackend by default (zero setup); swap for 'local', 's3', etc.
    fs: Storix = get_storage('memory')

    print('Starting stream from subprocess producer...')
    # Stream an archive of src/ via stdout using stdlib tarfile (stream mode)
    tar_code = (
        'import sys, tarfile; '
        "t = tarfile.open(fileobj=sys.stdout.buffer, mode='w|'); "
        "t.add('src'); t.close()"
    )
    cmd = [sys.executable, '-c', tar_code]

    try:
        await fs.mkdir('/archives', parents=True)
        await fs.echo(stream_from_subprocess(cmd), '/archives/src.tar')
        size = await fs.du('/archives/src.tar')
        print(f'Successfully streamed into /archives/src.tar ({size} bytes)')
        print(f'File exists: {await fs.exists("/archives/src.tar")}')
    except Exception as err:
        print(f'Streaming failed: {err}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
