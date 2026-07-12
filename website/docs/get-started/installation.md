# Installation

Storix requires Python 3.12 or newer.

## Install

=== "uv"

    ```bash
    uv add storix            # local filesystem + in-memory
    uv add "storix[azure]"   # + Azure Data Lake Gen2 (HNS accounts)
    ```

=== "pip"

    ```bash
    pip install storix
    pip install "storix[azure]"
    ```

The base install gives you the `LocalBackend` (real disk) and the
`MemoryBackend` (an in-process store, ideal for tests). Cloud backends are
optional extras so you only pull in a provider SDK when you need it.

| Extra | Adds |
| --- | --- |
| (none) | `LocalBackend`, `MemoryBackend` |
| `azure` | `AzureBackend` (Azure Data Lake Gen2, hierarchical namespace accounts) |

## Verify

```python
import storix

fs = storix.Storix(storix.backends.MemoryBackend())
fs.echo(b"it works", "/hello.txt")
print(fs.cat("/hello.txt"))   # b'it works'
```

If that prints `b'it works'`, you are ready. The `MemoryBackend` needs no
configuration and touches nothing on disk, which makes it the quickest way to
try things out.

## The CLI

Installing storix also gives you `sx`, a small shell over the same core:

```bash
sx                 # start the interactive shell (defaults to ~/.storix)
sx ls /            # or run a single command
sx -p azure ls /   # point it at a configured provider
```

Next: the [Quickstart](quickstart.md).
