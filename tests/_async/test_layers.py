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


# --- CacheLayer ---


class CountingBackend(MemoryBackend):
    """MemoryBackend that counts inner stat/list_dir calls, to prove hits."""

    def __init__(self) -> None:
        super().__init__()
        self.stat_calls = 0
        self.list_calls = 0

    async def stat(self, path):
        self.stat_calls += 1
        return await super().stat(path)

    async def list_dir(self, path):
        self.list_calls += 1
        async for entry in super().list_dir(path):
            yield entry


async def test_cache_layer_serves_repeat_reads_from_memory():
    from storix._async import Storix
    from storix._async.layers import CacheLayer

    inner = CountingBackend()
    fs = Storix(CacheLayer(inner))
    await fs.mkdir('/d')
    await fs.touch('/d/a.txt')

    inner.stat_calls = inner.list_calls = 0
    for _ in range(3):
        await fs.stat('/d/a.txt')
        await fs.ls('/d')
    # 3 iterations, but each distinct path hits the inner backend once:
    # /d/a.txt (fs.stat) and /d (ls's internal kind check) -> 2 stats, 1 list
    assert inner.stat_calls == 2
    assert inner.list_calls == 1


async def test_cache_layer_evicts_on_write():
    from storix._async import Storix
    from storix._async.layers import CacheLayer

    fs = Storix(CacheLayer(MemoryBackend()))
    await fs.echo(b'one', '/a.txt')
    assert (await fs.stat('/a.txt')).size == 3  # warms the cache
    await fs.echo(b'seventeen bytes!!', '/a.txt')  # mutation must evict
    assert (await fs.stat('/a.txt')).size == 17  # not a stale 3


async def test_cache_layer_evicts_listing_on_new_file():
    from storix._async import Storix
    from storix._async.layers import CacheLayer

    fs = Storix(CacheLayer(MemoryBackend()))
    await fs.mkdir('/d')
    assert await fs.ls('/d') == []  # warms empty listing
    await fs.touch('/d/a.txt')  # must evict the parent listing
    assert [p.name for p in await fs.ls('/d')] == ['a.txt']


async def test_cache_layer_caches_negative_then_evicts_on_create():
    from storix._async import Storix
    from storix._async.layers import CacheLayer

    fs = Storix(CacheLayer(MemoryBackend()))
    assert not await fs.exists('/a.txt')  # caches 'absent'
    await fs.touch('/a.txt')  # evicts the negative
    assert await fs.exists('/a.txt')


async def test_cache_layer_ttl_expires(monkeypatch: pytest.MonkeyPatch):
    from storix._async import Storix
    from storix._async.layers import CacheLayer

    clock = {'t': 1000.0}
    monkeypatch.setattr('time.monotonic', lambda: clock['t'])

    inner = CountingBackend()
    fs = Storix(CacheLayer(inner, ttl=30))
    await fs.touch('/a.txt')
    inner.stat_calls = 0
    await fs.stat('/a.txt')  # miss -> 1
    await fs.stat('/a.txt')  # hit -> still 1
    assert inner.stat_calls == 1

    clock['t'] += 31  # advance the clock past the ttl
    await fs.stat('/a.txt')  # expired -> re-fetch
    assert inner.stat_calls == 2


async def test_cache_layer_uses_a_custom_store():
    from storix._async import Storix
    from storix._async.layers import CacheLayer, CacheStore, InMemoryCacheStore

    class RecordingStore(InMemoryCacheStore):
        def __init__(self) -> None:
            super().__init__()
            self.ops: list[str] = []

        async def get(self, key, default=None):
            self.ops.append(f'get {key}')
            return await super().get(key, default)

        async def set(self, key, value, *, expire=None):
            self.ops.append(f'set {key}')
            await super().set(key, value, expire=expire)

        async def delete(self, key):
            self.ops.append(f'del {key}')
            await super().delete(key)

    store: CacheStore = RecordingStore()  # structural conformance
    fs = Storix(CacheLayer(MemoryBackend(), store=store))
    await fs.mkdir('/d')
    await fs.stat('/d')  # miss -> set, then a warm read
    await fs.stat('/d')  # hit

    assert any(o.startswith('set stat:/d') for o in store.ops)  # wrote through
    assert sum(o == 'get stat:/d' for o in store.ops) == 2  # both reads hit store
    # the mkdir evicted the parent listing through the same store:
    assert any(o.startswith('del list:/') for o in store.ops)


def test_inmemory_store_satisfies_the_protocol():
    from storix._async.layers import CacheStore, InMemoryCacheStore

    store: CacheStore = InMemoryCacheStore()  # the annotation is the test
    assert store is not None
