"""Verify the GCS extra exposes its public backend."""

from storix.backends import GcsBackend


assert GcsBackend.__name__ == 'GcsBackend'
