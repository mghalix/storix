<p align="center">
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/mghalix/storix/main/.github/assets/storix-banner-light.png">
    <img src="https://raw.githubusercontent.com/mghalix/storix/main/.github/assets/storix-banner.png" alt="Storix - Storage for Unix lovers." style="width: 100%; max-width: 880px;">
  </picture>
</p>

<p align="center">
  One unix-flavored filesystem API over any storage: local disk, in-memory,<br>
  Azure, S3, GCS. Python-first, sync and async, sandboxable, fully typed.
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

Storix puts one unix filesystem interface in front of every storage backend, so
you work with cloud storage the way you already work with local files: `ls`,
`cd`, `cat`, `mkdir`, `mv`, `rm`. The backend can be your disk, an in-memory
store for tests, or Azure / S3 / GCS in production, behind one small, fully
typed API, sync or async. Swap the backend, keep the code.

It is not a plumbing competitor to the cloud SDKs. It is the ergonomic layer over
them, the way FastAPI is a layer over the web rather than a new web server.

## Install

```bash
uv add storix            # local filesystem + in-memory
uv add "storix[azure]"   # + all of Azure Storage (ADLS Gen2 + Blob)
uv add "storix[s3]"      # + Amazon S3 (r2 / minio alias it)
uv add "storix[gcs]"     # + Google Cloud Storage
uv add "storix[cli]"     # + the sx command-line interface
uv add "storix[all]"     # all optional features
```

## Quick look

```python
from storix import Storix
from storix.backends import LocalBackend

fs = Storix(LocalBackend('~/storix-data'))  # '/' is anchored at ~/storix-data

fs.mkdir('/docs')
fs.echo('hello, storix!', '/docs/readme.txt')
print(fs.cat('/docs/readme.txt'))       # b'hello, storix!'

fs.cd('/docs')                          # a session has a cwd, like a shell
fs.mkdir('/archive')
fs.mv('readme.txt', '/archive')         # the last argument is the destination
```

Async is the same API under `storix.aio`, generated from the sync source so the
two never drift:

```python
from storix.aio import get_storage

async with get_storage('azure') as fs:
    await fs.echo(b'...', '/report.csv')
    print(await fs.url('/report.csv', expires_in=600))   # presigned SAS link
```

## The sx shell

The `cli` extra puts the same core behind a command line, one-shot or
interactive:

```bash
uv add "storix[cli]"

sx                                    # interactive shell (tab completes paths)
sx -p azure ls -l /media              # or a single command, any provider
sx upload ./video.mp4 /media/         # host -> provider, with a progress bar
```

Listings carry Nerd Font icons and coreutils-style sizes (`165M`); transfers
render progress through the `ObservabilityLayer`. Preferences and an always-on
layer stack persist in `~/.config/storix/config.toml`, a project
`storix.toml`, or `pyproject.toml`:

```toml
[tool.storix.cli]
icons = true
provider = 'azure'                          # what sx opens by default
layers = [{ name = "cache", ttl = 300 }]    # every session, read-through
```

## Highlights

- **Unix semantics, everywhere.** `ls`/`cd`/`cat`/`du`/`mv` with a real session
  and cwd, identical across local, memory, and cloud.
- **Python-first and streaming.** `echo` takes `bytes`, `str`, an iterator, or an
  async iterator, so large files move through bounded memory instead of loading
  whole.
- **Composable layers.** Sandbox a session (escape-proof chroot), add a
  read-through cache, emit transfer progress, or backfill capabilities, all as
  middleware that wraps any backend.
- **Sync and async, one API**, generated from a single source and proven by one
  conformance suite across every backend.
- **Typed and safe.** Fully typed and `py.typed`. Every failure raises a typed
  error, and a sandbox cannot be escaped, not even by the code inside it.

Full tutorials, task recipes (FastAPI, settings, caching, testing, custom
backends), and the API reference live at
**[storix.mghalix.com](https://storix.mghalix.com)**.

## Backends

| Backend | Import | Notes |
| --- | --- | --- |
| Local disk | `storix.backends.LocalBackend` | anchored at a base directory |
| In-memory | `storix.backends.MemoryBackend` | reference backend, great for tests |
| Azure ADLS Gen2 | `storix.backends.AzureBackend` | HNS accounts; the `azure` provider self-detects the account kind |
| Azure Blob | `storix.backends.AzureBlobBackend` | any account kind, blob API |
| Amazon S3 | `storix.backends.S3Backend` | plus S3-compatible stores (MinIO, R2) |
| Google Cloud Storage | `storix.backends.GcsBackend` | |

Third-party backends implement the small `StorageBackend` port and register via
`register_backend()`. See
[Write a custom backend](https://storix.mghalix.com/recipes/custom-backend/).

## Migrating from 0.1.x

0.2.0 was a ground-up rework (hexagonal core, generated sync flavor, layers,
capabilities). See the migration table in the
[release notes](https://storix.mghalix.com/release-notes/).

## License

Apache 2.0. See [LICENSE](./LICENSE).
