# Benchmarks

Performance checks for storix, kept out of the shipped package (like
`website/`). Run them by hand; they are not part of `pytest` or CI.

The perf that matters (concurrent listing, ADR 0025/0027) only shows against
**latency** - a local `MemoryBackend` is too fast to reveal it. So each
benchmark has two modes:

- **Reproducible** (default): a `LatencyBackend` adds a fixed sleep per backend
  call, standing in for a network round trip. Deterministic, needs no
  credentials, and the numbers move exactly as they do on a real cloud.
- **Real** (opt-in): set `STORIX_BENCH_PROVIDER=azure` (plus the usual
  `STORIX_*` credentials) to time against an actual container.

```bash
uv run python benchmarks/bench_listing.py            # reproducible
STORIX_BENCH_PROVIDER=azure uv run python benchmarks/bench_listing.py
```
