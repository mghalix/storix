"""The prompt's key bindings, and the "press again to exit" state they share."""

# pyright: reportUnusedFunction=false
# every helper below is used by a sibling module rather than by this one,
# which is what pyright's file-private reading of a leading underscore
# cannot see. Splitting them across modules is the point (ADR 0034).

from __future__ import annotations

import asyncio

from typing import TYPE_CHECKING, Final

from prompt_toolkit.application.current import get_app
from prompt_toolkit.filters import Condition, completion_is_selected
from prompt_toolkit.key_binding import KeyBindings

from .globbing import (
    _expand_on_line,  # pyright: ignore[reportPrivateUsage]
    _pattern_at_cursor,  # pyright: ignore[reportPrivateUsage]
)


if TYPE_CHECKING:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.key_binding.key_processor import KeyPressEvent


_HINT_SECONDS: Final[float] = 1.0
"""How long a "press again" hint stands before it lapses.

Long enough to read and act on, short enough that a press now and another
one minutes later is two separate intentions rather than an exit."""


class _ExitHint:
    """The "press again to exit" state, shared by the Ctrl+C and Ctrl+D keys.

    The hint is rendered as the prompt's bottom toolbar rather than printed,
    which is what keeps it under the line being typed instead of pushing a
    fresh prompt out below it. prompt_toolkit evaluates the toolbar's
    condition against the live attribute on every render, so clearing the
    attribute collapses the row and leaves no reserved blank line while
    nothing is armed.

    Args:
        session: The prompt session whose toolbar carries the hint.
    """

    def __init__(self, session: PromptSession[str]) -> None:
        self._session = session
        self._armed: str | None = None
        self._generation = 0

    def armed_for(self, key: str) -> bool:
        """Whether ``key`` is the key already waiting for its second press."""
        return self._armed == key

    def arm(self, key: str, message: str) -> None:
        """Show ``message`` for ``key`` and start its expiry.

        Args:
            key: The key this hint belongs to, so a different key's press
                does not satisfy it.
            message: The text to show beneath the prompt.
        """
        self._armed = key
        self._generation += 1
        generation = self._generation
        self._session.bottom_toolbar = message
        app = self._session.app
        app.invalidate()

        async def lapse() -> None:
            await asyncio.sleep(_HINT_SECONDS)
            # a later press supersedes this expiry rather than being cut
            # short by it, so only the newest generation may disarm
            if generation == self._generation:
                self.disarm()

        app.create_background_task(lapse())

    def disarm(self) -> None:
        """Drop the hint and the row it occupies.

        A no-op when nothing is armed, which is the common case: the loop
        disarms after every line, and forcing a redraw each time would be
        work for a row that is already absent.
        """
        if self._armed is None:
            return
        self._armed = None
        self._generation += 1
        self._session.bottom_toolbar = None
        self._session.app.invalidate()


def _cursor_on_pattern() -> bool:
    """Whether Tab is sitting on a word that expands instead of completing."""
    document = get_app().current_buffer.document
    return _pattern_at_cursor(document.text_before_cursor) is not None


def _key_bindings(hint: _ExitHint) -> KeyBindings:
    """Bind glob expansion, completion acceptance, and the two exit keys.

    Tab: a pattern is expanded on the line rather than offered as a
    completion candidate, because the two are different operations.
    Completion proposes candidates for one word and inserts the one chosen;
    expansion replaces one word with however many words it matched, which no
    single candidate can express - a candidate carrying the whole joined list
    would show one unreadable menu row, and picking a second one would
    replace the first expansion rather than add to it. That is why zsh
    expands in its line editor too. The filter is what keeps the ordinary
    path intact: with no unquoted wildcard under the cursor this binding is
    inactive and prompt_toolkit's own Tab handles the key.

    Enter: prompt_toolkit's default runs the line the moment you press Enter
    on a menu entry, so tab-completing a path and pressing Enter executes a
    half-written command. Every shell instead puts the completion on the
    line and waits, which is what lets you complete a second argument.

    Ctrl+C and Ctrl+D are bound here rather than left to raise out of
    ``prompt``, because a handler can put the hint under the live prompt and
    take it away again, where the loop around ``prompt`` can only print
    above a new one.

    Args:
        hint: The shared "press again" state both keys drive.
    """
    bindings = KeyBindings()

    @bindings.add('c-i', filter=Condition(_cursor_on_pattern))
    def _expand(event: KeyPressEvent) -> None:  # pyright: ignore[reportUnusedFunction]
        # the matching walk runs here rather than in the completion thread
        # `complete_in_thread` provides, so a pattern over a large tree holds
        # the prompt for as long as the walk takes; it is the same walk the
        # line pays on Enter, and moving it off the loop would mean rewriting
        # the buffer from another thread
        _expand_on_line(event.current_buffer)

    @bindings.add('enter', filter=completion_is_selected)
    def _accept(event: KeyPressEvent) -> None:  # pyright: ignore[reportUnusedFunction]
        event.current_buffer.complete_state = None

    @bindings.add('c-c')
    def _interrupt(event: KeyPressEvent) -> None:  # pyright: ignore[reportUnusedFunction]
        # an interrupt discards the line whatever its state, and that press
        # still counts as the first of the pair: clearing then exiting is two
        # presses rather than three
        had_text = bool(event.current_buffer.text)
        event.current_buffer.reset()
        if hint.armed_for('c-c') and not had_text:
            hint.disarm()
            event.app.exit(exception=EOFError)
            return
        hint.arm('c-c', ' press Ctrl+C again to exit')

    @bindings.add('c-d')
    def _end_of_input(event: KeyPressEvent) -> None:  # pyright: ignore[reportUnusedFunction]
        # end of input, not an interrupt: a terminal delivers the pending line
        # on Ctrl+D and only reports EOF on an empty one, so with text on the
        # line this does nothing at all rather than clearing or exiting
        if event.current_buffer.text:
            return
        if hint.armed_for('c-d'):
            hint.disarm()
            event.app.exit(exception=EOFError)
            return
        hint.arm('c-d', ' press Ctrl+D again to exit')

    return bindings
