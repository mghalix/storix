---
title: Storix
hide:
  - toc
---

# Storix { .hidden }

<p align="center">
  <img src="assets/storix-banner.png" alt="Storix" style="width: 100%; max-width: 720px;">
</p>

<p align="center"><strong>Storage for Unix lovers.</strong></p>

<p align="center">
One unix-flavored filesystem API over any storage: local disk, in-memory,
Azure Data Lake. Python-first, sync and async, sandboxable, fully typed.
</p>

---

You already know how to use a filesystem: `ls`, `cd`, `cat`, `mkdir`, `mv`, `rm`.
Storix gives you that exact mental model over any backend (your disk, an
in-memory store for tests, or Azure Data Lake in production) behind one small,
fully typed API. Same code, sync or async. Swap the backend, keep the code.

It is not a plumbing competitor to the cloud SDKs. It is the ergonomic layer
over them, the way FastAPI is a layer over the web rather than a new web server.

```python
from storix import Storix
from storix.backends import LocalBackend

fs = Storix(LocalBackend("~/data"))     # '/' is anchored at ~/data

fs.mkdir("/docs")
fs.echo(b"hello, storix!", "/docs/readme.txt")
print(fs.cat("/docs/readme.txt"))       # b'hello, storix!'

fs.cd("/docs")                          # a session has a cwd, like a shell
fs.mv("readme.txt", "/archive")         # the last argument is the destination
```

## Install

=== "uv"

    ```bash
    uv add storix            # local filesystem + in-memory
    uv add "storix[azure]"   # + Azure Data Lake Gen2 (HNS accounts)
    ```

=== "pip"

    ```bash
    pip install storix
    pip install "storix[azure]"
    ```

New here? Start with the [Introduction](get-started/introduction.md), or jump
straight to the [Quickstart](get-started/quickstart.md).

## Highlights

- **Unix semantics, everywhere.** `ls`/`cd`/`cat`/`du`/`mv` with a real session
  and cwd, identical across local, memory, and cloud. There is even an `sx` shell.
- **Python-first and streaming.** `echo` takes native Python: `bytes`, `str`, an
  `Iterator[bytes]`, or an `AsyncIterator[bytes]`. Large files move through
  bounded memory instead of being loaded whole. See
  [Reading and writing](guide/reading-and-writing.md).
- **Composable layers.** Sandbox a session (escape-proof chroot), add a
  read-through cache, or backfill capabilities, all as middleware that wraps any
  backend.
- **Sync and async, one API.** The async flavor under `storix.aio` is generated
  from a single source of truth and proven by one conformance suite across every
  backend.
- **Typed and safe.** Fully typed and `py.typed`. Every failure raises a typed
  error; nothing is silently dropped. A sandbox cannot be escaped, not even by
  the code running inside it.
