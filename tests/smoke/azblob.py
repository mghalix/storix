"""Verify the Azure Blob extra exposes its public backend."""

from storix.backends import AzureBlobBackend


assert AzureBlobBackend.__name__ == 'AzureBlobBackend'
