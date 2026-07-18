"""Benchmark: the emptiness lookups behind `sx ls` with the folder icon.

`sx ls` with the empty/full folder glyph needs every subdirectory's
emptiness. This times the serial loop (one `is_empty`, so one LIST, per
subdirectory - the pre-0.4.5 behavior) against the bulk path the CLI now
uses (`state.empty_all` -> `Storix.empty_children`), which derives every
child's emptiness from ONE recursive listing (ADR 0027 (b)). The win is
N round trips collapsing to one.

Reproducible mode uses a `LatencyBackend` (a `MemoryBackend` with a sleep
per listing call); set STORIX_BENCH_PROVIDER=azure (+ STORIX_* creds) for
the real thing. Run: `uv run python benchmarks/bench_listing.py`.
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

    def list_tree(self, path):  # one sleep: the whole bulk listing is one call
        time.sleep(LATENCY_S)
        yield from super().list_tree(path)


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
        names = [p.name for p in fs.ls('/', abs=True) if fs.isdir(p)]
        print(f'real backend {provider!r}: {len(names)} subdirs')
    else:
        fs = Storix(LatencyBackend())
        _seed(fs)
        names = [p.name for p in fs.ls('/', abs=True)]
        print(
            f'reproducible: LatencyBackend, {len(names)} subdirs, '
            f'{LATENCY_S * 1000:.0f}ms/call'
        )

    base = fs.resolve('/')
    dirs = [base / n for n in names]
    serial = _time('serial (loop is_empty)', lambda: [fs.is_empty(d) for d in dirs])
    bulk = _time('bulk (empty_all, 1 list)', lambda: empty_all(fs, base, names))
    if bulk:
        print(f'  -> {serial / bulk:.1f}x faster: one request vs {len(names)}')


if __name__ == '__main__':
    main()
