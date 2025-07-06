# Sandboxed Filesystem: Implementation Overview

## Introduction

The Storix sandboxed filesystem provides a secure, robust, and consistent interface for file operations, ensuring all actions are confined within a designated directory tree. This system is designed to prevent path traversal, symlink escapes, and unauthorized access, while maintaining seamless compatibility between synchronous and asynchronous APIs.

## Key Features

### Seamless Sync/Async API

-   **Consistent Imports:** Use `from storix import LocalFilesystem` for sync, or `from storix.aio import LocalFilesystem` for async.
-   **Identical Method Signatures:** The only difference is the use of `await` for async methods.
-   **Uniform Behavior:** Both sync and async versions handle paths, errors, and operations identically.

### Comprehensive Sandboxing

-   **Path Restriction:** All file operations are strictly confined to a specified sandbox root.
-   **Virtual Filesystem:** The sandbox root is presented as `/` to the application, abstracting the real filesystem structure.
-   **Security Enforcement:** Prevents path traversal and symlink-based escapes, ensuring no access outside the sandbox.
-   **Dual-Mode Support:** Sandboxing is available for both sync and async APIs.

### Security Mechanisms

-   **Path Traversal Protection:** Blocks `../` escape attempts and normalizes paths using `Path.resolve()`.
-   **Absolute Path Handling:** Converts absolute paths to sandbox-relative, preventing direct external access.
-   **Symlink Security:** Resolves symlinks before validation and blocks those pointing outside the sandbox.
-   **Comprehensive Validation:** All resolved paths are checked to ensure they remain within sandbox boundaries.

### Path Conversion Utilities

-   **Virtual-to-Real:** Converts sandbox paths (e.g., `/file.txt`) to real filesystem paths.
-   **Real-to-Virtual:** Maps real filesystem paths back to sandbox-relative paths.
-   **Decorator Support:** Automatic path conversion for function arguments and return values.
-   **Normalization:** Handles `.`, `..`, `/`, and complex path expressions robustly.

## Implementation Highlights

```python
# Example: Path resolution and sandbox enforcement

def _topath(self, path: PathLike | None = None) -> Path:
    sb: SandboxedPathHandler | None
    if sb := getattr(self, "_sandbox", None):
        path = sb.to_real(path)
        path = path.resolve()  # Normalize and resolve symlinks
        try:
            path.relative_to(sb.get_prefix().resolve())
        except ValueError:
            raise ValueError(f"Path '{path}' escapes sandbox boundaries")
    else:
        path = pipeline(self._parse_dots, self._parse_home, self._makeabs)(path)
    return path
```

```python
# Example: SandboxedPathHandler interface

class SandboxedPathHandler:
    def to_real(self, virtual_path: PathLike | None = None) -> Path:
        # Converts virtual path to real filesystem path, validates boundaries

    def to_virtual(self, real_path: PathLike) -> Path:
        # Converts real filesystem path to virtual sandbox path

    def __call__(self, func):
        # Decorator for automatic path conversion
```

## Security Validation

The sandbox implementation has undergone extensive security testing, including:

-   **Path Traversal Attacks:** Attempts using `../` and similar patterns are blocked.
-   **Absolute Path Escapes:** Absolute paths are safely contained within the sandbox.
-   **Symlink Attacks:** Symlinks pointing outside the sandbox are detected and blocked.
-   **Path Normalization:** Complex path expressions are resolved securely.
-   **Test Coverage:** All 86+ tests pass, with no regressions or vulnerabilities detected.

## Usage Examples

### Synchronous Usage

```python
from storix import LocalFilesystem

# Regular usage
storage = LocalFilesystem("/path/to/data")
storage.touch("file.txt", "content")

# Sandboxed usage
storage = LocalFilesystem("/path/to/data", sandboxed=True, sandbox_handler=SandboxedPathHandler)
storage.touch("/file.txt", "safe content")  # Creates /path/to/data/file.txt
```

### Asynchronous Usage

```python
from storix.aio import LocalFilesystem

# Regular async usage
storage = LocalFilesystem("/path/to/data")
await storage.touch("file.txt", "content")

# Sandboxed async usage
storage = LocalFilesystem("/path/to/data", sandboxed=True, sandbox_handler=SandboxedPathHandler)
await storage.touch("/file.txt", "safe content")  # Creates /path/to/data/file.txt
```

### Migration Path

-   Change import from `storix` to `storix.aio` for async.
-   Add `await` to method calls.
-   Make the calling function `async`.
-   No other changes required.

## Conclusion

The Storix sandboxed filesystem delivers robust, secure, and consistent file operations for both synchronous and asynchronous workflows. Its comprehensive sandboxing and security mechanisms ensure that all file access remains strictly within defined boundaries, protecting sensitive data and preventing unauthorized access. For details on internal architecture, please refer to the developer documentation or architecture-specific guides.
