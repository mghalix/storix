"""Verify the S3 extra exposes its public backend."""

from storix.backends import S3Backend


assert S3Backend.__name__ == 'S3Backend'
