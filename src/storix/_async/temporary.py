"""Disposable filesystems for tests and scratch work."""

from __future__ import annotations

import shutil
import tempfile
import uuid

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from storix import pathops
from storix.types import StorixPath

from .backends.local import LocalBackend
from .core import Storix
from .layers import SandboxLayer


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from storix.types import StrPathLike

    from .backends import StorageBackend


_ROOT = StorixPath('/')


@asynccontextmanager
async def temporary() -> AsyncGenerator[Storix]:
    """Yield a Storix session over a fresh temporary directory.

    The directory and everything in it are deleted on exit.
    """
    base = tempfile.mkdtemp(prefix='storix-')
    fs = Storix(LocalBackend(base))
    try:
        yield fs
    finally:
        await fs.close()
        shutil.rmtree(base, ignore_errors=True)


@asynccontextmanager
async def scratch(
    backend: StorageBackend,
    *,
    root: StrPathLike | None = None,
    prefix: str = 'scratch-',
) -> AsyncGenerator[Storix]:
    """Yield an ephemeral or pinned sandboxed workspace on *any* backend.

    Pure composition: a subtree, sandboxed so the session sees it as
    ``/``. With no ``root`` the subtree is uniquely named and deleted on
    exit; passing ``root`` pins the workspace - created if missing,
    reused across sessions, and *persisted* on exit (remove it yourself
    with ``rm(recursive=True)`` when done). The backend is borrowed, not
    owned - its lifecycle (``close``) stays with the caller.
    """
    pinned = root is not None
    workspace = (
        pathops.resolve(root, cwd=_ROOT, home=_ROOT)
        if root is not None
        else StorixPath(f'/{prefix}{uuid.uuid4().hex[:12]}')
    )
    await backend.make_dir(workspace, parents=True)
    try:
        yield Storix(SandboxLayer(backend, root=workspace))
    finally:
        if not pinned:
            await backend.delete_tree(workspace)
