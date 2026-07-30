"""How the prompt's completion menu is coloured and where it sits."""

# pyright: reportUnusedFunction=false
# every helper below is used by a sibling module rather than by this one,
# which is what pyright's file-private reading of a leading underscore
# cannot see. Splitting them across modules is the point (ADR 0034).

from __future__ import annotations

from typing import TYPE_CHECKING

from prompt_toolkit.layout.menus import MultiColumnCompletionsMenu
from prompt_toolkit.styles import Style


if TYPE_CHECKING:
    from collections.abc import Iterator

    from prompt_toolkit import PromptSession
    from prompt_toolkit.layout.containers import Float


_MENU_STYLE = Style.from_dict(
    {
        # every default in prompt_toolkit's menu paints a background
        # (`completion-menu` is bg:#bbbbbb, the meta rows are grey, the
        # scrollbar is two more greys), which draws an opaque slab over a
        # terminal the user chose to make transparent. `bg:default` hands
        # each cell back to the terminal, so the menu floats the way a
        # shell's completion list does.
        # `noinherit` as well as `bg:default`: the default pairs the grey
        # background with a black foreground, and keeping that half would
        # leave black text on a dark terminal
        'completion-menu': 'noinherit bg:default',
        'completion-menu.completion': 'noinherit bg:default',
        # `reverse` rather than a chosen pair: it swaps whatever the entry
        # already is, so the highlight follows both the terminal theme and
        # the per-entry color a directory carries
        'completion-menu.completion.current': 'noinherit reverse',
        'completion-menu.meta.completion': 'bg:default fg:ansibrightblack',
        'completion-menu.meta.completion.current': 'bg:default fg:ansibrightblack',
        'completion-menu.multi-column-meta': 'bg:default fg:ansibrightblack',
        'scrollbar.background': 'bg:default',
        'scrollbar.button': 'bg:ansibrightblack',
        # the exit hint. prompt_toolkit's default is `reverse`, which is a
        # full-width bright bar for one short sentence; dim foreground on the
        # terminal's own background says the same thing quietly
        'bottom-toolbar': 'noreverse bg:default fg:ansibrightblack',
        'bottom-toolbar.text': 'noreverse bg:default fg:ansibrightblack',
    }
)
"""Prompt colors, in ansi names so they follow the terminal theme.

Every entry here exists to undo a prompt_toolkit default that paints a
background: the point is a menu and a hint that sit on the terminal's own
surface rather than over it."""


def _left_align_menu(session: PromptSession[str]) -> None:
    """Start the completion grid at the left edge instead of under the cursor.

    prompt_toolkit floats the menu at the cursor, so completing a long path
    indents the whole grid to wherever the caret happens to be and wastes
    the width to its left. Every shell lists completions from column zero,
    under the line rather than beside the caret.

    prompt_toolkit exposes no option for this, so the float it built is
    adjusted in place. ``ycursor`` stays, which is what keeps the grid
    directly below the prompt line.

    Args:
        session: The session whose layout to adjust.
    """
    # reaches into the layout prompt_toolkit assembled, for want of a
    # parameter; a no-op if the internals move, never an error
    for float_ in _menu_floats(session):
        float_.xcursor = False
        float_.left = 0


def _menu_floats(session: PromptSession[str]) -> Iterator[Float]:
    """Yield the floats holding a multi-column completion menu.

    Yields nothing when there is no layout to walk, so a cosmetic
    adjustment can never be what stops the prompt from opening.
    """
    layout = getattr(session, 'layout', None)
    if layout is None:
        return
    containers = [layout.container]
    while containers:
        container = containers.pop()
        for float_ in getattr(container, 'floats', ()) or ():
            if _holds_multi_column_menu(float_.content):
                yield float_
        containers.extend(getattr(container, 'children', ()) or ())


def _holds_multi_column_menu(container: object) -> bool:
    """Whether ``container`` wraps the grid menu, at any depth."""
    stack = [container]
    while stack:
        current = stack.pop()
        if isinstance(current, MultiColumnCompletionsMenu):
            return True
        stack.extend(getattr(current, 'children', ()) or ())
        nested = getattr(current, 'content', None)
        if nested is not None:
            stack.append(nested)
    return False
