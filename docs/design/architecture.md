# Architecture: ports and adapters

storix is a hexagonal (ports-and-adapters) design. This note fixes the
vocabulary, because it is easy to say "the backend" and mean three different
things.

## The pieces

```
   driving adapters            application core            driven adapters
  (present the core)              (the hexagon)          (reach real storage)

      sx  (CLI)  ─┐                                      ┌─ LocalBackend
   library code  ─┼──►  ┌───────────────────┐           ├─ MemoryBackend
   (future) MCP  ─┘     │      Storix        │  ──────►  ├─ AzureBackend
                        │  cwd, ~, path       │  Storage  ├─ AzureBlobBackend
                        │  resolution, unix   │  Backend  ├─ S3Backend
                        │  operations         │  (port)   └─ GcsBackend
                        └───────────────────┘
                          driving port = the
                          Storix public API
```

- **Application core** - `Storix` (`_async/core.py`). The hexagon's inside. It
  owns the session's cwd and home, resolves `~`/`..`/relative paths, and
  implements every user-facing operation (`ls`, `cat`, `du`, `mv`, ...). It
  holds no knowledge of any storage technology; it speaks only to the port.

- **Driven port (secondary port)** - `StorageBackend` (`backends/_proto.py`),
  the ~14-method interface. This is the *contract*, the boundary the core
  depends on. It is not an implementation. In `AGENTS.md` this is what "the
  port" means.

- **Driven adapters (secondary adapters)** - `LocalBackend`, `MemoryBackend`,
  `AzureBackend`, `AzureBlobBackend`, `S3Backend`, `GcsBackend`. Each is a
  concrete implementation of the port that adapts one storage technology to it.
  These are the objects that actually produce data: when a listing carries an
  entry's kind and size, it is the *adapter* handing them over, satisfying what
  the port declared.

- **Driving adapters (primary adapters)** - the things that drive the core:
  the `sx` CLI, your own library code, and future front-ends (a pathlib-shaped
  adapter, a flat object-store facade, an MCP server). They present the core to
  a particular audience; they do not add capability to it.

- **Driving port (primary port)** - the public API `Storix` exposes to those
  adapters. storix does not split this into a separate interface class; the
  `Storix` methods *are* the driving port.

## Layers are adapters that are also ports

A layer (`CacheLayer`, `SandboxLayer`, `DataUrlLayer`, `MetadataLayer`,
`ObservabilityLayer`) is the decorator/middleware pattern on the driven side:
it **implements** `StorageBackend` and **wraps** another `StorageBackend`. So a
layer is simultaneously a driven adapter (from the core's view, it is just the
backend) and a driven port consumer (it forwards to the inner backend). That
dual nature is why `Storix(be, layers=[...])` composes: every layer speaks the
same port on both sides.

`fs.layers` reports the wrapping layers outermost-first; `fs.base_backend`
walks past them to the real driven adapter underneath.

## Why the shape

The point of a port is that the core depends on the *contract*, never a
provider SDK. Swap `LocalBackend` for `AzureBackend` and the core - and every
driving adapter above it - is unchanged, because both satisfy `StorageBackend`.
The same lever runs the other way: a new driving adapter (pathlike, flat, MCP)
reuses the whole core and every backend for free.

This is also the boundary rule for contributors (see `AGENTS.md`, "The core
boundary"): a driving adapter must not grow logic the core should own. If `sx`
needs the kind/size a listing already computed, the fix is a core method that
returns it, not a re-implementation in the CLI - otherwise the next driving
adapter re-implements it too, and core semantics drift across copies.

## Where each piece lives

| Role | Code |
| --- | --- |
| Application core | `src/storix/_async/core.py` (`Storix`) |
| Driven port | `src/storix/_async/backends/_proto.py` (`StorageBackend`) |
| Driven adapters | `src/storix/_async/backends/*.py` |
| Layers (adapter + port) | `src/storix/_async/layers/*.py` |
| Driving adapter: CLI | `src/storix/cli/` (`sx`) |
| Factory (wires provider name -> adapter) | `get_storage`, `register_backend` |

The `_sync` twins are generated from `_async` by `scripts/unasync.py`; the
architecture is identical in both flavors.
