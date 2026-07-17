"""Amazon S3 backend.

A typed facade: explicit, documented parameters over the internal
opendal engine, which supplies every port method. Flavor-neutral, so
the sync twin is generated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING


try:
    from .opendal import OpendalBackend
except ImportError:  # pragma: no cover
    _msg = "s3 extra not installed. Install it by running `uv add 'storix[s3]'`."
    raise ImportError(_msg) from None


if TYPE_CHECKING:
    from pathlib import PurePosixPath


class S3Backend(OpendalBackend):
    """Amazon S3, and S3-compatible stores (MinIO, R2, ...) via ``endpoint``.

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
        region: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        endpoint: str | None = None,
        root: str = '/',
    ) -> None:
        """Create an S3 backend.

        Args:
            bucket: Bucket anchoring port path ``/``.
            region: Bucket region; when omitted, resolved from the
                standard AWS environment/config chain.
            access_key_id: Static access key. When omitted, credentials
                resolve from the standard AWS chain (environment,
                profile, IAM role).
            secret_access_key: Secret for ``access_key_id``.
            endpoint: Custom endpoint URL for S3-compatible stores
                (e.g. ``http://localhost:9000`` for MinIO).
            root: Key prefix anchoring the session's ``/`` inside the
                bucket, like ``LocalBackend``'s base directory.

        Raises:
            ConfigurationError: If the configuration is rejected.
        """
        options = {
            'region': region,
            'access_key_id': access_key_id,
            'secret_access_key': secret_access_key,
            'endpoint': endpoint,
            'root': root,
        }
        super().__init__(
            's3',
            bucket=bucket,
            **{key: value for key, value in options.items() if value is not None},
        )

    def locate(self, path: PurePosixPath) -> str:
        """``s3://`` URI (the standard S3 locator), root prefix included."""
        prefix = self._options.get('root', '/').rstrip('/')
        return f's3://{self._options["bucket"]}{prefix}{path}'
