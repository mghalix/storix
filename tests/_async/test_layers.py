from collections.abc import AsyncIterator
from pathlib import PurePosixPath as P

import pytest

from storix._async.backends import StorageBackend
from storix._async.backends.memory import MemoryBackend
from storix._async.layers import LayerBase, SandboxLayer
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


async def test_passthrough_layer_satisfies_protocol_and_delegates():
    base: StorageBackend = LayerBase(MemoryBackend())  # static conformance
    await put(base, '/a.txt', b'through')
    assert await base.read(P('/a.txt')) == b'through'
    assert base.capabilities.custom_metadata is True  # inherited from memory


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


# --- native-preference combinator ---


def test_when_missing_wraps_only_capability_poor_backends():
    from storix._async.layers import DataUrlLayer, when_missing
    from storix.enums import Capability

    build = when_missing(Capability.PRESIGNED_URLS, DataUrlLayer)

    # memory lacks presigned_urls -> wrapped and upgraded
    wrapped = build(MemoryBackend())
    assert isinstance(wrapped, DataUrlLayer)
    assert wrapped.capabilities.presigned_urls is True

    # a backend that already has it -> returned untouched (zero overhead)
    native = DataUrlLayer(MemoryBackend())  # now advertises presigned_urls
    assert build(native) is native


async def test_with_layer_missing_infers_capability_and_prefers_native():
    from storix._async import Storix
    from storix._async.layers import DataUrlLayer

    inner = MemoryBackend()  # no presigned_urls
    fs = Storix(inner).with_layer_missing(DataUrlLayer)  # capability inferred
    await fs.echo(b'x', '/a.txt')
    assert (await fs.url('/a.txt')).startswith('data:')

    # if the backend already had the capability, the layer is skipped:
    native = DataUrlLayer(MemoryBackend())
    fs2 = Storix(native).with_layer_missing(DataUrlLayer)
    assert isinstance(fs2.backend, DataUrlLayer)  # only one layer, not two


async def test_with_layer_missing_rejects_layers_without_provides():
    from storix._async import Storix
    from storix._async.layers import LayerBase

    with pytest.raises(ValueError, match='provides'):
        Storix(MemoryBackend()).with_layer_missing(LayerBase)


# --- DataUrlLayer ---


async def test_dataurl_layer_makes_urls_on_any_backend():
    from storix._async import Storix
    from storix._async.layers import DataUrlLayer

    fs = Storix(DataUrlLayer(MemoryBackend()))
    await fs.echo(b'hello', '/a.txt')
    url = await fs.url('/a.txt')
    assert url.startswith('data:')
    assert url.endswith('aGVsbG8=')  # base64('hello')


# --- MetadataLayer sidecar ---


async def test_metadata_layer_sidecar_is_invisible():
    from storix._async import Storix
    from storix._async.layers import MetadataLayer

    fs = Storix(MetadataLayer(MemoryBackend()))
    await fs.echo(b'x', '/a.txt', metadata={'owner': 'me'})

    # metadata round-trips, but the sidecar never surfaces
    assert (await fs.stat('/a.txt')).metadata == {'owner': 'me'}
    assert await fs.ls('/', all=True) == [P('a.txt')]
    assert not await fs.exists('/.storix-meta.json')
    assert await fs.du('/') == 1  # sidecar bytes excluded


async def test_metadata_layer_move_rekeys_sidecar():
    from storix._async import Storix
    from storix._async.layers import MetadataLayer

    fs = Storix(MetadataLayer(MemoryBackend()))
    await fs.echo(b'x', '/a.txt', metadata={'k': 'v'})
    await fs.mv('/a.txt', '/b.txt')

    assert (await fs.stat('/b.txt')).metadata == {'k': 'v'}
    assert not await fs.exists('/a.txt')


class RecordingSerializer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def dumps(self, obj: object) -> bytes:
        import json

        self.calls.append('dumps')
        return json.dumps(obj).encode()

    def loads(self, data: bytes) -> object:
        import json

        self.calls.append('loads')
        return json.loads(data)


async def test_metadata_layer_accepts_custom_codec():
    from storix._async import Storix
    from storix._async.layers import MetadataLayer

    rec = RecordingSerializer()
    fs = Storix(
        MetadataLayer(MemoryBackend(), serialize=rec.dumps, deserialize=rec.loads)
    )
    await fs.echo(b'x', '/a.txt', metadata={'k': 'v'})
    assert (await fs.stat('/a.txt')).metadata == {'k': 'v'}
    assert 'dumps' in rec.calls and 'loads' in rec.calls


async def test_with_layer_forwards_typed_kwargs_to_the_layer():
    from storix._async import Storix
    from storix._async.layers import MetadataLayer

    rec = RecordingSerializer()
    # serialize=/deserialize= forward (and type-check) straight through with_layer
    fs = Storix(MemoryBackend()).with_layer(
        MetadataLayer, serialize=rec.dumps, deserialize=rec.loads
    )
    await fs.echo(b'x', '/a.txt', metadata={'k': 'v'})
    assert (await fs.stat('/a.txt')).metadata == {'k': 'v'}
    assert rec.calls  # the injected codec was used


async def test_metadata_layer_delete_drops_sidecar_entry():
    from storix._async import Storix
    from storix._async.layers import MetadataLayer

    inner = MemoryBackend()
    fs = Storix(MetadataLayer(inner))
    await fs.echo(b'x', '/a.txt', metadata={'k': 'v'})
    await fs.rm('/a.txt')

    # recreating without metadata must not resurrect the old entry
    await fs.echo(b'y', '/a.txt')
    assert (await fs.stat('/a.txt')).metadata is None
