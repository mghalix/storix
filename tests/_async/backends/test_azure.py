"""Azure-backend specifics that need no credentials.

Behavioral coverage lives in the conformance suite (test_backends.py),
where the azure param is integration-marked and runs against a real
HNS-enabled account.
"""

from pathlib import PurePosixPath as P

from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ResourceExistsError,
    ResourceNotFoundError,
)

from storix._async.backends.azure import _HNS_HINT, AzureBackend, _translate
from storix.errors import (
    AlreadyExistsError,
    DirectoryNotEmptyError,
    PathNotFoundError,
    PermissionDeniedError,
    StorageError,
)


PATH = P('/docs/a.txt')


def test_key_strips_the_port_anchor():
    assert AzureBackend._key(P('/docs/a.txt')) == 'docs/a.txt'
    assert AzureBackend._key(P('/')) == ''


def test_translate_not_found():
    err = _translate(ResourceNotFoundError(message='gone'), PATH)
    assert isinstance(err, PathNotFoundError)
    assert str(err.path) == str(PATH)


def test_translate_exists():
    err = _translate(ResourceExistsError(message='x'), PATH)
    assert isinstance(err, AlreadyExistsError)


def test_translate_auth():
    err = _translate(ClientAuthenticationError(message='denied'), PATH)
    assert isinstance(err, PermissionDeniedError)


def test_translate_error_code_beats_exception_type():
    exc = ResourceExistsError(message='conflict')
    exc.error_code = 'DirectoryNotEmpty'
    assert isinstance(_translate(exc, PATH), DirectoryNotEmptyError)


def test_translate_unknown_http_error_hints_at_hns():
    err = _translate(HttpResponseError(message='mystery failure'), PATH)
    assert isinstance(err, StorageError)
    assert _HNS_HINT in str(err)


def test_capabilities_advertise_content_type():
    assert AzureBackend.capabilities.content_type is True
