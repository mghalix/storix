from collections.abc import Generator

from storix.types import StorixPath, StrPathLike


def to_sx_path(path: StrPathLike, /, *paths: StrPathLike) -> Generator[StorixPath]:
    """Stream any path as a pure path."""
    yield from map(StorixPath, (path, *paths))


def is_file_approx(p: StrPathLike) -> bool:
    """Guess whether a path names a file, judging only by its shape.

    Args:
        p: The path as written. A trailing separator decides on its own and
            outranks the suffix, so ``a.txt/`` is a directory.
    """
    target = StorixPath(p)
    # trailing separator means "this is a directory"
    if target.named_as_directory:
        return False

    # if it has a suffix (e.g. ".txt", ".json"), we assume it's a file.
    return bool(target.suffix)


def is_dir_approx(p: StrPathLike) -> bool:
    """Guess whether a path names a directory, judging only by its shape."""
    return is_file_approx(p) is False
