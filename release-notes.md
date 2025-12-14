# Release Notes

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
- Introduce `StorixPath` with additional utilities

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
