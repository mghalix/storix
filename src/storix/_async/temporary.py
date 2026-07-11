"""Disposable local filesystems for tests and scratch work."""

from __future__ import annotations

import shutil
import tempfile

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from .backends.local import LocalBackend
from .core import Storix


if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@asynccontextmanager
async def temporary() -> AsyncIterator[Storix]:
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
