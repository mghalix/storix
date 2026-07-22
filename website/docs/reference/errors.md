# Errors

Every failure raises a typed exception from `storix.errors`. They all inherit
`StorageError`, so you can catch storage failures wholesale, and the path-related
ones also inherit their stdlib counterpart, so idiomatic handlers keep working.

```python
from storix.errors import StorageError, PathNotFoundError

try:
    fs.cat("/missing.txt")
except PathNotFoundError as exc:
    print(exc.path)          # the offending path, as data
except StorageError:
    ...                      # any storix failure
```

## Hierarchy

```text
StorageError                         # base for everything storix raises
├── PathError                        # concerns a single path; carries `.path`
│   ├── PathNotFoundError            # also a FileNotFoundError
│   ├── AlreadyExistsError           # also a FileExistsError
│   ├── NotADirectoryError           # also a NotADirectoryError
│   ├── IsADirectoryError            # also an IsADirectoryError
│   ├── PermissionDeniedError        # also a PermissionError
│   └── DirectoryNotEmptyError       # also an OSError
├── UnsupportedOperationError        # backend lacks the requested capability
├── NonRemovableLayerError           # without_layer() asked to strip a boundary
└── ConfigurationError               # backend configuration is invalid
    └── StorageRootNotFoundError     # the configured bucket/container is absent
```

## Notes

- `PathError` subclasses carry the offending path as `.path` (a `StorixPath`)
  plus `.filename` and `.errno`, mirroring `OSError`. In a sandbox, the path is
  the virtual one, so errors never leak the real prefix.
- `UnsupportedOperationError` names the missing capability (for example passing
  `content_type=` to a local backend, or `url()` on a backend without
  `presigned_urls`).
- `NonRemovableLayerError` is raised by `without_layer` when a matched layer sets
  `removable = False`, notably `SandboxLayer`.
- `ConfigurationError` covers factory configuration and settings that a lazy
  provider can validate only on first I/O, such as malformed Azure credentials.
- `StorageRootNotFoundError` means the namespace the backend is anchored to -
  an S3/GCS bucket, Azure Blob container, or ADLS Gen2 filesystem - does not
  exist. It carries `.root` (the configured name) and `.root_kind` (a
  descriptive phrase like `'s3 bucket'`). Deliberately not a
  `FileNotFoundError`: no path inside the namespace is at fault, the
  namespace itself is absent, and creating it belongs to your provider's
  own tooling.
- `from_os_error(exc, path)` translates a raw `OSError` into this taxonomy; it is
  the boundary helper filesystem-backed backends use.
