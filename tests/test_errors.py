# ruff: noqa: A004
import builtins
import errno

import pytest

from storix.errors import (
    AlreadyExistsError,
    IsADirectoryError,
    NotADirectoryError,
    PathNotFoundError,
    PermissionDeniedError,
    StorageError,
    UnsupportedOperationError,
)
from storix.types import StorixPath


PATH = '/data/report.csv'

PATH_ERRORS = [
    pytest.param(
        PathNotFoundError,
        FileNotFoundError,
        errno.ENOENT,
        f"path '{PATH}' does not exist",
        id='PathNotFoundError',
    ),
    pytest.param(
        AlreadyExistsError,
        FileExistsError,
        errno.EEXIST,
        f"path '{PATH}' already exists",
        id='AlreadyExistsError',
    ),
    pytest.param(
        NotADirectoryError,
        builtins.NotADirectoryError,
        errno.ENOTDIR,
        f"not a directory: '{PATH}'",
        id='NotADirectoryError',
    ),
    pytest.param(
        IsADirectoryError,
        builtins.IsADirectoryError,
        errno.EISDIR,
        f"is a directory: '{PATH}'",
        id='IsADirectoryError',
    ),
    pytest.param(
        PermissionDeniedError,
        builtins.PermissionError,
        errno.EACCES,
        f"permission denied: '{PATH}'",
        id='PermissionDeniedError',
    ),
]


@pytest.mark.parametrize(
    ('exc_cls', 'stdlib_parent', 'errno_code', 'message'), PATH_ERRORS
)
class TestPathErrors:
    """Contracts every single-path error must uphold."""

    def test_caught_as_storage_error(
        self,
        exc_cls: type[StorageError],
        stdlib_parent: type[Exception],
        errno_code: int,
        message: str,
    ):
        with pytest.raises(StorageError):
            raise exc_cls(PATH)

    def test_caught_by_stdlib_parent(
        self,
        exc_cls: type[StorageError],
        stdlib_parent: type[Exception],
        errno_code: int,
        message: str,
    ):
        with pytest.raises(stdlib_parent):
            raise exc_cls(PATH)

    def test_carries_path_facts(
        self,
        exc_cls: type[StorageError],
        stdlib_parent: type[Exception],
        errno_code: int,
        message: str,
    ):
        e = exc_cls(PATH)
        assert isinstance(e.path, StorixPath)
        assert str(e.path) == PATH
        assert e.filename == PATH

    def test_sets_errno(
        self,
        exc_cls: type[StorageError],
        stdlib_parent: type[Exception],
        errno_code: int,
        message: str,
    ):
        assert exc_cls(PATH).errno == errno_code

    def test_default_message_from_template(
        self,
        exc_cls: type[StorageError],
        stdlib_parent: type[Exception],
        errno_code: int,
        message: str,
    ):
        assert str(exc_cls(PATH)) == message

    def test_custom_message_overrides_template(
        self,
        exc_cls: type[StorageError],
        stdlib_parent: type[Exception],
        errno_code: int,
        message: str,
    ):
        assert str(exc_cls(PATH, 'boom')) == 'boom'


def test_str_is_not_hijacked_by_oserror_formatting():
    """OSError.__str__ switches to '[Errno n] strerror: filename' formatting
    once errno/filename are set; the storix message must win regardless.
    """
    e = PathNotFoundError(PATH)
    assert e.filename is not None
    assert '[Errno' not in str(e)


def test_facts_survive_oserror_init_reset():
    """OSError.__init__ clears the errno/strerror/filename slots when it runs,
    so facts must be assigned after the super().__init__ call.
    """
    e = PathNotFoundError(PATH)
    assert e.errno == errno.ENOENT
    assert e.filename == PATH


def test_unsupported_operation_caught_as_storage_error():
    operation = 'content_type'
    with pytest.raises(StorageError):
        raise UnsupportedOperationError(operation)


def test_unsupported_operation_is_not_an_oserror():
    """Nothing went wrong with a path - the backend simply cannot do what
    was asked - so this must not masquerade as an OS failure.
    """
    assert not isinstance(UnsupportedOperationError('x'), OSError)


def test_unsupported_operation_carries_operation():
    assert UnsupportedOperationError('content_type').operation == 'content_type'


def test_unsupported_operation_default_message_mentions_operation():
    assert 'content_type' in str(UnsupportedOperationError('content_type'))


def test_unsupported_operation_custom_message_overrides_default():
    assert str(UnsupportedOperationError('x', 'boom')) == 'boom'
