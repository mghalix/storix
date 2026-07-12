from typing import Final


DEFAULT_WRITE_CHUNKSIZE: Final[int] = 100 * 1024 * 1024
"""(100MB)"""
DEFAULT_CONCURRENCY: Final[int] = 32
"""Bounded fan-out for concurrent backend operations (per gather call)."""
DEFAULT_URL_EXPIRY_SECONDS: Final[int] = 3600
"""Lifetime of presigned URLs minted by url()."""
DEFAULT_CACHE_NAMESPACE: Final[str] = 'storix'
"""Root namespace for CacheLayer keys: ``<namespace>[:<env>]:<op>:<locator>``."""
DEFAULT_MIMETYPE_DETECTION_PEEKSIZE: Final[int] = 8 * 1024
"""(8KB)"""
