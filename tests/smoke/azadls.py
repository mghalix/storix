"""Verify the ADLS extra exposes its public backend."""

from storix.backends import AzureBackend


assert AzureBackend.__name__ == 'AzureBackend'
