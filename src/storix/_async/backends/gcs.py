"""Google Cloud Storage backend.

A typed facade: explicit, documented parameters over the internal
opendal engine, which supplies every port method. Flavor-neutral, so
the sync twin is generated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from storix.constants import DEFAULT_READ_CHUNK_SIZE, DEFAULT_WRITE_CHUNK_SIZE


try:
    from .opendal import OpendalBackend
except ImportError:  # pragma: no cover
    _msg = "gcs extra not installed. Install it by running `uv add 'storix[gcs]'`."
    raise ImportError(_msg) from None


if TYPE_CHECKING:
    from pathlib import PurePosixPath


class GcsBackend(OpendalBackend):
    """Google Cloud Storage, anchored at one bucket.

    The bucket anchors the session: port path ``/x`` maps to object key
    ``x`` (under ``root`` when one is set). Advertises the
    ``presigned_urls``, ``custom_metadata``, and ``content_type``
    capabilities. Construction is configuration-only; credentials are
    validated on first I/O.
    """

    def __init__(
        self,
        bucket: str,
        *,
        credential: str | None = None,
        credential_path: str | None = None,
        endpoint: str | None = None,
        root: str = '/',
        read_chunk_size: int = DEFAULT_READ_CHUNK_SIZE,
        write_chunk_size: int = DEFAULT_WRITE_CHUNK_SIZE,
        read_prefetch_size: int | None = None,
    ) -> None:
        """Create a GCS backend.

        Args:
            bucket: Bucket anchoring port path ``/``.
            credential: Service-account JSON as a string. When both
                credential arguments are omitted, credentials resolve
                from the standard Google chain (application default
                credentials, metadata server).
            credential_path: Path to a service-account JSON file.
            endpoint: Custom endpoint URL for GCS-compatible stores and
                emulators.
            root: Key prefix anchoring the session's ``/`` inside the
                bucket, like ``LocalBackend``'s base directory.

            read_chunk_size: Maximum chunk a read yields, and the size
                opendal is asked to fetch per request.
            write_chunk_size: Batch size accumulated before each write
                request.
            read_prefetch_size: Size of a stream's opening read; ``None``
                means the read chunk size. See the Tune transfers recipe.

        Raises:
            ConfigurationError: If the configuration is rejected.
        """
        options = {
            'credential': credential,
            'credential_path': credential_path,
            'endpoint': endpoint,
            'root': root,
        }
        super().__init__(
            'gcs',
            read_chunk_size=read_chunk_size,
            write_chunk_size=write_chunk_size,
            read_prefetch_size=read_prefetch_size,
            bucket=bucket,
            **{key: value for key, value in options.items() if value is not None},
        )

    def locate(self, path: PurePosixPath) -> str:
        """``gs://`` URI (the standard GCS locator), root prefix included."""
        prefix = self._options.get('root', '/').rstrip('/')
        return f'gs://{self._options["bucket"]}{prefix}{path}'
