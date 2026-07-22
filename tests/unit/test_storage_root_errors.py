"""Missing storage-root detection at the backend error boundaries (ADR 0029).

Loose flavor-parametrized tests over the hand-written twin pairs (the
opendal engine and the native azure adapter), so the sync and async
flavors cannot drift apart on this contract. The raw messages are exact
captures from live providers (R2 for s3, Azure Storage for azblob); the
tests pin the isolated string matching to those captures and prove the
safe fallback for everything else.
"""

from pathlib import PurePosixPath

import pytest

from storix.errors import (
    ConfigurationError,
    PathNotFoundError,
    StorageRootNotFoundError,
)


S3_MISSING_BUCKET = (
    'ConfigInvalid (permanent) at list => S3Error { code: "NoSuchBucket", '
    'message: "The specified bucket does not exist.", resource: "", '
    'request_id: "" }'
)
"""Captured live from Cloudflare R2 (opendal 0.47, 2026-07)."""

AZBLOB_MISSING_CONTAINER = (
    'NotFound (permanent) at list => AzblobError { code: "ContainerNotFound", '
    'message: "The specified container does not exist. RequestId:d9d620f7" }'
)
"""Captured live from Azure Blob Storage (opendal 0.47, 2026-07)."""


@pytest.fixture(params=['_async', '_sync'])
def opendal_backend(request):
    """The OpendalBackend class of one flavor (skips without the extra)."""
    mod = pytest.importorskip(f'storix.{request.param}.backends.opendal')
    return mod.OpendalBackend


@pytest.fixture(params=['_async', '_sync'])
def azure_backend(request):
    """The AzureBackend class of one flavor (skips without the extra)."""
    mod = pytest.importorskip(f'storix.{request.param}.backends.azure')
    return mod.AzureBackend


def _s3(opendal_backend):
    return opendal_backend(
        's3',
        bucket='media',
        region='us-east-1',
        access_key_id='key',
        secret_access_key='secret',  # noqa: S106
    )


def _azblob(opendal_backend):
    return opendal_backend(
        'azblob',
        container='media',
        account_name='acct',
        account_key='a2V5',
        endpoint='https://acct.blob.core.windows.net',
    )


def test_s3_missing_bucket_is_a_storage_root_error(opendal_backend):
    from opendal import exceptions as ope

    err = _s3(opendal_backend)._error(
        ope.ConfigInvalid(S3_MISSING_BUCKET), PurePosixPath('/')
    )

    assert isinstance(err, StorageRootNotFoundError)
    assert err.root == 'media'
    assert err.root_kind == 's3 bucket'
    assert str(err) == "configured s3 bucket 'media' does not exist"


def test_azblob_missing_container_is_a_storage_root_error(opendal_backend):
    from opendal import exceptions as ope

    err = _azblob(opendal_backend)._error(
        ope.NotFound(AZBLOB_MISSING_CONTAINER), PurePosixPath('/')
    )

    assert isinstance(err, StorageRootNotFoundError)
    assert err.root == 'media'
    assert str(err) == "configured azblob container 'media' does not exist"


def test_plain_not_found_keeps_the_generic_translation(opendal_backend):
    from opendal import exceptions as ope

    err = _azblob(opendal_backend)._error(
        ope.NotFound('NotFound (permanent) at stat'), PurePosixPath('/x.txt')
    )

    assert isinstance(err, PathNotFoundError)
    assert not isinstance(err, StorageRootNotFoundError)


def test_path_echoing_the_code_word_does_not_match(opendal_backend):
    """The raw message embeds the request URI, so a path that merely
    contains the code word must not read as a missing root; only the
    quoted ``code: "..."`` token matches.
    """
    from opendal import exceptions as ope

    err = _azblob(opendal_backend)._error(
        ope.NotFound('NotFound (permanent) at stat, path: /ContainerNotFound.txt'),
        PurePosixPath('/ContainerNotFound.txt'),
    )

    assert not isinstance(err, StorageRootNotFoundError)


def test_config_invalid_without_the_code_stays_a_configuration_error(
    opendal_backend,
):
    from opendal import exceptions as ope

    err = _s3(opendal_backend)._error(
        ope.ConfigInvalid('ConfigInvalid (permanent) => region is missing'),
        PurePosixPath('/'),
    )

    assert isinstance(err, ConfigurationError)
    assert not isinstance(err, StorageRootNotFoundError)


def test_service_without_a_marker_keeps_the_generic_translation(opendal_backend):
    from opendal import exceptions as ope

    err = opendal_backend('memory')._error(
        ope.NotFound('NotFound (permanent) at stat'), PurePosixPath('/x')
    )

    assert isinstance(err, PathNotFoundError)


def test_adls_missing_filesystem_is_a_storage_root_error(azure_backend):
    from azure.core.exceptions import ResourceNotFoundError

    be = azure_backend('media', account_name='acct', credential='sig')
    exc = ResourceNotFoundError('nope')
    exc.error_code = 'FilesystemNotFound'

    err = be._error(exc, PurePosixPath('/'))

    assert isinstance(err, StorageRootNotFoundError)
    assert err.root == 'media'
    assert str(err) == "configured azure filesystem 'media' does not exist"


def test_adls_path_not_found_keeps_the_generic_translation(azure_backend):
    from azure.core.exceptions import ResourceNotFoundError

    be = azure_backend('media', account_name='acct', credential='sig')
    exc = ResourceNotFoundError('nope')
    exc.error_code = 'PathNotFound'

    err = be._error(exc, PurePosixPath('/x.txt'))

    assert isinstance(err, PathNotFoundError)
    assert not isinstance(err, StorageRootNotFoundError)
