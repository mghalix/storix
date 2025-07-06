# Release Notes

## [0.0.1] - 2024-07-06

### 🎉 Initial Release

Storix is a blazing-fast, secure, and developer-friendly storage abstraction for Python that provides Unix-style file operations across local and cloud storage backends.

### ✨ Key Features

-   **Unified API**: Seamless sync and async support with identical interfaces
-   **Local Filesystem & Azure Data Lake Storage Gen2**: Production-ready backends
-   **CLI Tool (`sx`)**: Interactive shell and command-line interface
-   **Sandboxing**: Secure file operations with path traversal protection
-   **Smart Configuration**: Automatic `.env` discovery and environment variable support

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

-   [GitHub Repository](https://github.com/mghalix/storix)
-   [Sandbox Implementation](docs/SANDBOX_IMPLEMENTATION.md)
-   [Async Migration Guide](docs/ASYNC_MIGRATION.md)

---

## Version History

### [0.0.1] - 2024-07-06

-   Initial release with local filesystem and Azure Data Lake Storage Gen2 support
-   Sync and async APIs with unified interface
-   CLI tool with interactive shell
-   Sandboxing and security features
-   Comprehensive test suite and documentation
