---
hide:
  - navigation
  - toc
---

<p align="center">
  <img src="assets/storix-banner.png" alt="Storix" style="width: 100%; max-width: 720px;">
</p>

<p align="center"><strong>Storage for Unix lovers.</strong></p>

<p align="center">
One unix-flavored filesystem API over <em>any</em> storage — local disk,
in-memory, Azure Data Lake — sync <em>and</em> async, sandboxable, fully typed.
</p>

---

## The pitch

You already know how to use a filesystem: `ls`, `cd`, `cat`, `mkdir`, `mv`, `rm`.
Storix gives you that exact mental model over **any** backend — your disk, an
in-memory store for tests, or Azure Data Lake in production — behind one small,
fully-typed API. Same code, sync or async. Swap the backend, keep the code.

It isn't a plumbing competitor to the cloud SDKs; it's the **ergonomic layer**
over them — the way FastAPI is a layer over the web, not a new web server.

```python
from storix import Storix
from storix.backends import LocalBackend

fs = Storix(LocalBackend("~/data"))     # '/' is anchored at ~/data

fs.mkdir("/docs")
fs.echo(b"hello, storix!", "/docs/readme.txt")
print(fs.cat("/docs/readme.txt"))       # b'hello, storix!'

fs.cd("/docs")                          # sessions have a cwd, like a shell
fs.mv("readme.txt", "/archive")         # last argument is the destination, like mv
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

## Sync or async — same API

The async flavor lives under `storix.aio` and is *generated* from the sync
source of truth, so the two never drift.

=== "Sync"

    ```python
    from storix import get_storage

    fs = get_storage("azure")                       # env-driven
    fs.echo(b"...", "/report.csv")
    print(fs.url("/report.csv", expires_in=600))    # presigned SAS link
    ```

=== "Async"

    ```python
    from storix.aio import get_storage

    async with get_storage("azure") as fs:
        await fs.echo(b"...", "/report.csv")
        print(await fs.url("/report.csv", expires_in=600))
    ```

## What makes it different

<div class="grid cards" markdown>

-   :material-console:{ .lg .middle } **Unix semantics, everywhere**

    ---

    `ls`/`cd`/`cat`/`du`/`mv` with a real session and cwd, identical across
    local, memory, and cloud. There's even an `sx` shell.

-   :material-layers-triple:{ .lg .middle } **Composable layers**

    ---

    Sandbox a session (escape-proof `chroot`), add a read-through cache, or
    backfill capabilities — all as middleware that wraps any backend.

-   :material-shield-lock:{ .lg .middle } **Typed and safe**

    ---

    Fully typed, `py.typed`. Every failure raises a typed error; nothing is
    silently dropped. Sandboxes can't be escaped, even by the code inside them.

-   :material-sync:{ .lg .middle } **Sync *and* async**

    ---

    One API, both flavors, generated from a single source and proven by one
    conformance suite running against every backend.

</div>

!!! note "Early days"

    Storix is pre-1.0 and moving fast. These docs grow with it — start with the
    quickstart above, and follow the repo for what's next.

<p align="center" markdown>
[:fontawesome-brands-github: GitHub](https://github.com/mghalix/storix){ .md-button }
[:fontawesome-brands-python: PyPI](https://pypi.org/project/storix/){ .md-button }
</p>
