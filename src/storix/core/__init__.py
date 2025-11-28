from typing import TYPE_CHECKING

from storix._internal._lazy import _limp


__all__ = (
    'Finder',
    'Tree',
    'wc',
)


Finder = _limp('.find', 'Finder')
Tree = _limp('.tree', 'Tree')
c = _limp('.word_count', 'c')


if TYPE_CHECKING:
    from .find import Finder
    from .tree import Tree
    from .word_count import wc
