---
title: Storix
description: A typed, streaming-first filesystem API for local storage, Azure, S3, and GCS, with sync and async Python interfaces.
social_preview: true
hide:
  - toc
---

# Storix { .hidden }

<div class="brand-banner">
  <img class="brand-banner__image brand-banner__image--dark" src="assets/storix-banner.png" alt="Storix - Storage for Unix lovers.">
  <img class="brand-banner__image brand-banner__image--light" src="assets/storix-banner-light.png" alt="Storix - Storage for Unix lovers.">
</div>

<p align="center">
An async-first, streaming-first storage SDK for modern Python applications.
</p>

---

You already know how to use a filesystem: `ls`, `cd`, `cat`, `mkdir`, `mv`, `rm`.
Storix gives you that exact mental model over any backend (local disk, an
in-memory store for tests, Azure, S3, or GCS) behind one small,
fully typed API. Same code, sync or async. Swap the backend, keep the code.

```python
import asyncio
from storix.aio import Storix
from storix.aio.backends import MemoryBackend

async def main() -> None:
    fs = Storix(MemoryBackend())           # zero setup, runs anywhere

    await fs.mkdir('/reports')
    await fs.echo(b'quarterly numbers', '/reports/q1.txt')

    print(await fs.cat('/reports/q1.txt'))  # b'quarterly numbers'
    print(await fs.ls('/reports'))          # [StorixPath('q1.txt')]
    print(await fs.du('/reports'))          # 17

if __name__ == '__main__':
    asyncio.run(main())
```

## Install

=== "pip"

    ```bash
    pip install storix               # local filesystem + in-memory
    pip install "storix[azure]"      # + Azure Storage (ADLS Gen2 + Blob)
    pip install "storix[s3]"         # + Amazon S3 (also R2 / MinIO)
    pip install "storix[gcs]"        # + Google Cloud Storage
    pip install "storix[cli]"        # + the sx command-line shell
    pip install "storix[all]"        # everything
    ```

=== "uv"

    ```bash
    uv add storix            # local filesystem + in-memory
    uv add "storix[azure]"   # + Azure Storage (ADLS Gen2 + Blob)
    uv add "storix[s3]"      # + Amazon S3 (also R2 / MinIO)
    uv add "storix[gcs]"     # + Google Cloud Storage
    uv add "storix[cli]"     # + the sx command-line shell
    uv add "storix[all]"     # all optional features
    ```

New here? Start with the [Introduction](get-started/introduction.md), or jump
straight to the [Quickstart](get-started/quickstart.md).

Have a workflow to discuss? Start a [GitHub Discussion](https://github.com/mghalix/storix/discussions)
to explore data pipelines, provider integrations, or API ideas with the community.

## Highlights

- **Unix semantics, everywhere.** `ls`/`cd`/`cat`/`du`/`mv` with a real session
  and cwd, identical across local, memory, and cloud. The `cli` extra adds an
  `sx` shell.
- **Python-first and streaming.** `echo` takes native Python: `bytes`, `str`, an
  `Iterator[bytes]`, or an `AsyncIterator[bytes]`. Data streams through
  bounded memory without accumulating in application memory. See
  [Reading and writing](guide/reading-and-writing.md).
- **Composable layers.** Sandbox a session (escape-proof chroot), add a
  read-through cache, or track transfer progress, all as middleware that wraps any
  backend.
- **Sync and async, one API.** The sync flavor under `storix` is generated
  from the async source of truth (`storix.aio`) and proven by one conformance suite across every
  backend.
- **Typed and safe.** Fully typed and `py.typed`. Every failure raises a typed
  error; nothing is silently dropped. A sandbox cannot be escaped, not even by
  the code running inside it.
