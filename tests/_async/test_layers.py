import time

from collections.abc import AsyncIterator
from pathlib import PurePosixPath as P

import pytest

from storix._async.backends import StorageBackend
from storix._async.backends.memory import MemoryBackend
from storix._async.layers import LayerBase, SandboxLayer
from storix.errors import PathNotFoundError
from storix.models import Capabilities
from storix.types import EchoMode


async def _astream(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


async def put(
    backend: StorageBackend, path: str, data: bytes = b'', mode: EchoMode = 'w'
) -> None:
    await backend.write_stream(P(path), _astream(data), mode=mode, content_type=None)


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

    build = when_missing(DataUrlLayer)  # capability inferred from provides

    # memory lacks presigned_urls -> wrapped and upgraded
    wrapped = build(MemoryBackend())
    assert isinstance(wrapped, DataUrlLayer)
    assert wrapped.capabilities.presigned_urls is True

    # a backend that already has it -> returned untouched (zero overhead)
    native = DataUrlLayer(MemoryBackend())  # now advertises presigned_urls
    assert build(native) is native


def test_when_missing_rejects_layers_without_provides():
    from storix._async.layers import LayerBase, when_missing

    with pytest.raises(ValueError, match='provides'):
        when_missing(LayerBase)


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
    with pytest.raises(PathNotFoundError):
        await fs.cat('/.storix-meta.json')


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
    fs = Storix(CacheLayer(MemoryBackend(), store=store, environment='prod'))
    await fs.mkdir('/d')
    await fs.stat('/d')  # miss -> set, then a warm read
    await fs.stat('/d')  # hit

    # keys are prefixed and keyed on the physical locator (not the raw path)
    stat_key = fs.backend._key('stat', P('/d'))  # type: ignore[attr-defined]
    assert stat_key.startswith('storix:prod:stat:')  # namespace:env:op:locator
    assert any(o == f'set {stat_key}' for o in store.ops)  # wrote through
    assert sum(o == f'get {stat_key}' for o in store.ops) == 2  # both reads hit
    # the mkdir evicted the parent listing through the same store:
    assert any(o.startswith('del storix:prod:list:') for o in store.ops)


def test_inmemory_store_satisfies_the_protocol():
    from storix._async.layers import CacheStore, InMemoryCacheStore

    store: CacheStore = InMemoryCacheStore()  # the annotation is the test
    assert store is not None


# --- CacheLayer: configurable ops ---


async def test_cache_du_when_enabled_and_evicts_ancestors():
    from storix._async import Storix
    from storix._async.layers import CacheLayer, cache

    inner = CountingBackend()
    inner.du_calls = 0
    orig_du = inner.du

    async def counting_du(path):
        inner.du_calls += 1
        return await orig_du(path)

    inner.du = counting_du  # type: ignore[method-assign]
    fs = Storix(CacheLayer(inner, du=cache(ttl=60)))
    await fs.mkdir('/a')
    await fs.echo(b'12345', '/a/f.txt')

    inner.du_calls = 0
    assert await fs.du('/a') == 5
    assert await fs.du('/a') == 5  # cached
    assert inner.du_calls == 1

    await fs.echo(b'more', '/a/g.txt')  # write -> evicts du of /a and /
    assert await fs.du('/a') == 9  # recomputed
    assert inner.du_calls == 2


async def test_cache_du_off_by_default():
    from storix._async import Storix
    from storix._async.layers import CacheLayer

    fs = Storix(CacheLayer(MemoryBackend()))  # du not enabled
    await fs.mkdir('/a')
    await fs.echo(b'x', '/a/f.txt')
    assert await fs.du('/a') == 1  # works, just not cached (passthrough)


async def test_cache_read_content_with_max_bytes_skip():
    from storix._async import Storix
    from storix._async.layers import CacheLayer, cache

    class ReadCounter(MemoryBackend):
        reads = 0

        async def read_stream(self, path, *, chunk_size=None):
            ReadCounter.reads += 1
            async for c in super().read_stream(path, chunk_size=chunk_size):
                yield c

    inner = ReadCounter()
    fs = Storix(CacheLayer(inner, read=cache(max_bytes=4)))
    await fs.echo(b'abc', '/small.txt')  # 3 bytes <= 4 -> cached
    await fs.echo(b'toolong', '/big.txt')  # 7 bytes > 4 -> not cached

    ReadCounter.reads = 0
    assert await fs.cat('/small.txt') == b'abc'
    assert await fs.cat('/small.txt') == b'abc'  # cached
    assert ReadCounter.reads == 1

    ReadCounter.reads = 0
    assert await fs.cat('/big.txt') == b'toolong'
    assert await fs.cat('/big.txt') == b'toolong'  # NOT cached (too big)
    assert ReadCounter.reads == 2


async def test_cache_per_op_stores_are_independent():
    from storix._async import Storix
    from storix._async.layers import CacheLayer, InMemoryCacheStore, cache

    meta_store = InMemoryCacheStore()
    read_store = InMemoryCacheStore()
    fs = Storix(
        CacheLayer(
            MemoryBackend(),
            metadata=cache(store=meta_store),
            read=cache(store=read_store),
        )
    )
    await fs.echo(b'x', '/a.txt')
    await fs.stat('/a.txt')
    await fs.cat('/a.txt')

    assert any('stat' in k for k in meta_store._data)
    assert not any('read' in k for k in meta_store._data)  # read went elsewhere
    assert any('read' in k for k in read_store._data)


async def test_inmemory_store_maxsize_evicts_lru():
    from storix._async.layers import InMemoryCacheStore

    store = InMemoryCacheStore(maxsize=2)
    await store.set('a', 1)
    await store.set('b', 2)
    await store.get('a')  # touch 'a' -> 'b' now LRU
    await store.set('c', 3)  # over cap -> evict LRU ('b')

    assert await store.get('a') == 1
    assert await store.get('c') == 3
    assert await store.get('b', 'gone') == 'gone'  # evicted


async def test_cache_url_ttl_only_and_capped_to_lifetime():
    from storix._async import Storix
    from storix._async.layers import CacheLayer, InMemoryCacheStore, cache

    class Signer(MemoryBackend):
        capabilities = Capabilities(custom_metadata=True, presigned_urls=True)
        mints = 0

        async def make_url(self, path, *, expires_in=None):
            Signer.mints += 1
            return f'https://signed/{path}?n={Signer.mints}&e={expires_in}'

    inner = Signer()
    store = InMemoryCacheStore()
    # ttl far above lifetime -> must be capped to the 30s URL lifetime
    fs = Storix(CacheLayer(inner, url=cache(ttl=99_999), store=store))
    await fs.echo(b'x', '/a.txt')

    Signer.mints = 0
    u1 = await fs.url('/a.txt', expires_in=30)
    u2 = await fs.url('/a.txt', expires_in=30)
    assert u1 == u2  # cached, minted once
    assert Signer.mints == 1

    # different expires_in is a different URL (part of the key)
    u3 = await fs.url('/a.txt', expires_in=60)
    assert u3 != u1
    assert Signer.mints == 2

    # entry never outlives the URL: capped at lifetime, not the 99_999 ttl
    key = f'{fs.backend._key("url", P("/a.txt"))}:30'
    deadline, _ = store._data[key]
    assert deadline is not None and deadline <= time.monotonic() + 30


async def test_cache_url_survives_writes():
    from storix._async import Storix
    from storix._async.layers import CacheLayer, cache

    class Signer(MemoryBackend):
        capabilities = Capabilities(custom_metadata=True, presigned_urls=True)
        mints = 0

        async def make_url(self, path, *, expires_in=None):
            Signer.mints += 1
            return f'https://signed/{path}?n={Signer.mints}'

    inner = Signer()
    fs = Storix(CacheLayer(inner, url=cache(ttl=60)))
    await fs.echo(b'x', '/a.txt')

    Signer.mints = 0
    u1 = await fs.url('/a.txt')
    await fs.echo(b'changed', '/a.txt')  # content change does NOT invalidate a URL
    u2 = await fs.url('/a.txt')
    assert u1 == u2  # still cached
    assert Signer.mints == 1


async def test_cache_url_off_by_default():
    from storix._async import Storix
    from storix._async.layers import CacheLayer

    class Signer(MemoryBackend):
        capabilities = Capabilities(custom_metadata=True, presigned_urls=True)
        mints = 0

        async def make_url(self, path, *, expires_in=None):
            Signer.mints += 1
            return 'https://signed/x'

    inner = Signer()
    fs = Storix(CacheLayer(inner))  # url not enabled
    await fs.echo(b'x', '/a.txt')
    Signer.mints = 0
    await fs.url('/a.txt')
    await fs.url('/a.txt')
    assert Signer.mints == 2  # passthrough, not cached


async def test_cache_clear_drops_only_this_namespace():
    from storix._async import Storix
    from storix._async.layers import CacheLayer, InMemoryCacheStore

    store = InMemoryCacheStore()
    fs = Storix(CacheLayer(MemoryBackend(), du=True, store=store, environment='prod'))
    await fs.echo(b'x', '/a.txt')
    await fs.stat('/a.txt')
    await fs.du('/')
    assert any(k.startswith('storix:prod:') for k in store._data)
    # a foreign key sharing the same store (different namespace) must survive
    await store.set('other:stat:/z', 'keep')

    await fs.backend.clear()

    assert await store.get('other:stat:/z') == 'keep'
    assert not any(k.startswith('storix:prod:') for k in store._data)


# --- ObservabilityLayer ---


async def test_observability_layer_emits_cumulative_transfer_events():
    from storix._async.layers import ObservabilityLayer, TransferEvent

    events: list[TransferEvent] = []
    layer = ObservabilityLayer(MemoryBackend(), sink=events.append)

    await layer.write_stream(
        P('/a.bin'), _astream(b'12345', b'678'), mode='w', content_type=None
    )
    # cumulative per pulled chunk, ending at the known payload size
    assert [e.transferred for e in events] == [5, 8]
    assert all(e.op == 'write' and e.path == P('/a.bin') for e in events)

    events.clear()
    data = b''.join([c async for c in layer.read_stream(P('/a.bin'))])
    assert data == b'12345678'
    assert events[-1].transferred == 8
    assert all(e.op == 'read' and e.path == P('/a.bin') for e in events)


async def test_observability_layer_awaits_an_async_sink():
    from storix._async.layers import ObservabilityLayer, TransferEvent

    events: list[TransferEvent] = []

    async def sink(event: TransferEvent) -> None:
        events.append(event)

    layer = ObservabilityLayer(MemoryBackend(), sink=sink)
    await layer.write_stream(P('/a.bin'), _astream(b'abc'), mode='w', content_type=None)
    assert [e.transferred for e in events] == [3]


# --- without_layer / uncached ---


async def test_without_layer_drops_cache_but_keeps_the_jail():
    from storix._async import Storix
    from storix._async.layers import CacheLayer, SandboxLayer
    from storix.errors import NonRemovableLayerError

    inner = MemoryBackend()
    await inner.make_dir(P('/jail'), parents=False)
    fs = Storix(CacheLayer(SandboxLayer(inner, root='/jail')))

    # uncached view bypasses the cache but preserves the sandbox
    bare = fs.without_layer(CacheLayer)
    assert not isinstance(bare.backend, CacheLayer)
    assert isinstance(bare.backend, SandboxLayer)

    # the jail is a boundary: it can never be stripped
    with pytest.raises(NonRemovableLayerError, match='SandboxLayer'):
        fs.without_layer(SandboxLayer)


async def test_without_layer_absent_is_noop_and_preserves_cwd():
    from storix._async import Storix
    from storix._async.layers import CacheLayer

    fs = Storix(MemoryBackend())
    await fs.mkdir('/a')
    await fs.cd('/a')
    # no cache present -> a graceful no-op that keeps cwd
    view = fs.without_layer(CacheLayer)
    assert str(view.pwd()) == '/a'
    assert type(view.backend).__name__ == 'MemoryBackend'


async def test_uncached_bypasses_the_cache_for_a_fresh_read():
    from storix._async import Storix
    from storix._async.layers import CacheLayer

    class Counter(MemoryBackend):
        stat_calls = 0

        async def stat(self, path):
            Counter.stat_calls += 1
            return await super().stat(path)

    inner = Counter()
    fs = Storix(CacheLayer(inner))
    await fs.echo(b'x', '/a.txt')

    Counter.stat_calls = 0
    await fs.stat('/a.txt')  # miss -> 1 backend stat, now cached
    await fs.stat('/a.txt')  # hit -> still 1
    assert Counter.stat_calls == 1
    await fs.uncached.stat('/a.txt')  # bypass -> hits the backend again
    assert Counter.stat_calls == 2


def test_bound_layer_type_is_public():
    from storix import BoundLayer as SyncBound
    from storix.aio import BoundLayer as AsyncBound

    assert SyncBound is not None and AsyncBound is not None
