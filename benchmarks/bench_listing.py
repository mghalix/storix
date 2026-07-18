"""Benchmark: the emptiness lookups behind `sx ls` with the folder icon.

`sx ls` with the empty/full folder glyph checks `is_empty` once per
subdirectory. This times that as a serial loop (the pre-0.4.5 behavior)
versus the concurrent batch the CLI now uses (`state.empty_all`), so the
concurrency win is visible against a fixed per-call latency.

Reproducible mode uses a `LatencyBackend` (a `MemoryBackend` with a sleep
per call); set STORIX_BENCH_PROVIDER=azure (+ STORIX_* creds) for the real
thing. Run: `uv run python benchmarks/bench_listing.py`.
"""

from __future__ import annotations

import os
import time

from storix import Storix, get_storage
from storix.backends import MemoryBackend
from storix.cli.state import empty_all


N_DIRS = 24
LATENCY_S = 0.05  # per backend call, stand-in for a cloud round trip


class LatencyBackend(MemoryBackend):
    """A MemoryBackend that sleeps before each listing, to model latency."""

    def list_dir(self, path):  # mirrors the port signature
        time.sleep(LATENCY_S)
        yield from super().list_dir(path)


def _seed(fs: Storix) -> None:
    """Create N subdirectories, every other one holding a file."""
    for i in range(N_DIRS):
        fs.mkdir(f'/dir{i:02d}')
        if i % 2:
            fs.echo('x', f'/dir{i:02d}/f.txt')


def _time(label: str, fn) -> float:  # fn: a thunk
    start = time.perf_counter()
    fn()
    elapsed = time.perf_counter() - start
    print(f'  {label:26} {elapsed:6.2f}s')
    return elapsed


def main() -> None:
    provider = os.environ.get('STORIX_BENCH_PROVIDER')
    if provider:
        fs = get_storage(provider)
        dirs = [p for p in fs.ls('/', abs=True) if fs.isdir(p)]
        print(f'real backend {provider!r}: {len(dirs)} subdirs')
    else:
        fs = Storix(LatencyBackend())
        _seed(fs)
        dirs = fs.ls('/', abs=True)
        print(
            f'reproducible: LatencyBackend, {len(dirs)} subdirs, '
            f'{LATENCY_S * 1000:.0f}ms/call'
        )

    serial = _time('serial (loop is_empty)', lambda: [fs.is_empty(d) for d in dirs])
    batch = _time('concurrent (empty_all)', lambda: empty_all(fs, dirs))
    if batch:
        print(f'  -> {serial / batch:.1f}x faster concurrent ({len(dirs)} dirs)')


if __name__ == '__main__':
    main()
