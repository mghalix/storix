"""Bring-your-own backend, and how a plugin system collapses in 0.2.0.

In 0.1.x a "provider" WAS the whole ~30-method unix interface, so a
plugin adapter had to re-declare and forward every method (touch, echo,
cat, cd, ls, mv, cp, rm, rmdir, tree, stat, du, exists, isdir, ...) -
~200 lines of boilerplate per plugin, plus reaching into private
attributes (`fs._min_depth`, `fs._sandbox`) to answer "where does this
physically live".

In 0.2.0 the core owns the unix interface; a backend implements only the
small StorageBackend port. So a plugin shrinks to: build a backend from
config, register it. The forwarding disappears entirely, and the
physical-location question is answered by the public `locate()`.

Run:  uv run python samples/plugins/byo_backend.py
"""

import asyncio

from collections.abc import AsyncIterator, Mapping
from pathlib import PurePosixPath

from pydantic_settings import BaseSettings

# register_backend is per-flavor (async and sync keep separate registries,
# like the backends themselves) - use the flavor you build for
from storix.aio import Storix, get_storage, register_backend
from storix.aio.backends import BackendBase
from storix.enums import PathKind
from storix.errors import IsADirectoryError, PathNotFoundError
from storix.models import Entry, RawStat
from storix.types import EchoMode
from storix.utils.time import utcnow


# --- 1. A backend: implement the six primitives; the core does the rest ---
#     (subclass BackendBase to inherit read/move/copy/du/exists/... for free)


class DictBackend(BackendBase):
    """A trivially small backend over a flat dict - the whole port surface.

    Real backends (S3, GCS, SFTP, a database) look exactly like this:
    six methods translating port paths to native calls. Everything else -
    the unix commands, streaming, concurrency - is provided by Storix.
    """

    def __init__(self, *, label: str = 'dict') -> None:
        self._label = label
        self._files: dict[str, bytes] = {}
        self._dirs: set[str] = {'/'}

    def _exists(self, key: str) -> bool:
        return key in self._files or key in self._dirs

    async def read_stream(self, path: PurePosixPath) -> AsyncIterator[bytes]:
        key = str(path)
        if key in self._dirs:
            raise IsADirectoryError(path)
        if key not in self._files:
            raise PathNotFoundError(path)
        yield self._files[key]

    async def write(
        self,
        path: PurePosixPath,
        data: AsyncIterator[bytes],
        *,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        payload = b''.join([chunk async for chunk in data])
        key = str(path)
        if mode == 'a':
            payload = self._files.get(key, b'') + payload
        self._files[key] = payload

    async def delete(self, path: PurePosixPath) -> None:
        key = str(path)
        if key in self._files:
            del self._files[key]
        elif key in self._dirs:
            self._dirs.discard(key)
        else:
            raise PathNotFoundError(path)

    async def list_dir(self, path: PurePosixPath) -> AsyncIterator[Entry]:
        base = str(path).rstrip('/')
        for key in [*self._files, *self._dirs]:
            parent, _, name = key.rpartition('/')
            if (parent or '/') == (base or '/') and key != '/':
                yield Entry(name=name, is_dir=key in self._dirs)

    async def stat(self, path: PurePosixPath) -> RawStat:
        key = str(path)
        if not self._exists(key):
            raise PathNotFoundError(path)
        is_dir = key in self._dirs
        return RawStat(
            kind=PathKind.DIRECTORY if is_dir else PathKind.FILE,
            size=0 if is_dir else len(self._files[key]),
            created=utcnow(),
            modified=utcnow(),
        )

    async def make_dir(self, path: PurePosixPath, *, parents: bool) -> None:
        self._dirs.add(str(path))

    def locate(self, path: PurePosixPath) -> str:
        """Physical locator - answer 'where does this live' without hacks."""
        return f'dict://{self._label}{path}'


# --- 2. A plugin: config + a builder, registered under a name ---
#     This is the ENTIRE plugin. Compare the 0.1.x StoragePlugin's ~200
#     forwarding lines + private-attribute reads.


class DictConfig(BaseSettings):
    label: str = 'dict'


def build_dict_backend(**overrides: object) -> DictBackend:
    cfg = DictConfig(**overrides)
    return DictBackend(label=cfg.label)


register_backend('dict', build_dict_backend)


async def main() -> None:
    # explicit composition...
    fs = Storix(DictBackend(label='demo'))
    # ...or through the factory, now that it's registered:
    fs = get_storage('dict', label='demo')

    await fs.mkdir('/docs')
    await fs.echo(b'hello from a custom backend', '/docs/a.txt')

    print('cat    ->', await fs.cat('/docs/a.txt'))
    print('ls     ->', await fs.ls('/docs'))  # core-provided
    print('du     ->', await fs.du('/'), 'bytes')  # generic fallback
    print('locate ->', fs.locate('/docs/a.txt'))  # your physical URI


if __name__ == '__main__':
    asyncio.run(main())
