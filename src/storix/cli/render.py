"""Presentation for the storix CLI: consoles, icons, sizes, labels.

Icons are provided by the eza-ported icon catalog (``icons.py``) using
Nerd Font codepoints. Icons render only on a terminal and only when
enabled (``--no-icons`` / persistent prefs), mirroring eza's ``--icons=auto``.
"""

from __future__ import annotations

import os
import subprocess
import sys

from math import ceil
from typing import TYPE_CHECKING, Final

import typer

from rich.console import Console
from rich.text import Text

from .config import load_prefs
from .icons import lookup_entry_decor
from .state import icons_enabled


if TYPE_CHECKING:
    from pathlib import Path
    from typing import Literal

    from storix.models import DirEntry

    type DirState = Literal['closed', 'full', 'empty']


console = Console()
err = Console(stderr=True)


def resolve_editor() -> str | None:
    """The editor command to open files with, or None if there is none.

    In order: the ``[cli] editor`` preference, because a user who set it
    for sx means it; then ``$VISUAL`` over ``$EDITOR``, the long-standing
    convention where the former names an editor that can hold a terminal,
    which is what a blocking hand-off needs; then ``notepad`` on Windows,
    where a fresh shell has neither variable set but does always have
    that. No such last resort on unix: ``vi`` and ``nano`` are both
    plausible and picking one for someone is worse than saying so.
    """
    configured = load_prefs().editor
    if configured:
        return configured
    inherited = os.environ.get('VISUAL') or os.environ.get('EDITOR')
    if inherited:
        return inherited
    return 'notepad' if sys.platform == 'win32' else None


def launch_editor(path: Path) -> None:
    """Open ``path`` in the user's editor and wait for it to close.

    Args:
        path: The local file to open.

    Raises:
        Exit: If no editor can be determined, since guessing which editor
            a user wants is not a thing to be clever about.
    """
    editor = resolve_editor()
    if editor is None:
        err.print(
            '[red]sx: no editor configured[/red]\n'
            'set $VISUAL or $EDITOR, or put [cyan]editor = "nvim"[/cyan] under '
            '[cyan][cli][/cyan] in your config ([cyan]sx config edit[/cyan])'
        )
        raise typer.Exit(1)
    subprocess.run([*editor.split(), str(path)], check=False)  # noqa: S603


def entry_decor(entry: DirEntry, *, dir_state: DirState = 'closed') -> tuple[str, str]:
    """The (icon, rich style) pair for a directory-listing entry.

    Files match by exact name first, then extension, then generic file decor.
    ``dir_state`` picks the folder glyph. The icon is '' when icons are
    disabled or output is not a terminal.
    """
    icon, style = lookup_entry_decor(
        entry.name, is_dir=entry.is_dir, dir_state=dir_state
    )
    if not (icons_enabled() and console.is_terminal):
        icon = ''
    return icon, style


def entry_label(
    entry: DirEntry, *, slash: bool = True, dir_state: DirState = 'closed'
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
