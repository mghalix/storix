"""Pure, lexical path resolution shared by both flavor trees and the core.

Lexical means the filesystem is never consulted: unlike
``pathlib.Path.resolve``, nothing here follows symlinks or checks
existence. Storage paths (cloud especially) have no symlinks, so ``..``
resolves from the path text alone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from storix.types import StorixPath


if TYPE_CHECKING:
    from pathlib import PurePosixPath

    from storix.types import StrPathLike


def expand_home(path: StrPathLike, *, home: PurePosixPath) -> StorixPath:
    """Anchor ``~`` or ``~/...`` at ``home``; ``~`` anywhere else is literal.

    ``~user`` expansion is deliberately unsupported (no user database in a
    virtual filesystem) and passes through as an ordinary name.
    """
    p = StorixPath(path)
    if p.parts and p.parts[0] == '~':
        return StorixPath(home, *p.parts[1:])
    return p


def make_absolute(path: StrPathLike, *, cwd: PurePosixPath) -> StorixPath:
    """Join relative paths onto ``cwd``; absolute paths pass through."""
    p = StorixPath(path)
    if p.is_absolute():
        return p
    return StorixPath(cwd, *p.parts)


def normalize(path: StrPathLike) -> StorixPath:
    """Resolve ``..`` segments lexically over an absolute path.

    ``..`` at the root is absorbed (``/..`` == ``/``), matching POSIX and
    every shell. ``.`` segments never reach us - pathlib drops them at
    construction.
    """
    p = StorixPath(path)
    if not p.is_absolute():
        msg = f'normalize() expects an absolute path, got {str(p)!r}'
        raise ValueError(msg)

    stack: list[str] = []
    for part in p.parts[1:]:  # parts[0] is the '/' anchor
        if part == '..':
            if stack:
                stack.pop()
            # -> else: '..' above root is absorbed
        else:
            stack.append(part)
    return StorixPath('/', *stack)


def resolve(
    path: StrPathLike, *, cwd: PurePosixPath, home: PurePosixPath
) -> StorixPath:
    """The full pipeline for user-supplied paths: home -> absolute -> normal.

    Idempotent: resolving an already-resolved path is a no-op.
    """
    return normalize(make_absolute(expand_home(path, home=home), cwd=cwd))


def is_hidden(path: StrPathLike) -> bool:
    """Whether the path's own basename is dot-prefixed.

    Only the entry's own name counts - a visible file under a hidden
    directory is not itself hidden.
    """
    return StorixPath(path).name.startswith('.')
