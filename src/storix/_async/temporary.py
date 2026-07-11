"""Disposable filesystems for tests and scratch work."""

from __future__ import annotations

import shutil
import tempfile
import uuid

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from storix.types import StorixPath

from .backends.local import LocalBackend
from .core import Storix
from .layers import SandboxLayer


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from .backends import StorageBackend


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
    backend: StorageBackend, *, prefix: str = 'scratch-'
) -> AsyncGenerator[Storix]:
    """Yield an ephemeral workspace on *any* backend.

    Pure composition: a uniquely-named subtree, sandboxed so the session
    sees it as ``/``, deleted on exit. The backend is borrowed, not
    owned - its lifecycle (``close``) stays with the caller.
    """
    root = StorixPath(f'/{prefix}{uuid.uuid4().hex[:12]}')
    await backend.make_dir(root, parents=True)
    try:
        yield Storix(SandboxLayer(backend, root=root))
    finally:
        await backend.delete_tree(root)
