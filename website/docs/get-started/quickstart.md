# Quickstart

This walks through your first storix session end to end. Everything here runs
against real local disk, but the exact same code runs against any backend, which
is the whole point.

## Open a session

A session is anchored at a backend. `LocalBackend("~/storix-data")` makes that
directory the root, so inside the session `/` means `~/storix-data` and you can
never wander above it.

```python
from storix import Storix
from storix.backends import LocalBackend

fs = Storix(LocalBackend("~/storix-data"))
print(fs.pwd())   # / , the session starts at its home
```

## Create and read

```python
fs.mkdir("/notes")
fs.echo("buy milk", "/notes/todo.txt")

print(fs.cat("/notes/todo.txt"))   # b'buy milk'
print(fs.exists("/notes/todo.txt"))  # True
```

`echo` writes, `cat` reads. `echo` accepts native Python: `bytes`, `str`, or an
iterator of chunks (more on that in [Reading and writing](../guide/reading-and-writing.md)).

## Navigate like a shell

A session has a working directory, so relative paths and `cd` work exactly as in
a terminal.

```python
fs.cd("/notes")
print(fs.pwd())          # /notes
print(fs.ls())           # [StorixPath('todo.txt')]
fs.echo("...", "idea.txt")   # relative to the cwd -> /notes/idea.txt
```

`ls` hides dotfiles by default, like the real thing. Pass `all=True` to show them.

## Move, copy, remove

Move and copy are variadic, and the last argument is the destination, just like
unix `mv` and `cp`.

```python
fs.mkdir("/archive", parents=True)  # mkdir -p; safe if it already exists
fs.mv("/notes/todo.txt", "/notes/idea.txt", "/archive")  # both into /archive
fs.rm("/notes", recursive=True)                          # rm -r
```

Every one of these raises a typed error on failure (for example
`PathNotFoundError`), so you never have to check a boolean return.

## Swap the backend, keep the code

Here is the payoff. Point the same code at the in-memory backend, and nothing
else changes. This is what makes tests fast and hermetic.

```python
from storix.backends import MemoryBackend

fs = Storix(MemoryBackend())   # nothing on disk
fs.mkdir("/notes")
fs.echo("buy milk", "/notes/todo.txt")
print(fs.cat("/notes/todo.txt"))   # b'buy milk'
```

Swap `MemoryBackend()` for `AzureBackend(...)` and the same code talks to Azure
Data Lake. See [Backends](../guide/backends.md).

## The async flavor

Every operation has an awaitable twin under `storix.aio`, with identical names.
Storix is async-first, and the sync package is generated from that source so the
two never diverge.

```python
from storix.aio import Storix
from storix.aio.backends import MemoryBackend

async def main():
    async with Storix(MemoryBackend()) as fs:
        await fs.echo("buy milk", "/todo.txt")
        print(await fs.ls())
        print(await fs.cat("/todo.txt"))
```

## Where to next

- [Reading and writing](../guide/reading-and-writing.md): streaming, iterators,
  and keeping memory bounded on large files.
- [Backends](../guide/backends.md): the port, configuration, and going to the cloud.
- [Layers](../guide/layers.md): sandboxing, caching, and capabilities.
