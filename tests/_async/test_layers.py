from collections.abc import AsyncIterator
from pathlib import PurePosixPath as P

import pytest

from storix._async.backends import StorageBackend
from storix._async.backends.memory import MemoryBackend
from storix._async.layers import SandboxLayer
from storix.errors import PathNotFoundError
from storix.types import EchoMode


async def _astream(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


async def put(
    backend: StorageBackend, path: str, data: bytes = b'', mode: EchoMode = 'w'
) -> None:
    await backend.write(P(path), _astream(data), mode=mode, content_type=None)


@pytest.fixture
async def jailed() -> tuple[MemoryBackend, SandboxLayer]:
    inner = MemoryBackend()
    await inner.make_dir(P('/jail'), parents=False)
    return inner, SandboxLayer(inner, root='/jail')


def test_satisfies_protocol():
    # the annotation is the test: type checkers verify structural conformance
    layer: StorageBackend = SandboxLayer(MemoryBackend(), root='/')
    assert layer.capabilities.content_type is False


async def test_paths_are_anchored_under_root(
    jailed: tuple[MemoryBackend, SandboxLayer],
):
    inner, layer = jailed
    await put(layer, '/a.txt', b'scoped')
    assert await inner.read(P('/jail/a.txt')) == b'scoped'
    assert await layer.read(P('/a.txt')) == b'scoped'


async def test_traversal_cannot_escape(jailed: tuple[MemoryBackend, SandboxLayer]):
    inner, layer = jailed
    await inner.make_dir(P('/secret'), parents=False)
    await put(inner, '/secret/key.txt', b'nope')

    # '..' bypassing the core clamps at the virtual root, not the real one
    with pytest.raises(PathNotFoundError):
        await layer.read(P('/../secret/key.txt'))


async def test_errors_are_rescoped_to_virtual_paths(
    jailed: tuple[MemoryBackend, SandboxLayer],
):
    _, layer = jailed
    with pytest.raises(PathNotFoundError) as excinfo:
        await layer.stat(P('/nope'))
    assert str(excinfo.value.path) == '/nope'
    assert 'jail' not in str(excinfo.value)


async def test_rescopes_parent_paths_from_inner_errors(
    jailed: tuple[MemoryBackend, SandboxLayer],
):
    _, layer = jailed
    with pytest.raises(PathNotFoundError) as excinfo:
        await layer.make_dir(P('/missing/child'), parents=False)
    assert str(excinfo.value.path) == '/missing'


async def test_translation_is_public_for_audit(
    jailed: tuple[MemoryBackend, SandboxLayer],
):
    """The audit pattern: the layer owner records real paths; the
    sandboxed session only ever sees virtual ones.
    """
    from storix._async import Storix

    inner, layer = jailed
    fs = Storix(layer)
    await fs.mkdir('/videos')
    await fs.cd('/videos')
    await fs.echo(b'...', 'abc123.mp4')

    audit_path = layer.to_real(fs.resolve('abc123.mp4'))
    assert str(audit_path) == '/jail/videos/abc123.mp4'
    assert await inner.exists(audit_path)

    # and back: reconstruct the virtual name from the audited real path
    assert str(layer.to_virtual(audit_path)) == '/videos/abc123.mp4'


async def test_layers_compose(jailed: tuple[MemoryBackend, SandboxLayer]):
    inner, layer = jailed
    await layer.make_dir(P('/deeper'), parents=False)
    nested = SandboxLayer(layer, root='/deeper')
    await put(nested, '/a.txt', b'twice jailed')
    assert await inner.read(P('/jail/deeper/a.txt')) == b'twice jailed'
