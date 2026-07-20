<p align="center">
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/mghalix/storix/main/.github/assets/storix-banner-light.png">
    <img src="https://raw.githubusercontent.com/mghalix/storix/main/.github/assets/storix-banner.png" alt="Storix" style="width: 100%; max-width: 880px;">
  </picture>
</p>

<p align="center">
  An async-first, streaming-first storage SDK for modern Python applications.
</p>

<p align="center">
  <a href="https://github.com/mghalix/storix/actions/workflows/ci.yml"><img src="https://github.com/mghalix/storix/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/storix/"><img src="https://badge.fury.io/py/storix.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/storix/"><img src="https://img.shields.io/pypi/pyversions/storix.svg" alt="Supported Python versions"></a>
  <a href="https://github.com/mghalix/storix/blob/main/LICENSE"><img src="https://img.shields.io/github/license/mghalix/storix.svg" alt="License"></a>
</p>

<p align="center">
  <b>Documentation</b>: <a href="https://storix.mghalix.com">storix.mghalix.com</a>
</p>

---

Storix gives you one unix-flavored filesystem API over any storage backend.
Write your application logic once with `ls`, `cat`, `echo`, `mv`, and `stream`,
then swap between local disk, in-memory, Azure, S3, or GCS by changing one line.

Data flows through bounded memory as async streams, so application code can forward
incremental byte streams directly into cloud storage or stream a large file back
to a client without accumulating the complete object in memory.

```python
import asyncio

from storix.aio import Storix
from storix.aio.backends import MemoryBackend


async def main() -> None:
    fs = Storix(MemoryBackend())  # zero setup, runs anywhere

    await fs.mkdir('/reports')
    await fs.echo(b'quarterly numbers', '/reports/q1.txt')

    print(await fs.cat('/reports/q1.txt'))  # b'quarterly numbers'
    print(await fs.ls('/reports'))  # [StorixPath('q1.txt')]
    print(await fs.du('/reports'))  # 17


if __name__ == '__main__':
    asyncio.run(main())
```

## Install

```bash
pip install storix               # local filesystem + in-memory
pip install "storix[azure]"      # + Azure Storage (ADLS Gen2 + Blob)
pip install "storix[s3]"         # + Amazon S3 (also R2 / MinIO)
pip install "storix[gcs]"        # + Google Cloud Storage
pip install "storix[cli]"        # + the sx command-line shell
pip install "storix[all]"        # everything
```

Requires Python 3.12+.

## Why Storix?

**Streaming writes from any source.** `echo()` accepts bytes, strings,
iterators, async iterators, and file-like objects. Pipe data directly into
storage without landing it on disk first:

```python
from collections.abc import AsyncIterable

from storix.aio import get_storage


async def stream_upload_to_cloud(
    upload_chunks: AsyncIterable[bytes],
) -> None:
    """Stream data chunks directly into cloud storage."""
    fs = get_storage('s3', bucket='my-bucket')
    await fs.echo(upload_chunks, '/incoming/data.bin')
    # each chunk flows through bounded memory -> no temp file
```

**Test without mocks or credentials.** `MemoryBackend` is a full in-process
backend. Write your tests against it, run them in CI, and deploy against any
cloud provider:

```python
import pytest

from storix import Storix
from storix.backends import MemoryBackend


@pytest.fixture
def fs() -> Storix:
    return Storix(MemoryBackend())


def test_pipeline(fs: Storix) -> None:
    fs.echo(b'data', '/input.csv')
    assert fs.cat('/input.csv') == b'data'
```

**Change providers without changing code.** Your application logic depends on
`Storix`, never on a provider SDK. Flip one environment variable and the same
code runs against a different backend:

```python
from storix.aio import Storix, get_storage

# Reads STORIX_PROVIDER from the environment (+ STORIX_<PROVIDER>_* config).
# Local in development, Azure in staging, S3 in production.
fs: Storix = get_storage()
```

**Composable middleware.** Layers wrap any backend without touching your code:

- **SandboxLayer** - escape-proof chroot for multi-tenant isolation
- **CacheLayer** - configurable read-through cache with per-operation control
- **ObservabilityLayer** - transfer events for progress bars and metrics
- **DataUrlLayer / MetadataLayer** - backfill capabilities on any provider

```python
from storix.aio import CacheLayer, get_storage

fs = get_storage('azure').with_layer(CacheLayer, ttl=300)
fresh = await fs.uncached.cat('/config.json')  # bypass cache for one read
```

## Streaming

Storix treats streaming as the default path, not an afterthought. Reads and
writes use async iterators through the full stack:

```python
# Stream a file back chunk by chunk (feeds directly into StreamingResponse)
async for chunk in fs.stream('/large-file.bin', chunk_size=65536):
    yield chunk

# Write from any async source (e.g. an HTTP upload stream, subprocess pipe)
await fs.echo(async_upload_chunks, '/output.bin')
```

This is especially useful in containers, serverless environments, and web
applications where disk space is limited. Application code can stream data
incrementally (such as reading FastAPI `UploadFile` in chunks or forwarding
raw `Request.stream()` chunks) without accumulating the complete object in memory.

## The sx shell

The `cli` extra adds an interactive shell and one-shot commands:

```bash
pip install "storix[cli]"

sx                                    # interactive shell (tab-completes paths)
sx -p azure ls -l /media              # one-shot, any provider
sx upload ./video.mp4 /media/         # host -> provider, with a progress bar
```

Configure defaults in `storix.toml`, `pyproject.toml`, or `~/.config/storix/config.toml`:

```toml
[tool.storix.cli]
provider = "azure"
layers = [{ name = "cache", ttl = 300 }]
```

## Sync and async

Storix is async-first. The sync API is generated from the async source so the
two never drift. Use `storix` for sync and `storix.aio` for async:

```python
# Sync
from storix import Storix, get_storage
fs = get_storage('local')
fs.echo(b'hello', '/greeting.txt')

# Async - identical names, awaitable
from storix.aio import Storix, get_storage
fs = get_storage('local')
await fs.echo(b'hello', '/greeting.txt')
```

## Backends

| Backend | Import | Notes |
| --- | --- | --- |
| Local disk | `LocalBackend` | Anchored at a base directory |
| In-memory | `MemoryBackend` | Full reference backend, ideal for tests |
| Azure ADLS Gen2 | `AzureBackend` | HNS accounts; the `azure` provider auto-detects account kind |
| Azure Blob | `AzureBlobBackend` | Any account kind, blob API |
| Amazon S3 | `S3Backend` | Also S3-compatible stores (MinIO, R2) |
| Google Cloud Storage | `GcsBackend` | |

Third-party backends implement the `StorageBackend` protocol and register via
`register_backend()`. See
[Write a custom backend](https://storix.mghalix.com/recipes/custom-backend/).

## Project status

Storix is pre-1.0 (currently v0.4.x) and under active development. It is
used in the maintainer's own production projects.

**What this means in practice:**

- The core API (`ls`, `cat`, `echo`, `mv`, `stream`, `du`, ...) is designed to
  remain stable. These operations follow unix conventions that leave little room
  for ambiguity.
- Breaking changes are possible during 0.x, but they are not made casually.
  Each breaking change gets an [ADR](docs/adr/), migration guidance, and a
  minor version bump (0.4 -> 0.5).
- 27 architecture decision records document the reasoning behind the design.
- A conformance test suite runs against every backend in CI.
- The library is fully typed (`py.typed`) and checked with strict BasedPyright
  and mypy.

If you are evaluating Storix for a project, the safest starting point is
`MemoryBackend` for tests and `LocalBackend` or a single cloud provider for
your application code. The API surface that touches your logic is small and
unlikely to change in ways that are difficult to adapt to.

## Roadmap

The [roadmap](docs/roadmap.md) is organized by the workflows it improves.
Key areas under development or consideration:

- **Streaming reliability** - resumable uploads, progress reporting, range reads
- **Provider capabilities** - broader presigned URL support, content type handling
- **Framework integrations** - pathlib-shaped adapter, flat object-store facade,
  fsspec compatibility
- **Observability** - operation-level events, telemetry hooks
- **Testing tools** - built-in test fixtures, snapshot testing

Community feedback influences priorities. If your workflow would benefit from
a specific improvement, open a
[workflow discussion](https://github.com/mghalix/storix/discussions)
describing what you are building.

## Get involved

Storix is looking for early users who want to build real things, share
workflows, and help shape the project.

**Share your workflow.** The most useful contribution right now is describing
what you are trying to build and where Storix fits or falls short. Start a
[discussion](https://github.com/mghalix/storix/discussions) to explore new
workflows, provider ideas, or API designs.

**Report bugs.** A clear reproduction against any backend is valuable. File a
[bug report](https://github.com/mghalix/storix/issues/new?template=bug_report.yml).

**Contribute code.** See [CONTRIBUTING.md](CONTRIBUTING.md) for setup,
conventions, and the pull request workflow. Small self-contained fixes can go
directly to a pull request.

**Challenge the design.** Disagreement is welcome when it is respectful and
grounded in a real use case. The project's
[architecture decisions](docs/adr/) are documented precisely so they can be
questioned.

## Resources

- [Documentation](https://storix.mghalix.com) - guides, recipes, and API reference
- [Samples](samples/) - runnable examples covering common patterns
- [Architecture](docs/design/architecture.md) - ports-and-adapters design overview
- [ADRs](docs/adr/) - 27 architecture decision records
- [Roadmap](docs/roadmap.md) - planned work and priorities
- [Release notes](https://storix.mghalix.com/release-notes/) - changelog

## License

Apache 2.0. See [LICENSE](./LICENSE).
