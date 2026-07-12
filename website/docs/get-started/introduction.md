# Introduction

Storix is a filesystem for people who already think in filesystems.

Cloud storage SDKs make you relearn storage for every provider: containers and
blobs here, buckets and keys there, each with its own client, its own errors,
its own idea of what a "path" is. Storix hides that behind one idea you already
know: a unix filesystem. You open a session, you get a working directory, and you
call `ls`, `cd`, `cat`, `mkdir`, `mv`, `rm`. The backend underneath can be your
local disk, an in-memory store, or Azure Data Lake, and your code does not change.

## The mental model

A `Storix` session is like a shell logged into one machine:

- It has a current working directory and a home, so relative paths and `cd` work.
- Paths are resolved the unix way: `~`, `..`, and `.` all behave as you expect.
- Every operation raises a typed error on failure. Nothing returns `False` and
  hopes you check it.

Underneath, the session talks to a small `StorageBackend` port (about 14
methods). Backends implement that port and nothing else. They do no path logic
and speak only in storix errors, so the core stays identical across all of them.

## What makes it different

- **Python-first.** `echo` accepts native Python values: `bytes`, `str`, an
  `Iterator[bytes]`, or an `AsyncIterator[bytes]`. You hand storix the data in
  whatever shape you already have it.
- **Streaming and memory-efficient.** Because writes accept iterators and reads
  can stream, a multi-gigabyte file moves through bounded memory in chunks
  instead of being loaded whole. See [Reading and writing](../guide/reading-and-writing.md).
- **Sync and async from one source.** The async API under `storix.aio` is
  generated from the sync source of truth, so the two never drift, and a single
  conformance suite proves both against every backend.
- **Composable layers.** Cross-cutting behavior (sandboxing, caching, capability
  backfill) is middleware that wraps a backend and satisfies the same port, so
  layers compose with backends and with each other. See [Layers](../guide/layers.md).
- **Typed and safe.** The package ships `py.typed`. Errors are a typed taxonomy.
  A sandboxed session cannot see or escape above its root, not even by bypassing
  the core.

## What storix is not

Storix is not trying to out-plumb the cloud SDKs on raw throughput or provider
count. It is the ergonomic layer on top of them, the way FastAPI is a layer over
the web rather than a replacement for it. When you need a provider storix does
not ship, you bring a backend that implements the port, and everything above it
keeps working.

Ready? [Install it](installation.md), then walk through the
[Quickstart](quickstart.md).
