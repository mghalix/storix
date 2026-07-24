"""Benchmark: what a bulk push or pull costs in time and in memory.

`sx push`/`sx pull` fan a directory out over the core `concurrent` helper,
one in-flight transfer per file. Throughput therefore scales with the
fan-out, and so does memory: every stream in flight holds its backend's
buffers (for Azure, the initial download request plus one chunk). This
times a whole directory at a given fan-out and reports both, so the two
can be traded against each other with numbers rather than intuition.

Reproducible mode (default) uses a `LatencyBackend`: a `LocalBackend` that
sleeps once per streamed request, standing in for a network round trip.
Deterministic, needs no credentials, and the fan-out curve moves the way it
does on a real cloud. Set STORIX_BENCH_PROVIDER=azure (plus the usual
STORIX_* credentials) to time a real container instead; only real mode
makes the memory column mean anything, since the reproducible backend
writes to a local disk rather than holding provider buffers.

One process measures one configuration, because peak RSS is a
whole-process high-water mark. Sweep from the shell:

    for n in 4 8 16 32; do uv run python bench/transfer.py --limit $n; done
"""

from __future__ import annotations

import argparse
import os
import resource
import shutil
import tempfile
import time

from functools import partial
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from storix import Storix, get_storage
from storix._sync._compat import concurrent  # pyright: ignore[reportPrivateUsage]
from storix.backends import LocalBackend
from storix.constants import DEFAULT_CONCURRENCY


if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from storix.enums import EchoMode


REMOTE_ROOT = PurePosixPath('/_bench_transfer')
"""Prefix every run writes under, removed again on the way out."""

LATENCY_S = 0.05
"""Sleep per streamed request in reproducible mode, modelling a round trip."""


class LatencyBackend(LocalBackend):
    """A LocalBackend that sleeps per transfer request, to model latency.

    The sleep sits on the streaming calls only: it is the per-request cost
    that fan-out exists to hide, and the one that makes a serial transfer
    look like a cloud transfer.
    """

    def read_stream(
        self, path: PurePosixPath, *, chunk_size: int | None = None
    ) -> Iterator[bytes]:
        """Stream a file, paying one round trip before the first chunk."""
        time.sleep(LATENCY_S)
        yield from super().read_stream(path, chunk_size=chunk_size)

    def write_stream(
        self,
        path: PurePosixPath,
        data: Iterator[bytes],
        *,
        chunk_size: int | None = None,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Write a file, paying one round trip for the request."""
        time.sleep(LATENCY_S)
        super().write_stream(
            path,
            data,
            chunk_size=chunk_size,
            mode=mode,
            content_type=content_type,
            metadata=metadata,
        )


def rss_mb() -> float:
    """Resident set size right now, in megabytes."""
    statm = Path('/proc/self/statm').read_text().split()
    return int(statm[1]) * os.sysconf('SC_PAGE_SIZE') / 1e6


def peak_rss_mb() -> float:
    """Highest resident set size this process has reached, in megabytes."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def build_payload(root: Path, files: int, size: int) -> None:
    """Write `files` incompressible files of `size` bytes, once per shape.

    Args:
        root: Directory to fill; reused as-is when it already exists.
        files: How many files to write.
        size: Size of each file in bytes.
    """
    if root.exists():
        return
    root.mkdir(parents=True)
    block = os.urandom(1024 * 1024)
    for index in range(files):
        with (root / f'part{index:03d}.bin').open('wb') as handle:
            for _ in range(size // len(block)):
                handle.write(block)


def build_session() -> tuple[Storix, Path | None]:
    """Open the session under test, plus the sink to remove afterwards.

    Returns:
        The session, and the temporary directory backing it in reproducible
        mode (None when timing a real provider).
    """
    if os.getenv('STORIX_BENCH_PROVIDER') == 'azure':
        return get_storage('azure'), None
    sink = Path(tempfile.mkdtemp(prefix='bench-transfer-sink-'))
    return Storix(LatencyBackend(sink)), sink


def push(fs: Storix, payload: Path, remote: PurePosixPath, limit: int) -> None:
    """Upload every file under `payload`, `limit` transfers in flight."""
    files = sorted(path for path in payload.rglob('*') if path.is_file())
    fs.mkdir(remote, parents=True)

    def send(source: Path) -> None:
        with source.open('rb') as data:
            fs.echo(data, remote / source.name)

    concurrent((partial(send, source) for source in files), limit=limit)


def pull(fs: Storix, remote: PurePosixPath, out: Path, limit: int) -> None:
    """Download everything under `remote`, `limit` transfers in flight."""
    entries = [entry for entry in fs.walk(remote, all=True) if not entry.is_dir]

    def fetch(source: PurePosixPath) -> None:
        with (out / source.name).open('wb') as handle:
            for chunk in fs.stream(source):
                handle.write(chunk)

    concurrent((partial(fetch, entry.path) for entry in entries), limit=limit)


def main() -> None:
    """Time one push or pull and print its cost."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--op', default='push', choices=['push', 'pull'])
    parser.add_argument('--limit', type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument('--files', type=int, default=24)
    parser.add_argument('--size-mb', type=int, default=8)
    args = parser.parse_args()

    shape = f'{args.files}x{args.size_mb}'
    payload = Path(tempfile.gettempdir()) / f'bench-transfer-{shape}'
    build_payload(payload, args.files, args.size_mb * 1024 * 1024)
    fs, sink = build_session()
    remote = REMOTE_ROOT / shape
    out = Path(tempfile.mkdtemp(prefix='bench-transfer-out-'))

    try:
        if args.op == 'pull':
            push(fs, payload, remote, args.limit)
        start = time.monotonic()
        if args.op == 'push':
            push(fs, payload, remote, args.limit)
        else:
            pull(fs, remote, out, args.limit)
        elapsed = time.monotonic() - start
    finally:
        shutil.rmtree(out, ignore_errors=True)
        if sink is None:
            fs.rm(REMOTE_ROOT, recursive=True)
        else:
            shutil.rmtree(sink, ignore_errors=True)

    total_mb = args.files * args.size_mb
    where = 'azure' if sink is None else f'local +{LATENCY_S * 1000:.0f}ms'
    print(
        f'{args.op} {shape}MiB on {where} at fan-out '
        f'{args.limit}: {elapsed:6.2f}s {total_mb / elapsed:7.1f} MB/s '
        f'peak={peak_rss_mb():6.1f} MB retained={rss_mb():6.1f} MB'
    )


if __name__ == '__main__':
    main()
