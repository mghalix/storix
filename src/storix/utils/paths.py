from collections.abc import Generator

from storix.types import StorixPath, StrPathLike


def to_sx_path(*paths: StrPathLike) -> Generator[StorixPath]:
    """Stream any path as a pure path."""
    yield from map(StorixPath, paths)
