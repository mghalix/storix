"""Presentation for the storix CLI: consoles, icons, sizes, labels.

Icons are provided by the eza-ported icon catalog (``icons.py``) using
Nerd Font codepoints. Icons render only on a terminal and only when
enabled (``--no-icons`` / persistent prefs), mirroring eza's ``--icons=auto``.
"""

from __future__ import annotations

import os
import subprocess
import sys

from contextlib import contextmanager
from math import ceil
from typing import TYPE_CHECKING, Final

import typer

from rich.console import Console
from rich.text import Text

from .config import load_prefs
from .icons import lookup_entry_decor
from .state import icons_enabled


if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path
    from typing import Literal

    from storix.models import DirEntry

    type DirState = Literal['closed', 'full', 'empty']


console = Console()
err = Console(stderr=True)


@contextmanager
def unstyled() -> Generator[None]:
    """Render through ``console`` with no styling, for output leaving the terminal.

    Unix colors for a terminal and writes plain text for anything else, and
    a file or a pipe is the "anything else". Redirecting stdout is not
    enough on its own: rich resolves ``color_system='auto'`` once when the
    console is constructed, and that console is built at import time while
    stdout is still the terminal, so the cached answer keeps emitting
    escapes into a file that was never a terminal. ``no_color`` is also not
    enough - it removes color and leaves ``dim`` and ``bold``.

    Nulling the color system is what actually gates styling in rich's
    renderer, and there is no public setter for it.
    """
    # a private attribute, for want of a documented one: rich has no
    # setter for color_system, and a second Console cannot be substituted
    # because every command imported this one by name
    previous = console._color_system  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
    console._color_system = None  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
    try:
        yield
    finally:
        console._color_system = previous  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]


_OPEN_LINE_MARK: Final[str] = '%'
"""zsh's mark for output that stopped mid-line, borrowed for the same job.

zsh is where a unix user has already met it. bash leaves the case
unmarked, and fish spells it with a glyph outside ASCII.
"""


def close_line(tail: str | bytes) -> None:
    """End a line the written data did not end itself, marking that it happened.

    Output that stops mid-line is information for a storage tool: the file,
    or the command, ended without a newline. Closing that line silently
    keeps the next prompt off the data but throws the fact away, so the
    line is closed with a mark instead.

    The mark is inverse video, as zsh's is, because that is what keeps it
    from reading as a percent sign the command printed. It is the
    deliberate exception to the prompt's no-background rule (``_MENU_STYLE``
    in ``shell``): a completion menu is chrome and hands its cells back to
    a terminal the user chose to make transparent, while a mark that could
    pass for data has failed at its one job.

    Only a terminal is marked. Redirected or captured output is data and
    stays exactly the bytes that were written.

    Args:
        tail: The last character or byte written to stdout, empty when
            nothing was written. An empty tail leaves the cursor at the
            start of a line already, and a newline ended the line itself,
            so neither is marked.
    """
    if not tail or tail in {'\n', b'\n'} or not sys.stdout.isatty():
        return
    # a console resolved against the stream in hand rather than the shared
    # one: rich fixes a console's color system when it is built, and the
    # shared console is built at import (see `unstyled`), so it can only
    # answer for the stdout of that moment. A terminal that cannot do
    # inverse video (TERM=dumb) gets a plain mark, which is where zsh's own
    # ends up too.
    Console(file=sys.stdout).print(Text(_OPEN_LINE_MARK, style='reverse'))


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


def count_label(count: int, singular: str, plural: str) -> str:
    """Choose a count-sensitive label.

    Args:
        count: Quantity the label describes.
        singular: Label used for exactly one item.
        plural: Label used for every other count.
    """
    return singular if count == 1 else plural


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
