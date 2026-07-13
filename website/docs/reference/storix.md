# Storix session

Everything you call on a session. A `Storix` is created over a backend (or built
by `get_storage`), and every path argument is resolved the unix way (`~`, `..`,
and the current working directory) before it reaches the backend. Any operation
raises a typed [error](errors.md) on failure; nothing returns a boolean you have
to check.

Unless noted, every method has an awaitable twin under `storix.aio` with the same
name and signature.

## Session and navigation

### `pwd`

```python
pwd() -> StorixPath
```

The current working directory.

### `cd`

```python
cd(path: StrPathLike | None = None) -> Self
```

Change the working directory. No argument returns to `home`. Returns the session
for chaining.

### `ls`

```python
ls(path: StrPathLike | None = None, *, all: bool = False, abs: bool = False) -> list[StorixPath]
```

List a directory (the cwd by default). Dotfiles are hidden unless `all=True`.
`abs=True` returns absolute paths instead of names.

### `resolve`

```python
resolve(path: StrPathLike | None = None) -> StorixPath
```

Resolve a path to its absolute, normalized port path (applying cwd, `~`, `..`),
without touching the backend. Useful for logging and bookmarking.

### `locate`

```python
locate(path: StrPathLike | None = None) -> str
```

The physical URI of a path (`file://...`, `abfss://...`), resolved through any
sandbox. Use it for audit and cross-system references.

### Properties

```python
backend -> StorageBackend   # the raw port, for backend-specific calls
root    -> StorixPath       # always '/'
home    -> StorixPath       # the '~' anchor
```

## Reading

### `cat`

```python
cat(path: StrPathLike, /, *paths: StrPathLike) -> bytes
```

Read one or more files fully and concatenate them into `bytes`. Use for small,
known-size content. For large files, prefer `stream`.

### `stream`

```python
stream(
    path: StrPathLike,
    /,
    *paths: StrPathLike,
    chunk_size: int | None = None,
) -> Iterator[bytes]
```

Read files back in chunks. `chunk_size` is the maximum yielded size; `None` uses
the backend's preferred default. Smaller provider chunks pass through promptly.
Zero or negative values raise `ValueError`. Streaming-native backends keep memory
bounded; a whole-object custom backend's compatibility fallback does not. See
[Reading and writing](../guide/reading-and-writing.md).

### `stat`

```python
stat(path: StrPathLike | None = None) -> FileProperties
```

Facts about a path: kind, size, and (where the backend supports it) content type
and custom metadata.

### `du`

```python
du(path: StrPathLike | None = None) -> int
```

Total size in bytes of a tree (apparent content bytes).

### `exists`, `isfile`, `isdir`

```python
exists(path: StrPathLike | None = None) -> bool
isfile(path: StrPathLike | None = None) -> bool
isdir(path: StrPathLike | None = None) -> bool
```

Existence and kind checks.

## Writing and creating

### `echo`

```python
echo(
    data: DataBuffer[str] | DataBuffer[bytes],
    path: StrPathLike,
    /,
    *,
    chunk_size: int | None = None,
    mode: EchoMode = "w",
    content_type: str | None = None,
    metadata: Mapping[str, str] | None = None,
) -> None
```

Write `data` to `path`. `data` accepts native Python: `bytes`, `str`, a `Buffer`,
an open file (`IO`), or an iterable of chunks (and an async iterable under
`storix.aio`). `mode="a"` appends. `content_type` and `metadata` are applied where
the backend supports them. `chunk_size` is the maximum target backend write
batch; `None` uses its preferred default. Tiny iterator yields are combined and
oversized values are split. Zero or negative values raise `ValueError`.

### `touch`

```python
touch(path: StrPathLike, /, *paths: StrPathLike) -> None
```

Create empty files, or refresh their modification time if they exist.

### `mkdir`

```python
mkdir(path: StrPathLike, /, *paths: StrPathLike, parents: bool = False) -> None
```

Create directories. `parents=True` creates missing parents and does not error if
the directory already exists (unix `mkdir -p`).

### `set_metadata`

```python
set_metadata(path: StrPathLike, metadata: Mapping[str, str], /, *, merge: bool = False) -> None
```

Replace a file's custom metadata (`{}` clears it). `merge=True` does a
non-atomic read-modify-write to add keys instead of replacing. Requires the
`custom_metadata` capability.

## Moving, copying, removing

Move and copy are variadic; the last argument is the destination, like unix.

### `mv`

```python
mv(source: StrPathLike, /, *paths: StrPathLike) -> None
```

Move or rename. With more than two paths, all sources move into the final
directory.

### `cp`

```python
cp(source: StrPathLike, /, *paths: StrPathLike, recursive: bool = False) -> None
```

Copy. `recursive=True` to copy directories.

### `rm`

```python
rm(path: StrPathLike, /, *paths: StrPathLike, recursive: bool = False) -> None
```

Remove files. `recursive=True` removes directories and their contents (unix
`rm -r`).

### `rmdir`

```python
rmdir(path: StrPathLike, /, *paths: StrPathLike) -> None
```

Remove strictly empty directories.

## URLs and sharing

### `url`

```python
url(path: StrPathLike | None = None, *, expires_in: int | None = None) -> str
```

A presigned URL (an Azure SAS link). Requires the `presigned_urls` capability;
raises [`UnsupportedOperationError`](errors.md) otherwise. Use `DataUrlLayer` to
get one on any backend.

### `data_url`

```python
data_url(path: StrPathLike | None = None) -> str
```

A base64 `data:` URL, generated by the core for any backend.

## Composition

### `with_layer`, `with_layer_missing`

```python
with_layer(layer, /, *args, **kwargs) -> Self
with_layer_missing(layer, /, *args, **kwargs) -> Self
```

Return a new session with `layer` wrapping this backend. `with_layer_missing`
skips the layer when the backend already provides its capability. See
[Layers](../guide/layers.md).

### `without_layer`, `uncached`

```python
without_layer(*layers: type) -> Self
uncached -> Self          # property; sugar for without_layer(CacheLayer)
```

Return a session with the given layer types bypassed. Absent layers are a no-op;
a `SandboxLayer` cannot be stripped.

### `chroot`, `scratch`

```python
chroot(path: StrPathLike, /) -> Self
scratch(*, root: StrPathLike | None = None, prefix: str = "scratch-") -> ContextManager[Storix]
```

`chroot` returns a sandboxed session rooted at `path`. `scratch` is a context
manager giving a disposable (or pinned, with `root`) workspace on the same
backend.

## Lifecycle

```python
close() -> None
```

Release the backend's resources (idempotent). In async code, use the session as
a context manager: `async with get_storage("azure") as fs: ...`.
