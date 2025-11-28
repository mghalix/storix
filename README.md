# Storix: Storage for Unix Lovers

**A blazing-fast, secure, and developer-friendly storage abstraction for Python.**

[![PyPI version](https://badge.fury.io/py/storix.svg)](https://pypi.org/project/storix/)
[![GitHub stars](https://img.shields.io/github/stars/mghalix/storix.svg?style=social)](https://github.com/mghalix/storix)
[![License](https://img.shields.io/github/license/mghalix/storix.svg)](https://github.com/mghalix/storix/blob/main/LICENSE)

<img src=".github/assets/storix-icon.png"/ alt="storix-icon">

---

## 🎬 Demo

![Storix Interactive Shell Demo](.github/assets/demo.gif)

_Watch storix in action: navigating files, creating directories, and using the interactive shell mode._

---

## 🚀 Getting Started

### 1. Install Storix

Choose the installation that fits your needs:

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

### 2. Configure (Optional)

Create a `.env` file for custom settings:

```bash
cp env.example .env
# Edit .env with your preferences
```

### 3. Start Using

```python
from storix import get_storage

fs = get_storage()
fs.touch("hello.txt", "Hello, Storix!")
```

---

## 💡 Quick Examples

```python
# Basic file operations
from storix import get_storage

fs = get_storage()
fs.touch("hello.txt", "Hello, World!")
content = fs.cat("hello.txt").decode()
print(content)  # Hello, World!

# List files
files = fs.ls("/")
print(files)  # ['hello.txt']

# Create directories
fs.mkdir("mydata", parents=True)
fs.touch("mydata/config.json", '{"key": "value"}')
```

```python
# Async operations
from storix.aio import get_storage

async def main():
    fs = get_storage()
    await fs.touch("async.txt", "Async is easy!")
    content = await fs.cat("async.txt")
    print(content.decode())  # Async is easy!
```

---

## 🛠️ Quickstart

### Install

```bash
# Basic installation (local filesystem only)
uv add storix
# or
pip install storix

# With CLI support
uv add "storix[cli]"
# or
pip install "storix[cli]"

# With Azure support
uv add "storix[azure]"
# or
pip install "storix[azure]"

# With everything (CLI + Azure)
uv add "storix[all]"
# or
pip install "storix[all]"
```

### Development Installation

```bash
# Clone the repository
git clone https://github.com/mghalix/storix.git
cd storix

# Install dependencies and setup development environment
uv sync
uv run pip install -e .
```

### CLI Configuration (Optional)

Create a `.env` file to customize your storage settings. Storix will automatically find your `.env` file in:

1. **Current directory** (where you run the command)
2. **Parent directories** (searches up the directory tree)
3. **Home directory** (`~/.storix/.env`)

```bash
# Copy the example configuration
cp env.example .env
```

Then edit `.env` with your preferences:

```env
# Storage Provider (local or azure)
STORAGE_PROVIDER=local

# Initial paths for different providers
STORAGE_INITIAL_PATH=.
STORAGE_INITIAL_PATH_LOCAL=/path/to/your/data
STORAGE_INITIAL_PATH_AZURE=/your/azure/path

# Azure credentials (only needed for azure provider)
ADLSG2_CONTAINER_NAME=my-container
ADLSG2_ACCOUNT_NAME=my-storage-account
ADLSG2_TOKEN=your-sas-token-or-account-key
```

**Smart Discovery**: You can run `sx` from any subdirectory of your project and it will find your `.env` file automatically!

**Path Configuration**:

- `STORAGE_INITIAL_PATH` is the shared default path for all providers
- `STORAGE_INITIAL_PATH_LOCAL` and `STORAGE_INITIAL_PATH_AZURE` override the shared path for specific providers
- Provider-specific paths take precedence over the shared path

### CLI Usage

```bash
# List files in current directory
sx ls

# Interactive shell
sx

# Switch providers
sx -p local ls

# Create directory
sx mkdir mydata

# Upload file
sx upload local_file.txt remote_file.txt
```

### Basic Usage

```python
from storix import LocalFilesystem

fs = LocalFilesystem("/tmp/mydata")
fs.touch("hello.txt", "Hello, world!")
print(fs.cat("hello.txt").decode())
```

### Sandboxed Usage

```python
from storix import LocalFilesystem

fs = LocalFilesystem("/tmp/sandbox", sandboxed=True)
fs.touch("/secret.txt", "sandboxed!")
print(fs.ls("/"))  # ['secret.txt']
```

### Async Usage

```python
from storix.aio import LocalFilesystem

fs = LocalFilesystem("/tmp/mydata")
await fs.touch("async.txt", "Async is easy!")
print((await fs.cat("async.txt")).decode())
```

---

## 🗄️ Supported Backends

| Backend                          | Sync | Async | Sandboxed | Status  |
| -------------------------------- | ---- | ----- | --------- | ------- |
| **Local Filesystem**             | ✅   | ✅    | ✅        | Beta    |
| **Azure Data Lake Storage Gen2** | ✅   | ✅    | ✅        | Beta    |
| **AWS S3**                       | ❌   | ❌    | ❌        | Planned |
| **Google Cloud Storage**         | ❌   | ❌    | ❌        | Planned |

## 🔌 Integrations

### FastAPI Integration

Storix integrates seamlessly with FastAPI for dependency injection and async file operations:

```python
from typing import AsyncGenerator
from fastapi import Depends, FastAPI
from typing_extensions import Annotated

import storix as sx

app = FastAPI()

async def get_fs() -> AsyncGenerator[sx.Storage, None]:
    """Dependency to provide storage service."""
    async with sx.get_storage() as fs:
        yield fs

StorageDep = Annotated[sx.Storage, Depends(get_fs)]

@app.get("/files/{file_path:path}")
async def read_file(file_path: str, fs: StorageDep):
    """Read a file from storage."""
    content = await fs.cat(file_path)
    return {"content": content.decode()}

@app.post("/files/{file_path:path}")
async def write_file(file_path: str, content: str, fs: StorageDep):
    """Write content to a file."""
    success = await fs.touch(file_path, content)
    return {"success": success}
```

**Configuration**: Set `STORAGE_PROVIDER` in your `.env` file to choose your backend:

```
# For local filesystem
STORAGE_PROVIDER=local
STORAGE_INITIAL_PATH_LOCAL=/path/to/local/data

# For Azure Data Lake
STORAGE_PROVIDER=azure
STORAGE_INITIAL_PATH_AZURE=/your/azure/path
ADLSG2_ACCOUNT_NAME=your_account
ADLSG2_TOKEN=your_token
ADLSG2_CONTAINER_NAME=your_container
```

> Notes
>
> > **Local:**
> >
> > - if `STORAGE_INITIAL_PATH` set to "~", gets mapped to your home directory
> > - if `STORAGE_INITIAL_PATH` set to ".", gets mapped to your current working directory
>
> > **Azure:**
> >
> > - if `STORAGE_INITIAL_PATH` set to "~", gets mapped to root "/"
> > - if `STORAGE_INITIAL_PATH` set to ".", gets mapped to root "/"

## 🖼️ Media Support

Storix makes it effortless to store and retrieve images or any binary media files—just use Python's `bytes` type.

### Write an Image to Storage

```python
from storix import get_storage

fs = get_storage()
with open("my_photo.jpg", "rb") as img_file:
    img_bytes = img_file.read()
fs.touch("photos/profile.jpg", img_bytes)
```

### Read an Image from Storage

```python
from storix import get_storage

fs = get_storage()
img_bytes = fs.cat("photos/profile.jpg")
# Now you can use img_bytes with PIL, OpenCV, or send it in a web response...
```

### Async Example

```python
from storix.aio import get_storage

fs = get_storage()
async with fs:
    img_bytes = await fs.cat("photos/profile.jpg")
    await fs.touch("photos/backup.jpg", img_bytes)
```

**It's that simple:**

- No special APIs for media—just use `bytes` for any file type.
- Works for images, audio, video, or any binary data.
- Seamless support for both sync and async code.

## ✨ Features

- **Sync & Async APIs:**
  Use `from storix import LocalFilesystem` or `from storix.aio import LocalFilesystem` — just add `await` for async!
- **Sandboxing:**
  Restrict all file operations to a virtual root, blocking path traversal and symlink escapes.
- **Consistent Path Handling:**
  Absolute and relative paths, `cd`, `ls`, and more — just like a shell.
- **Decorator Support:**
  Automatic path conversion for your own functions.
- **Easy Migration:**
  Switch from sync to async in seconds.
- **CLI Tool:**
  Manage files and sandboxes from your terminal.

---

## 🚀 Why storix

- **Unified API:** Seamless sync and async support with identical interfaces.
- **Rock-solid sandboxing:** Secure your file operations with robust path traversal and symlink protection.
- **Plug-and-play:** Instantly switch between local and cloud (Azure) backends.
- **CLI included:** Script and automate storage tasks from the command line.
- **Extensible:** Clean, modern codebase ready for new providers and features.
- **Tested & Secure:** Comprehensive test suite and security-first design.

---

## 🔒 Security

- **Path Traversal Protection:**
  All `../` and symlink escapes are blocked.
- **Virtual Root:**
  Sandboxed mode makes `/` map to your chosen directory.
- **Symlink Safety:**
  Symlinks are resolved and validated before access.

---

## 🙋 Need Help or Found a Bug?

If you run into any issues, have questions, or spot a bug, please [open an issue](https://github.com/mghalix/storix/issues) on the GitHub repository.

We welcome all feedback and contributions—your input helps make Storix better for everyone!

---

## 🧑‍💻 Contributing

Contributions are welcome and appreciated. If you have ideas for improvements, new features, or spot something that could be better, feel free to open an issue or a pull request.

Storix aims to be robust, secure, and easy to use. We value clear code, good documentation, and thoughtful discussion. Whether you want to add a new provider, enhance the CLI, share real-world examples, or review security, your input is valued.

To get started:

- Star and fork the repository
- Open an issue to discuss your idea or report a bug
- Submit a pull request with your proposed changes

For more details, see the documentation or join the discussion on GitHub.

---

## 📣 Spread the Word

If you like `storix` ⭐ star the repo, share it, and help us grow the community!

---

## 📚 Documentation

- [Sandbox Implementation Details](docs/SANDBOX_IMPLEMENTATION.md)
- [Async Migration Guide](docs/ASYNC_MIGRATION.md)
- [Release Notes](release-notes.md)

---

## 🧪 Testing

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=storix

# Run specific test categories
uv run pytest -m "not slow"  # Skip slow tests
uv run pytest -m integration # Run only integration tests
```

## 🗺️ Roadmap

Planned and upcoming features:

- **`mv` support for directories in Azure sync/async providers**
- **`du` (Disk Usage):**
  - Calculate and display the size of files and directories, similar to the Unix `du` command.
- **`stat` (File Metadata):**
  - Retrieve and display detailed file metadata (size, permissions, timestamps, etc.),
    similar to the Unix `stat` command.
  - Normalize the result using a shared model between the sync/async interfaces.
- `touch`, `mkdir`, `rm`, `rmdir` should take **`*paths`** instead of a single path arg
- **Storage Tree Structure (`tree`):**
  - Not just for visualization—enables programmatic operations such as copying, iterating, or transforming entire directory trees easily.
  - Will likely use a tree data structure (e.g., [anytree](https://anytree.readthedocs.io/), TBD) to represent and manipulate storage hierarchies efficiently.
  - Should be streaming for performance (leverage generators)
- **Advanced CLI Features:**
  - Enhanced command-line tools for scripting and automation.
- **Performance Improvements:**
  - Further optimize for speed and scalability.
- **Additional Cloud Providers:**
  - Add support for more cloud storage backends (e.g., S3, GCS). Local filesystem support is already included.
- **Auto Completions in the storix REPL (Interactive Shell)**
- **Improve validation strategy**
  - Reduce code duplication in validation logic between sync/async providers
  - Evaluate shared utility functions, mixins, or decorator patterns
  - Focus on common operations like `rm`, `rmdir`, `touch` validation
  - Ensure consistent error messages and behavior across providers
- **Storage Connection Pool**
  - Implement connection pooling for cloud storage providers to improve performance
  - Reuse connections across requests to reduce latency and overhead
  - Configurable pool sizes and connection timeouts

---

## 📝 License

Storix is licensed under the Apache 2.0 License
