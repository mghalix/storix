# Benchmarks

Performance checks for storix, kept out of the shipped package (like
`website/`). Run them by hand; they are not part of `pytest` or CI. They are
tracked source all the same: Ruff lints and formats this directory with the
rest of the repository, so keep them readable.

The perf that matters (concurrent listing, ADR 0025/0027; bulk transfers)
only shows against **latency** - a local backend is too fast to reveal it. So
each benchmark has two modes:

- **Reproducible** (default): a `LatencyBackend` adds a fixed sleep per backend
  call, standing in for a network round trip. Deterministic, needs no
  credentials, and the numbers move exactly as they do on a real cloud.
- **Real** (opt-in): set `STORIX_BENCH_PROVIDER=azure` (plus the usual
  `STORIX_*` credentials) to time against an actual container.

## listing.py

The emptiness lookups behind `sx ls` with the folder glyph: the serial loop
against the batched path the CLI uses now.

```bash
uv run python bench/listing.py            # reproducible
STORIX_BENCH_PROVIDER=azure uv run python bench/listing.py
```

## transfer.py

What a bulk `push`/`pull` costs in wall time and in memory at a given
fan-out. Throughput scales with the fan-out; so does peak memory, because
every transfer in flight holds its backend's buffers. One process measures
one configuration (peak RSS is a whole-process high-water mark), so sweep
from the shell:

```bash
for n in 4 8 16 32; do uv run python bench/transfer.py --limit "$n"; done
uv run python bench/transfer.py --op pull --files 12 --size-mb 40
STORIX_BENCH_PROVIDER=azure uv run python bench/transfer.py --limit 32
```

The memory column only means something in real mode: the reproducible
backend writes to a local disk instead of holding provider buffers. Real
mode uploads and deletes its own payload under `/_bench_transfer`, so it
costs transactions (and egress on `--op pull`) against the container you
point it at.
