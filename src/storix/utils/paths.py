import os

from collections.abc import Generator

from storix.types import StorixPath, StrPathLike


def to_sx_path(path: StrPathLike, /, *paths: StrPathLike) -> Generator[StorixPath]:
    """Stream any path as a pure path."""
    yield from map(StorixPath, (path, *paths))


def is_file_approx(p: StrPathLike) -> bool:
    """Guess whether a path names a file, judging only by its shape.

    Args:
        p: The path as written. The trailing-separator test below reads the
            argument before it becomes a ``StorixPath``, because that
            conversion normalizes the separator away: converting first left
            the check unreachable, and reported ``a.txt/`` as a file.
    """
    # trailing separator means "this is a directory" (POSIX and Windows)
    if os.fspath(p).endswith(('/', '\\')):
        return False

    # if it has a suffix (e.g. ".txt", ".json"), we assume it's a file.
    return bool(StorixPath(p).suffix)


def is_dir_approx(p: StrPathLike) -> bool:
    """Guess whether a path names a directory, judging only by its shape."""
    return is_file_approx(p) is False
