# ruff: noqa: A001 - error classes intentionally shadow their stdlib namesakes
import builtins
import errno

from typing import ClassVar

from storix.types import StorixPath, StrPathLike


class StorageError(Exception):
    """Base class for all storix errors.

    Every exception storix raises inherits from this, so callers can catch
    storage failures wholesale with ``except StorageError``. Subclasses also
    inherit the matching stdlib exception where one exists, so idiomatic
    handlers like ``except FileNotFoundError`` keep working.
    """


class PathError(StorageError):
    """Base for errors concerning a single path.

    Carries the offending path as data instead of burying it in the message:
    ``path`` holds it as a :class:`~storix.types.StorixPath`, while
    ``filename`` and ``errno`` mirror the :class:`OSError` conventions. The
    default message is built from the class ``_template`` so error text has
    exactly one home per error kind.
    """

    _template: ClassVar[str] = "'{path}': operation failed"
    _errno: ClassVar[int | None] = None

    def __init__(self, path: StrPathLike, msg: str | None = None) -> None:
        super().__init__(msg or self._template.format(path=path))
        # facts must be set after super().__init__: OSError.__init__ resets
        # its errno/strerror/filename slots when it runs.
        self.path = StorixPath(path)
        self.filename = str(path)
        if self._errno is not None:
            self.errno = self._errno

    def __str__(self) -> str:
        # OSError.__str__ switches to '[Errno n] strerror: filename' formatting
        # whenever errno/filename are set, discarding the message; always show
        # the storix message instead.
        return str(self.args[0]) if self.args else super().__str__()


class PathNotFoundError(PathError, FileNotFoundError):
    """A path that was expected to exist does not.

    Also caught by ``except FileNotFoundError``.
    """

    _template = "path '{path}' does not exist"
    _errno = errno.ENOENT


class AlreadyExistsError(PathError, FileExistsError):
    """A path that was expected to be absent already exists.

    Also caught by ``except FileExistsError``.
    """

    _template = "path '{path}' already exists"
    _errno = errno.EEXIST


class NotADirectoryError(PathError, builtins.NotADirectoryError):
    """A directory operation was attempted on a path that is not a directory.

    Also caught by ``except NotADirectoryError`` (the builtin).
    """

    _template = "not a directory: '{path}'"
    _errno = errno.ENOTDIR


class IsADirectoryError(PathError, builtins.IsADirectoryError):
    """A file operation was attempted on a path that is a directory.

    Also caught by ``except IsADirectoryError`` (the builtin).
    """

    _template = "is a directory: '{path}'"
    _errno = errno.EISDIR


class PermissionDeniedError(PathError, builtins.PermissionError):
    """The backend denied access to a path.

    Also caught by ``except PermissionError``.
    """

    _template = "permission denied: '{path}'"
    _errno = errno.EACCES


class DirectoryNotEmptyError(PathError, OSError):
    """A directory that was expected to be empty has children.

    Raised by ``delete`` on a non-empty directory (``delete`` removes
    leaves only - files or empty directories). Also caught by
    ``except OSError``.
    """

    _template = "directory not empty: '{path}'"
    _errno = errno.ENOTEMPTY


class UnsupportedOperationError(StorageError):
    """The backend does not support the requested feature.

    Raised when an argument or operation requires a capability the backend
    does not advertise (see :class:`~storix.models.Capabilities`), e.g.
    passing ``content_type=`` to a local filesystem. Deliberately not an
    :class:`OSError`: nothing went wrong with the path — the backend simply
    cannot do what was asked.
    """

    def __init__(self, operation: str, msg: str | None = None) -> None:
        self.operation = operation
        super().__init__(
            msg or f"operation '{operation}' is not supported by this backend"
        )


_OS_ERROR_MAP: tuple[tuple[type[OSError], type[PathError]], ...] = (
    (FileNotFoundError, PathNotFoundError),
    (builtins.IsADirectoryError, IsADirectoryError),
    (builtins.NotADirectoryError, NotADirectoryError),
    (FileExistsError, AlreadyExistsError),
    (builtins.PermissionError, PermissionDeniedError),
)


def from_os_error(exc: OSError, path: StrPathLike) -> StorageError:
    """Translate a raw ``OSError`` into the storix taxonomy.

    The boundary tool for filesystem-backed backends: catch ``OSError``,
    raise ``from_os_error(exc, port_path) from exc``. ``path`` should be
    the *port* path (virtual), never the native OS path, so errors speak
    the caller's namespace.
    """
    for stdlib_cls, storix_cls in _OS_ERROR_MAP:
        if isinstance(exc, stdlib_cls):
            return storix_cls(path)
    if exc.errno == errno.ENOTEMPTY:
        return DirectoryNotEmptyError(path)
    return StorageError(f"'{path}': {exc.strerror or exc}")
