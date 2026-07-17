"""Azure Blob Storage backend (flat namespace).

A typed facade: explicit, documented parameters over the internal
opendal engine, which supplies every port method. Flavor-neutral, so
the sync twin is generated.

The companion to ``AzureBackend``: that one speaks the Data Lake Gen2
endpoint and requires hierarchical namespaces; this one speaks the
plain blob endpoint and works on every storage account, flat
(portal-default) accounts included.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .opendal import OpendalBackend


if TYPE_CHECKING:
    from pathlib import PurePosixPath


class AzureBlobBackend(OpendalBackend):
    """Azure Blob Storage, anchored at one container.

    The container anchors the session: port path ``/x`` maps to blob
    name ``x`` (under ``root`` when one is set). Works on any storage
    account; for accounts with hierarchical namespaces enabled,
    ``AzureBackend`` offers richer semantics (atomic renames, true
    appends) over the Data Lake endpoint.

    Advertises the ``custom_metadata`` and ``content_type``
    capabilities always, and ``presigned_urls`` when the credential is
    a SAS token (a bare account key cannot mint one here).
    Construction is configuration-only; credentials are validated on
    first I/O.
    """

    def __init__(
        self,
        container: str,
        *,
        account_name: str,
        credential: str | None = None,
        endpoint: str | None = None,
        root: str = '/',
    ) -> None:
        """Create an Azure Blob Storage backend.

        Args:
            container: Container anchoring port path ``/``.
            account_name: Azure Storage account name.
            credential: SAS token or account key, distinguished by the
                ``sig=`` marker every SAS token carries (base64 account
                keys cannot contain it). ``None`` means anonymous
                access, for public containers.
            endpoint: Custom blob endpoint URL (emulators, sovereign
                clouds); defaults to the account's public
                ``blob.core.windows.net`` endpoint.
            root: Blob-name prefix anchoring the session's ``/`` inside
                the container, like ``LocalBackend``'s base directory.

        Raises:
            ConfigurationError: If the configuration is rejected.
        """
        options = {
            'endpoint': endpoint or f'https://{account_name}.blob.core.windows.net',
            'root': root,
        }
        if credential is not None:
            kind = 'sas_token' if 'sig=' in credential else 'account_key'
            options[kind] = credential
        super().__init__(
            'azblob',
            container=container,
            account_name=account_name,
            **options,
        )

    def locate(self, path: PurePosixPath) -> str:
        """``wasbs://`` URI (the standard blob locator), root included."""
        container = self._options['container']
        account = self._options['account_name']
        prefix = self._options.get('root', '/').rstrip('/')
        return f'wasbs://{container}@{account}.blob.core.windows.net{prefix}{path}'
