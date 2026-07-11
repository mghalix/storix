# Storix: Storage for Unix Lovers

**One unix-flavored filesystem API over any storage - local disk, in-memory,
Azure Data Lake - sync and async, sandboxable, fully typed.**

[![PyPI version](https://badge.fury.io/py/storix.svg)](https://pypi.org/project/storix/)
[![GitHub stars](https://img.shields.io/github/stars/mghalix/storix.svg?style=social)](https://github.com/mghalix/storix)
[![License](https://img.shields.io/github/license/mghalix/storix.svg)](https://github.com/mghalix/storix/blob/main/LICENSE)

![storix-icon](./.github/assets/storix-icon.png)

> **0.2.0 is a ground-up rework** (hexagonal core, generated sync flavor,
> layers, capabilities). Migrating from 0.1.x? See the table in
> [release-notes.md](./release-notes.md). Full documentation site: coming soon.

---

## Install

```bash
uv add storix            # local filesystem + in-memory
uv add "storix[azure]"   # + Azure Data Lake Gen2 (HNS accounts)
```

## Five minutes of storix

```python
from storix import Storix
from storix.backends import LocalBackend

fs = Storix(LocalBackend('~/data'))     # '/' is anchored at ~/data

fs.mkdir('/docs')
fs.echo(b'hello, storix!', '/docs/readme.txt')
print(fs.cat('/docs/readme.txt'))       # b'hello, storix!'

fs.cd('/docs')                          # sessions have a cwd, like a shell
fs.touch('a.txt', 'b.txt')              # variadic, like real touch
print(fs.ls())                          # dotfiles hidden, like real ls
fs.mkdir('/archive')
fs.mv('a.txt', 'b.txt', '/archive')     # last argument is the destination
fs.rm('/archive', recursive=True)       # rm -r; rmdir is strictly empty dirs
```

Async is the same API under `storix.aio` - every operation awaitable:

```python
from storix.aio import Storix
from storix.aio.backends import AzureBackend

async with Storix(AzureBackend('raw', account_name=..., credential=...)) as fs:
    await fs.echo(b'...', '/report.csv')
    print(await fs.url('/report.csv', expires_in=600))   # SAS link
```

(The sync flavor is *generated* from the async source - identical semantics,
verified by one conformance suite running against every backend in both
flavors.)

## Configuration

`get_storage()` builds a session from the environment (see
[env.example](./env.example)):

```bash
STORIX_PROVIDER=azure
STORIX_AZURE_CONTAINER=raw
STORIX_AZURE_ACCOUNT_NAME=myaccount
STORIX_AZURE_CREDENTIAL=...
```

```python
from storix import get_storage

fs = get_storage()                        # env-driven; defaults to ~/.storix
fs = get_storage('local', base='~/x')     # typed per-provider overrides
```

## Sandboxing & scratch spaces

Layers are backends that wrap backends. `SandboxLayer` is chroot as
middleware - escape-proof, with errors re-scoped so the real prefix never
leaks to the sandboxed caller:

```python
from storix import SandboxLayer, Storix, temporary
from storix.backends import LocalBackend

backend = LocalBackend('/srv/data')
fs = Storix(SandboxLayer(backend, root='/tenant-42'))   # escape-proof jail

with fs.scratch() as tmp:               # ephemeral workspace on fs's OWN
    tmp.echo(b'work', '/notes.txt')     # backend (any backend) - unique
                                        # subtree, deleted on exit

with fs.scratch(root='/agent-7') as tmp:  # pinned: created if missing,
    ...                                   # reused, PERSISTS on exit

with temporary() as fs:                 # local-only convenience: zero-config
    fs.echo(b'scratch', '/tmp.txt')     # mkdtemp on real disk, self-destructs
```

Write your own layers by subclassing `LayerBase` (override what you
change, upgrade the capabilities you add) — see
[samples/layers/](./samples/layers/).

## Capabilities

Backends advertise optional features; storix fails loudly instead of
silently dropping arguments:

```python
fs.echo(b'x', '/f.png', content_type='image/png')       # azure: stored
fs.set_metadata('/f.png', {'owner': 'me'}, merge=True)  # azure/memory
fs.url('/f.png', expires_in=600)                        # presigned (SAS)
fs.data_url('/f.png')                                   # any backend
# unsupported -> UnsupportedOperationError naming the missing capability
```

**Portable capabilities via layers.** Bundled layers backfill missing
capabilities so one construction path works across providers.
`with_layer_missing` infers the capability from the layer and skips it
where the backend is already native:

```python
from storix import DataUrlLayer, MetadataLayer

# url() everywhere: native SAS on azure, data: URLs on local
fs = get_storage('local').with_layer_missing(DataUrlLayer)
# custom metadata everywhere: native on azure, JSON sidecar on local
fs = fs.with_layer_missing(MetadataLayer)
# with_layer forwards typed kwargs to the layer, Starlette-style
# (serialize/deserialize are object<->bytes; orjson works, json.dumps
# does not - it returns str):
fs = fs.with_layer(MetadataLayer, serialize=orjson.dumps, deserialize=orjson.loads)
```

Switching `'local'` to `'azure'` needs no code change — the native
capability wins and the layer becomes a no-op.

## Backends

| Backend | Import | Notes |
|---|---|---|
| Local disk | `storix.backends.LocalBackend` | anchored at a base directory |
| In-memory | `storix.backends.MemoryBackend` | reference backend; great for tests |
| Azure ADLS Gen2 | `storix.backends.AzureBackend` | requires hierarchical namespaces |

Third-party backends implement the ~13-method `StorageBackend` port (or
subclass `BackendBase` for generic fallbacks) and hook in via
`register_backend()`.

## License

Storix is licensed under the Apache 2.0 License
