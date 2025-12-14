from collections.abc import Generator

from storix.types import StorixPath, StrPathLike


def to_sx_path(path: StrPathLike, /, *paths: StrPathLike) -> Generator[StorixPath]:
    """Stream any path as a pure path."""
    yield from map(StorixPath, (path, *paths))


def is_file_approx(p: StrPathLike) -> bool:
    p = StorixPath(p)

    # trailing separator usually means "this is a directory"
    if str(p).endswith(('/', '\\')):  # handles POSIX & Windows style strings
        return False

    # if it has a suffix (e.g. ".txt", ".json"), we assume it's a file.
    return bool(p.suffix)


def is_dir_approx(p: StrPathLike) -> bool:
    return is_file_approx(p) is False
