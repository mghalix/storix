from typing import Final


DEFAULT_READ_CHUNK_SIZE: Final[int] = 1024 * 1024
"""1 MiB fallback read chunk size for backends without a native preference."""
DEFAULT_WRITE_CHUNK_SIZE: Final[int] = 1024 * 1024
"""1 MiB fallback write batch size for backends without a native preference."""
DEFAULT_SOURCE_READ_SIZE: Final[int] = 1024 * 1024
"""1 MiB pull size when normalizing readable Python objects for ``echo``."""
DEFAULT_AZURE_READ_CHUNK_SIZE: Final[int] = 4 * 1024 * 1024
"""4 MiB Azure read size, matching the SDK's native download chunks."""
DEFAULT_AZURE_WRITE_CHUNK_SIZE: Final[int] = 4 * 1024 * 1024
"""4 MiB Azure write batch size, avoiding small-request overhead."""
DEFAULT_AZURE_READ_PREFETCH_SIZE: Final[int] = 8 * 1024 * 1024
"""8 MiB Azure initial download request (the SDK's own default is 32 MiB).

This is the one buffer a download holds whole before any chunk is yielded,
so it is what a bulk pull multiplies by its fan-out. Measured over a 480 MiB
concurrent pull, 32 MiB peaked at 708 MB RSS and 8 MiB at 273 MB for the
same wall time; the cost is one extra range request per 8 MiB on a lone
stream (about 14 percent on a single large file over a high-latency link).
Raise it per session with ``AzureBackend(read_prefetch_size=...)`` when
single-file reads matter more than concurrent ones."""
DEFAULT_CONCURRENCY: Final[int] = 32
"""Bounded fan-out for concurrent backend operations (per gather call)."""
BULK_LISTING_KEY_LIMIT: Final[int] = 10_000
"""Descendant-key ceiling for the bulk-emptiness fast path (ADR 0027). A
recursive listing of a parent prefix that yields more keys than this is
abandoned and the core falls back to the concurrent per-child floor, so a
container with millions of keys under one prefix is never pulled whole."""
DEFAULT_URL_EXPIRY_SECONDS: Final[int] = 3600
"""Lifetime of presigned URLs minted by url()."""
DEFAULT_CACHE_NAMESPACE: Final[str] = 'storix'
"""Root namespace for CacheLayer keys: ``<namespace>[:<env>]:<op>:<locator>``."""
DEFAULT_MIMETYPE_DETECTION_PEEKSIZE: Final[int] = 8 * 1024
"""(8KB)"""
