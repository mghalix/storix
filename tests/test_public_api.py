"""The top-level public surface: sync (`storix`) and async (`storix.aio`).

These guard against `__all__` drift - names imported into the namespace
but forgotten in `__all__` (so type checkers reject them) and the two
flavors falling out of sync.
"""

import storix
import storix.aio


def test_flavors_export_the_same_public_surface():
    # storix and storix.aio must stay symmetric - identical names.
    assert set(storix.__all__) == set(storix.aio.__all__)


def test_every_exported_name_is_actually_present():
    for mod in (storix, storix.aio):
        for name in mod.__all__:
            assert hasattr(mod, name), f'{mod.__name__}.__all__ lists absent {name!r}'


def test_cache_api_is_public_from_both_flavors():
    # regression: CacheOp/CacheStore/InMemoryCacheStore were importable but
    # missing from __all__, so `from storix.aio import CacheOp` failed typing.
    names = ('CacheLayer', 'CacheOp', 'cache', 'CacheStore', 'InMemoryCacheStore')
    for mod in (storix, storix.aio):
        for name in names:
            assert name in mod.__all__, f'{mod.__name__} does not export {name}'
