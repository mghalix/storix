"""Presentation for the storix CLI: consoles, icons, sizes, labels.

The icon and color table ships as package data (``data/icons.toml``,
Nerd Font glyphs harvested from eza) rather than code; edit the TOML to
retheme. Icons render only on a terminal and only when enabled
(``--no-icons`` / persistent prefs), mirroring eza's ``--icons=auto``.
"""

from __future__ import annotations

import tomllib

from functools import cache
from importlib import resources
from math import ceil
from typing import TYPE_CHECKING, Any, Final

from rich.console import Console
from rich.text import Text

from .state import icons_enabled


if TYPE_CHECKING:
    from typing import Literal

    from storix.models import Entry

    type DirState = Literal['closed', 'full', 'empty']


console = Console()
err = Console(stderr=True)


@cache
def _icon_table() -> dict[str, Any]:
    """The parsed icon/style table shipped as package data."""
    text = resources.files('storix.cli').joinpath('data/icons.toml').read_text('utf-8')
    return tomllib.loads(text)


def entry_decor(entry: Entry, *, dir_state: DirState = 'closed') -> tuple[str, str]:
    """The (icon, rich style) pair for a directory-listing entry.

    Files match by exact name first (``Makefile``), then extension, then
    the generic file decor. ``dir_state`` picks the folder glyph, and only
    a caller that *knows* should pass a knowing one: 'full' or 'empty'
    when the contents were looked at, 'closed' when they were not, so the
    glyph never claims what nobody checked. The icon is '' when icons are
    disabled or output is not a terminal.
    """
    table = _icon_table()
    if entry.is_dir:
        node = table['dir']
        icon = node['icon'] if dir_state == 'closed' else node[dir_state]
        # an empty folder recedes (its own style); full/unknown keep the color
        style = node['empty_style'] if dir_state == 'empty' else node['style']
    else:
        node = (
            table['name'].get(entry.name)
            or table['ext'].get(entry.name.rpartition('.')[2].lower())
            or table['file']
        )
        icon = node['icon']
        style = node.get('style', '')
    if not (icons_enabled() and console.is_terminal):
        icon = ''
    return icon, style


def entry_label(
    entry: Entry, *, slash: bool = True, dir_state: DirState = 'closed'
) -> Text:
    """A styled, icon-prefixed name for an entry (markup-safe)."""
    icon, style = entry_decor(entry, dir_state=dir_state)
    name = f'{entry.name}/' if slash and entry.is_dir else entry.name
    return Text(f'{icon} {name}' if icon else name, style=style)


def dir_state_of(*, populated: bool | None) -> DirState:
    """Map a known-contents answer onto a folder glyph state."""
    if populated is None:
        return 'closed'
    return 'full' if populated else 'empty'


_KIB: Final[int] = 1024
"""One binary kilobyte, the humanization base (IEC, like coreutils)."""

_ONE_DECIMAL_BELOW: Final[int] = 10
"""Under this scaled value coreutils shows one decimal (5.1M vs 165M)."""


def human_size(size: int) -> str:
    """GNU-style human size: powers of 1024, single-letter suffix.

    Mirrors coreutils ``du -h``/``ls -lh`` (equivalently ``numfmt
    --to=iec --round=up``): scale by 1024 until the value fits, round up,
    one decimal under 10 (``5.1M``), whole numbers above (``165M``).
    """
    if size < _KIB:
        return str(size)
    value = float(size)
    suffix = ''
    for suffix in 'KMGTPEZ':  # noqa: B007 - the suffix where the loop stops is used
        value /= _KIB
        # coreutils rounds before picking the unit: 1023.4K shows as 1.0M
        if ceil(value) < _KIB:
            break
    if value < _ONE_DECIMAL_BELOW:
        scaled = ceil(value * 10) / 10
        if scaled < _ONE_DECIMAL_BELOW:
            return f'{scaled:.1f}{suffix}'
    return f'{ceil(value)}{suffix}'
