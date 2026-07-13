# Installation

Storix requires Python 3.12 or newer.

## Install

=== "uv"

    ```bash
    uv add storix            # local filesystem + in-memory
    uv add "storix[azure]"   # + Azure Data Lake Gen2 (HNS accounts)
    uv add "storix[cli]"     # + the sx command-line interface
    uv add "storix[all]"     # all optional features
    ```

=== "pip"

    ```bash
    pip install storix
    pip install "storix[azure]"
    pip install "storix[cli]"
    pip install "storix[all]"
    ```

The base install gives you the `LocalBackend` (real disk) and the
`MemoryBackend` (an in-process store, ideal for tests). Cloud backends are
optional extras so you only pull in a provider SDK when you need it.

| Extra | Adds |
| --- | --- |
| (none) | `LocalBackend`, `MemoryBackend` |
| `azure` | `AzureBackend` (Azure Data Lake Gen2, hierarchical namespace accounts) |
| `cli` | the `sx` command-line interface and interactive shell |
| `all` | every backend and tool above |

## Verify

```python
from storix import Storix
from storix.backends import MemoryBackend

fs = Storix(MemoryBackend())
fs.echo("it works", "/hello.txt")
print(fs.ls())                # [StorixPath('hello.txt')]
print(fs.cat("/hello.txt"))   # b'it works'
```

If that prints `b'it works'`, you are ready. The `MemoryBackend` needs no
configuration and touches nothing on disk, which makes it the quickest way to
try things out.

## The CLI

The CLI dependencies are optional. Install `storix[cli]` (or `storix[all]`)
before using `sx`, a small shell over the same core:

=== "uv"

    ```bash
    uv add "storix[cli]"
    ```

=== "pip"

    ```bash
    pip install "storix[cli]"
    ```

```bash
sx                 # start the interactive shell (defaults to ~/.storix)
sx ls /            # or run a single command
sx -p azure ls /   # point it at a configured provider
```

If you run the launcher without the extra, it exits with the install command
instead of an optional-dependency traceback.

Next: the [Quickstart](quickstart.md).
