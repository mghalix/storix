# Release Notes

## [0.2.0] - unreleased

Ground-up hexagonal rework: one core engine (`Storix`) owns every unix
semantic over a small backend port; the sync flavor is generated from
the async source of truth. Breaking release.

### Added

- `MemoryBackend` (dict-backed reference backend) alongside `LocalBackend`
  and the HNS-only `AzureBackend`.
- Layers - backends that wrap backends: `SandboxLayer` (chroot as
  middleware), `DataUrlLayer` and `MetadataLayer` (portable capabilities
  - url() and custom metadata on backends that lack them natively), and
  `LayerBase` for writing your own. `when_missing`/`with_layer(unless=)`
  prefer native capabilities so one construction path spans providers.
- `temporary()` and `scratch(backend, root=...)` disposable/pinned
  workspaces; `fs.scratch()` on any session.
- Capabilities with typed gates: `content_type`, `custom_metadata`
  (write-through + `fs.set_metadata(..., merge=)`), `presigned_urls`
  (`fs.url()`, SAS on Azure) and the backend-agnostic `fs.data_url()`.
- Typed factory: `get_storage('azure', container=...)` with full IDE
  completion, `register_backend()` + `available_providers()` for third
  parties.
- `fs.locate()` returns a physical URI (file://, abfss://) for audit/
  cross-system reference, resolved through any sandbox.
- `MetadataLayer` takes a pluggable `serializer` (default stdlib json;
  pass `orjson` or any bytes dumps/loads).
- Typed, fact-carrying error taxonomy (`storix.errors`) with errno and
  dual stdlib inheritance; every failure raises - no boolean returns.
- `py.typed`: the package is now typed for downstream checkers.

### Changed (breaking)

| 0.1.x | 0.2.0 |
|---|---|
| `LocalFilesystem(...)` | `Storix(LocalBackend(base))` |
| `AzureDataLake(...)` | `Storix(AzureBackend(container, account_name=..., credential=...))` |
| `STORAGE_*` / `ADLSG2_*` env vars | `STORIX_PROVIDER`, `STORIX_LOCAL_*`, `STORIX_AZURE_*` (see env.example) |
| `touch(path, data)` | `touch(*paths)` creates/refreshes only; data goes through `echo` |
| `rm(path)` file-only + `rmdir(recursive=True)` | `rm(*paths, recursive=True)` is rm -r; `rmdir(*paths)` strictly empty dirs |
| `mv(src, dst)` / `cp(src, dst)` | variadic, last argument is the destination (unix) |
| `ls()` shows dotfiles | hidden by default; `ls(all=True)` shows them |
| failed ops return `False` | typed exceptions, always |
| `sandboxed=True` constructor flag | explicit `SandboxLayer(backend, root=...)` composition |
| `FileProperties.file_kind` | `FileProperties.kind` |
| `PathNotFoundError` subclasses `ValueError` | subclasses `FileNotFoundError` only |

### Known gaps in this release

- `tree`/`find`/`wc` are not yet reimplemented on the new core.
- Azure behavior is wire-verified: the full conformance suite (80
  integration params, both flavors) passes against a real HNS account.


## [0.1.3] - 2026-07-05

### Fixed

- Loosened dependency lower bounds to their tested minimums so `storix` no longer
  conflicts with packages that pin older versions (e.g. `pyrit`'s `aiofiles>=24,<25`):
  `aiofiles>=24.1.0`, `rich>=13.0.0`, `typer>=0.13.0`, `loguru>=0.7.2`,
  `azure-storage-file-datalake>=12.14.0`, `aiohttp>=3.9.0`. No code changes;
  functionality is identical to 0.1.2.
- Removed the unused `rich-toolkit` dependency from the `cli` extra.

## [0.1.2] - 2026-06-02

### Improvements

- `StorixPath` is now always in POSIX path form, making it platform-agnostic across
  Windows and Unix systems.
- `StorixPath` is now recognized by Pydantic as a valid type for model fields and
  validation.

### Internal

- `storix.errors` is now eagerly imported (no longer lazy-loaded), since the module
  is lightweight and needed at import time for isinstance checks.

## [0.1.0] - 2025-12-14

### Highlights

- Add test coverage for `du()` / `stat()` and `StorixPath` helpers across providers.

### BREAKING CHANGES

- `ls()` now always returns `StorixPath` items (never `str`).

    Migration:
    - If you previously relied on strings, convert explicitly:

        ```python
        files = fs.ls("/")
        names = [p.name for p in files]
        paths_as_str = [str(p) for p in files]
        ```

### Internal

- Added test coverage for `du`/`stat` and `StorixPath` helpers across providers.

## [0.0.3] - 2025-12-14

### Features

- Smart MIME type inference when writing files (path-first → buffer sniff →
  default), with explicit `content_type` override for sync/async Azure `touch`
  and `echo`.
- New helpers: `storix.utils.detect_mimetype` and
  `storix.utils.guess_mimetype_from_path`.
- Unified missing-path exception: `PathNotFoundError` (subclasses
  `FileNotFoundError` & `ValueError`) replacing previous raw `ValueError` while
  keeping backward compatibility.
- Introduce StorixPath as the standardized return for logical path operations + bonus
  defined operations such as mimetype detection and file type guess
- Introduce new function `echo` for efficient streaming writes
- Introduce simple implementation of `tree` and extras such as `wc` and `find`

### Fixes

- Storage protocols are now runtime checkable to easily check isinstance() and support
  for tools that enforce type hints through instance checks like pydantic
- settings are loaded by `get_settings`; to avoid cached settings, allowing
  manipulation of environment dynamically during runtime affecting filesystems
  initialization defaults and `get_storage()`.

## [0.0.2] – 2025‑10‑16

### Highlights

- **Python 3.12+ support** – raised the minimum Python version to 3.12 (tested
  on 3.13) and dropped support for older versions.
- **`src` layout & build upgrade** – moved all code under the `src/` directory
  and switched from `hatchling` to **uv_build** for packaging. This aligns with
  best practices and simplifies installation via `uv`.
- **Lazy imports & module reorganisation** – refactored modules into `storix`
  and `storix.aio` packages under `src`, introducing `__getattr__` to lazily load
  providers (avoids importing optional dependencies until needed).
- **Sandbox refactor** – replaced `PathSandboxable` with **PathSandboxer** and
  `SandboxedPathHandler`, strengthening sandbox enforcement and path‑resolution
  logic to block traversal & symlink escapes.
- **New utility & model modules** – added `storix/utils` (e.g. `to_data_url`,
  `PathLogicMixin`) and data models such as `AzureFileProperties` to standardize
  metadata returned by `stat()`.
- **Scripts & CLI updates** – updated scripts (`coverage`, `format`, `lint`) to
  operate on the new `src` layout; `pyproject.toml` now defines pytest discovery
  paths and richer `ruff` formatting/linting rules.
- **Miscellaneous improvements** – improved `get_storage()` typing
  (`StrPathLike`), added lazy provider lookup maps, fixed configuration for
  docstring formatting, and defined version statically rather than dynamically.

### Migration notes

- **Sandbox handlers** – if you rely on custom sandbox handlers, update them to
  implement `PathSandboxer` rather than the old `PathSandboxable` interface.
- **Async API** – the asynchronous API remains identical; just import from
  `storix.aio` and use `await` on file operations.

## [0.0.1] - 2024-07-06

### 🎉 Initial Release

Storix is a blazing-fast, secure, and developer-friendly storage abstraction
for Python that provides Unix-style file operations across local and cloud
storage backends.

### ✨ Key Features

- **Unified API**: Seamless sync and async support with identical interfaces
- **Local Filesystem & Azure Data Lake Storage Gen2**: Production-ready backends
- **CLI Tool (`sx`)**: Interactive shell and command-line interface
- **Sandboxing**: Secure file operations with path traversal protection
- **Smart Configuration**: Automatic `.env` discovery and environment variable support

### 📦 Installation

```bash
# Basic (local filesystem only)
uv add storix

# With CLI tools
uv add "storix[cli]"

# With Azure support
uv add "storix[azure]"

# Everything included
uv add "storix[all]"
```

### 🚀 Quick Start

```python
from storix import get_storage

fs = get_storage()
fs.touch("hello.txt", "Hello, Storix!")
content = fs.cat("hello.txt").decode()
print(content)  # Hello, Storix!
```

### 🔧 Configuration

Create a `.env` file:

```env
STORAGE_PROVIDER=local
STORAGE_INITIAL_PATH=.
STORAGE_INITIAL_PATH_LOCAL=/path/to/your/data
STORAGE_INITIAL_PATH_AZURE=/your/azure/path
ADLSG2_CONTAINER_NAME=my-container
ADLSG2_ACCOUNT_NAME=my-storage-account
ADLSG2_TOKEN=your-sas-token-or-account-key
```

### 📚 Documentation

- [GitHub Repository](https://github.com/mghalix/storix)
- [Sandbox Implementation](docs/SANDBOX_IMPLEMENTATION.md)
- [Async Migration Guide](docs/ASYNC_MIGRATION.md)

---

## Version History

### <0.1.2> – 2026-06-02

- `StorixPath` is now always in posix path form - platform agnostic.
- `StorixPath` is now recognized by pydantic.
- `storix.errors` is now eagerly imported for reliable isinstance checks.

### <0.1.1> – 2026-06-02 *(yanked — republished as 0.1.2)*

### <0.1.0> – 2025-12-14

- Breaking: `ls()` now always returns `StorixPath` items (never `str`).
- Added test coverage for `du()` / `stat()` and `StorixPath` helpers across providers.

### <0.0.3> – 2025-12-14

- Smart MIME type inference for sync/async Azure `touch()` and `echo()` (with explicit
  `content_type` override).
- Added `storix.utils.detect_mimetype()` and `storix.utils.guess_mimetype_from_path()`.
- Unified missing-path exception as `PathNotFoundError` (subclasses `FileNotFoundError`
  & `ValueError`).

### <0.0.2> – 2025‑10‑16

- Introduced Python 3.12+ requirement and removed support for Python < 3.12.
- Adopted a `src` layout and switched packaging to `uv_build`.
- Implemented lazy imports via `__getattr__` and reorganized modules under
  `storix` and `storix.aio`.
- Refactored sandbox to use `PathSandboxer`/`SandboxedPathHandler`.
- Added new utility and model modules (`utils`, `AzureFileProperties`).
- Updated scripts and tooling (`coverage`, `format`, `lint`, `pyproject.toml`).

### <0.0.1> - 2024-07-06

- Initial release with local filesystem and Azure Data Lake Storage Gen2 support
- Sync and async APIs with unified interface
- CLI tool with interactive shell
- Sandboxing and security features
- Comprehensive test suite and documentation
