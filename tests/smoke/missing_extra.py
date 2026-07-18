"""Verify a default install explains how to enable an optional backend."""

try:
    from storix.backends import S3Backend
except ImportError as error:
    assert 'storix[s3]' in str(error)
else:
    message = (
        f'the default distribution unexpectedly installed the s3 extra: '
        f'{S3Backend.__name__}'
    )
    raise AssertionError(message)
