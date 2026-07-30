"""Interactive REPL for the storix CLI.

Reuses the Typer/Click parser from ``app`` - every command and flag works
identically to the one-shot CLI, so there is no second argument parser to
keep in sync. Only shell built-ins (exit/help/clear) are handled here.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import posixpath
import shlex

from itertools import takewhile
from typing import TYPE_CHECKING, Final

import click

from prompt_toolkit import PromptSession
from prompt_toolkit.application.current import get_app
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.filters import Condition, completion_is_selected
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.menus import MultiColumnCompletionsMenu
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.styles import Style
from typer.main import get_command

from storix.config import user_config_path
from storix.errors import StorageError

from .app import app
from .config import expand_alias, load_prefs
from .icons import lookup_entry_decor
from .render import console, entry_decor, unstyled
from .state import (
    cache_layer,
    current_fs,
    layer_summary,
    selection,
    use_fs,
)


if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.completion import CompleteEvent
    from prompt_toolkit.document import Document
    from prompt_toolkit.key_binding.key_processor import KeyPressEvent
    from prompt_toolkit.layout.containers import Float

    from storix import Storix


_MAX_CWD = 30

_WILDCARDS: Final[str] = '*?'
"""The glob metacharacters a prompt token is scanned for.

``**`` is two of the first; the across-directories meaning of the pair
comes from the core glob, which is what does the matching."""

_QUOTED: Final[str] = '\x00'
"""Marks a wildcard the user quoted, so tokenizing cannot lose the quotes.

``shlex.split`` strips quotes, so ``'*.txt'`` and ``*.txt`` reach the
tokens as one string and a pattern that was protected is indistinguishable
from one that was meant. Marking the protected wildcards before the split
and dropping the marks after keeps the two apart without a second
tokenizer. A control character because no prompt line can contain one."""

_BUILTINS: dict[str, str] = {
    'clear': 'clear the screen',
    'exit': 'leave the shell',
    'help': 'show commands',
    'quit': 'leave the shell',
    'refresh': 'clear the cache layer',
}
"""Shell built-ins and the descriptions their completions display."""

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


_UNESCAPED_PUNCTUATION: Final[str] = '_@%+=:,./-'
"""The ASCII punctuation a completed name may carry with no backslash.

The set `shlex.quote` calls safe, which is the punctuation no tokenizer,
glob, or redirect operator reads as syntax."""


def _escape_shell_path(name: str) -> str:
    """Quote one path component so tokenizing the line returns it unchanged.

    The contract is the round trip: `_parse_input` on what this produces
    yields exactly `name`. That is stated as a rule (backslash every ASCII
    character that is neither alphanumeric nor `_UNESCAPED_PUNCTUATION`)
    rather than a list of the characters noticed so far, because a list is
    silently short until a filename finds the gap. A glob wildcard was one
    such gap: `report*.md` inserted bare is a pattern over the directory
    rather than the file that was picked.

    A literal backslash is why this cannot be a chain of replacements. It has
    to be escaped too, and escaping any other character first makes the
    backslashes just inserted indistinguishable from the one in the name, so
    a name carrying both a backslash and a space arrived as two tokens.

    Non-ASCII is left alone. It is syntax to no tokenizer, and a backslash
    before every accent or emoji only makes the line unreadable.

    Args:
        name: An entry name, or a POSIX path of them, as the backend or the
            host filesystem reports it. The `/` separator is safe punctuation
            and stays unescaped. A Windows host separator never reaches here,
            because a directory prefix the user typed is passed through as
            typed rather than escaped.

    Returns:
        The name as a single shell token.
    """
    return ''.join(
        char
        if char.isalnum() or not char.isascii() or char in _UNESCAPED_PUNCTUATION
        else f'\\{char}'
        for char in name
    )


def _parse_completion_context(text_before_cursor: str) -> tuple[str, int, str]:
    """Parse text before cursor into (cmd_name, arg_index, current_word).

    arg_index is the 1-based index of the argument being typed:
    - 0 if the cursor is on the command name itself
    - 1 for the first argument after the command
    - 2 for the second argument after the command, etc.

    A trailing unescaped space means a fresh (empty) argument has begun, so the
    index counts every completed token. An escaped trailing space (part of a
    completed path that contains a space) still belongs to the last token, so
    the index stays on that token.
    """
    if not text_before_cursor.lstrip():
        return '', 0, ''
    try:
        tokens = shlex.split(text_before_cursor)
    except ValueError:
        tokens = text_before_cursor.split()
    if not tokens:
        return '', 0, ''

    ends_with_new_arg = text_before_cursor[-1].isspace() and not (
        len(text_before_cursor) > 1 and text_before_cursor[-2] == '\\'
    )
    cmd = tokens[0]
    if ends_with_new_arg:
        return cmd, len(tokens), ''
    return cmd, len(tokens) - 1, tokens[-1]


def _completion_matches(name: str, fragment: str) -> bool:
    """Whether ``name`` completes ``fragment``, per ``[cli] completion_case``.

    ``smart`` (the default) ignores case only until the user types an
    uppercase letter - at which point they clearly meant it.
    ``insensitive`` always ignores it, ``sensitive`` is the plain prefix
    test.

    Args:
        name: The candidate entry name.
        fragment: The word fragment the user has typed.
    """
    mode = load_prefs().completion_case
    if mode == 'insensitive' or (
        mode == 'smart' and not any(char.isupper() for char in fragment)
    ):
        return name.lower().startswith(fragment.lower())
    return name.startswith(fragment)


def _completion_order(name: str) -> tuple[str, str]:
    """Sort key for completions: the order a shell's own completion shows.

    Leading punctuation is ignored for the primary comparison, so
    ``_proto.py`` files between ``opendal.py`` and ``__pycache__`` rather
    than ahead of every letter. That is glibc's collation under a UTF-8
    locale, which is what coreutils `ls` and a zsh completion list both
    follow, and it is what stops a directory of dunder modules from opening
    with a block of underscores.

    Deliberately not the key `ls` uses: that listing follows eza, which
    files punctuation first, and the two are different views with different
    precedents rather than one inconsistency.

    Args:
        name: The entry name being ordered.
    """
    return name.lstrip('_.-').lower(), name.lower()


def _get_remote_completions(word: str) -> Iterator[Completion]:
    """Yield remote backend completions for `word`."""
    fragment = word.rpartition('/')[2]
    parent = word[: len(word) - len(fragment)]  # '' or ends with '/'
    try:
        entries = sorted(
            current_fs().scandir(parent or None, all=fragment.startswith('.')),
            key=lambda entry: _completion_order(entry.name),
        )
    except Exception:  # noqa: BLE001 - completion must never break the prompt
        return
    for entry in entries:
        if not _completion_matches(entry.name, fragment):
            continue
        icon = entry_decor(entry)[0]
        slash = '/' if entry.is_dir else ''
        label = f'{icon} {entry.name}{slash}' if icon else f'{entry.name}{slash}'
        escaped_name = _escape_shell_path(entry.name)
        yield Completion(
            f'{parent}{escaped_name}{slash}',
            start_position=-len(word),
            display=label,
            style='fg:ansibrightblue bold' if entry.is_dir else '',
        )


def _get_local_completions(word: str) -> Iterator[Completion]:
    """Yield local host machine completions for `word` (starting from cwd)."""
    from pathlib import Path

    if word == '~':
        yield Completion(
            '~/', start_position=-1, display='~/', style='fg:ansibrightblue bold'
        )
        return

    fragment = word.rpartition('/')[2]
    parent_str = word[: len(word) - len(fragment)]  # '' or ends with '/'

    target_dir = Path.cwd() if not parent_str else Path(parent_str).expanduser()
    fragment = word.rpartition('/')[2]
    parent_str = word[: len(word) - len(fragment)]  # '' or ends with '/'

    if not parent_str:
        target_dir = Path.cwd()
    elif parent_str.startswith('~/'):
        target_dir = Path.home() / parent_str[2:]
    else:
        target_dir = Path(parent_str)

    try:
        if not target_dir.is_dir():
            return
        entries = sorted(target_dir.iterdir(), key=lambda p: _completion_order(p.name))
    except Exception:  # noqa: BLE001 - completion must never break prompt
        return

    show_hidden = fragment.startswith('.')
    for path in entries:
        name = path.name
        if not show_hidden and name.startswith('.'):
            continue
        if not _completion_matches(name, fragment):
            continue

        try:
            is_dir = path.is_dir()
        except OSError:
            is_dir = False

        slash = '/' if is_dir else ''
        icon, _ = lookup_entry_decor(name, is_dir=is_dir)
        label = f'{icon} {name}{slash}' if icon else f'{name}{slash}'
        escaped_name = _escape_shell_path(name)

        yield Completion(
            f'{parent_str}{escaped_name}{slash}',
            start_position=-len(word),
            display=label,
            style='fg:ansibrightblue bold' if is_dir else '',
        )


class _ShellCompleter(Completer):
    """Tab candidates: command names first, context-aware path completion after.

    - push <1> <2>: <1> local host machine, <2> remote backend
    - pull <1> <2>: <1> remote backend, <2> local host machine
    - all other commands: remote backend paths
    """

    def __init__(self, commands: Mapping[str, str]) -> None:
        self._commands = dict(sorted(commands.items()))

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterator[Completion]:
        """Yield completions for the word before the cursor."""
        text = document.text_before_cursor
        cmd, arg_index, word = _parse_completion_context(text)

        if arg_index == 0:
            yield from (
                Completion(name, start_position=-len(word), display_meta=meta)
                for name, meta in self._commands.items()
                if name.startswith(word)
            )
            return

        if cmd == 'push':
            use_local = arg_index == 1
        elif cmd == 'pull':
            use_local = arg_index >= 2  # noqa: PLR2004
        else:
            use_local = False

        if use_local:
            yield from _get_local_completions(word)
        else:
            yield from _get_remote_completions(word)


def _prompt(fs: Storix) -> FormattedText:
    """The prompt: just where you are, starship-style.

    Who you are connected to and what wraps the session are stable facts,
    not per-line ones: the start banner states them once and ``whereami``
    reprints them on demand, rather than prefixing every command with a
    label that grows with each layer.
    """
    cwd = str(fs.pwd())
    if len(cwd) > _MAX_CWD:
        cwd = '...' + cwd[-(_MAX_CWD - 3) :]
    return FormattedText(
        [
            ('ansibrightblue bold', cwd),
            # the starship-style prompt glyph, deliberately not an ascii '>'
            ('ansimagenta bold', ' ❯ '),  # noqa: RUF001
        ]
    )


def _subcommands(command: click.Command) -> Mapping[str, click.Command]:
    """The registered subcommands, or empty when ``command`` is not a group."""
    return command.commands if isinstance(command, click.Group) else {}


def _help(commands: Mapping[str, click.Command]) -> None:
    """List the commands, grouped exactly as ``sx --help`` groups them.

    Derived from what is registered rather than restated here: the
    hand-written list drifted, advertising the hidden ``provider`` alias
    while never learning about ``find``, ``whereami``, ``doctor`` or
    ``config``.

    Args:
        commands: The registered subcommands, keyed by name.
    """
    console.print('[bold blue]storix shell[/bold blue] - unix over any backend\n')
    panels: dict[str, list[str]] = {}
    for name, sub in commands.items():
        if sub.hidden:
            continue
        panel = getattr(sub, 'rich_help_panel', None) or 'commands'
        panels.setdefault(panel.lower(), []).append(name)
    panels['shell'] = sorted(_BUILTINS)

    width = max(len(panel) for panel in panels)
    for panel, names in panels.items():
        console.print(f'  [cyan]{panel:<{width}}[/cyan]  {"  ".join(names)}')
    console.print('\n[dim]any command supports --help, e.g. `ls --help`[/dim]')


def _history() -> FileHistory:
    """The prompt history file, kept beside the user config.

    A shell that forgets every line the moment it exits is not one; the
    user config directory is where storix already keeps per-user state,
    so history follows it (``XDG_CONFIG_HOME`` included).
    """
    path = user_config_path().parent / 'history'
    path.parent.mkdir(parents=True, exist_ok=True)
    return FileHistory(str(path))


def _split_redirect(argv: list[str]) -> tuple[list[str], str | None, bool]:
    """Split a trailing ``> path`` / ``>> path`` off a command line.

    Redirection only, not pipes: the target is a backend path and the
    operator is an output sink, which needs no process model. ``cmd1 |
    cmd2`` does, and is deliberately not here.

    Args:
        argv: The tokenized line, after alias expansion.

    Returns:
        The command's own argv, the redirect target (None when there is
        no operator), and whether it appends.

    Raises:
        ValueError: If the operator has no target, or more than one.
    """
    for i, token in enumerate(argv):
        if not token.startswith('>'):
            continue
        append = token.startswith('>>')
        attached = token[2:] if append else token[1:]
        rest = argv[i + 1 :]
        target = attached or (rest.pop(0) if rest else '')
        if not target or rest:
            msg = 'redirect needs exactly one target: cmd > path'
            raise ValueError(msg)
        return argv[:i], target, append
    return argv, None, False


def _capture(command: click.Command, argv: list[str]) -> bytes:
    """Run one command with its stdout collected instead of printed.

    A text wrapper over a byte buffer, because both output paths have to
    land in the same place: ``cat`` writes bytes to ``stdout.buffer``
    while everything else prints text through rich.

    A redirect target gets text, not a rendering: ``unstyled`` drops the
    escapes and the column padding a table pads its last cell with is
    stripped, so a listing read back out of a file is the listing and
    nothing else. ``cat`` is unaffected, writing bytes storix never styled.
    """
    collected = io.BytesIO()
    text = io.TextIOWrapper(collected, encoding='utf-8', newline='')
    with unstyled(), contextlib.redirect_stdout(text):
        _dispatch(command, argv)
        text.flush()
    return _strip_padding(collected.getvalue())


def _strip_padding(output: bytes) -> bytes:
    """Drop the trailing spaces a fixed-width table leaves on every row.

    Args:
        output: The captured bytes, which may not be valid text at all.

    Returns:
        The same bytes with trailing horizontal whitespace removed from
        each line, or unchanged when they are not decodable text.
    """
    try:
        decoded = output.decode('utf-8')
    except UnicodeDecodeError:
        return output
    stripped = '\n'.join(line.rstrip(' \t') for line in decoded.split('\n'))
    return stripped.encode('utf-8')


def _mark_quoted(line: str) -> str:
    """Mark every quoted or escaped wildcard in ``line`` as a literal.

    Runs before ``shlex.split`` because the split is where the quotes go:
    the scan tracks only quote and escape state, which is all that decides
    whether a wildcard was protected, and leaves the tokenizing to shlex.

    Args:
        line: The line as typed.
    """
    marked: list[str] = []
    quote = ''
    escaped = False
    for char in line:
        if (escaped or quote) and char in _WILDCARDS:
            marked.append(_QUOTED)
        if escaped:
            escaped = False
        elif char == '\\' and quote != "'":
            escaped = True
        elif quote:
            quote = '' if char == quote else quote
        elif char in '\'"':
            quote = char
        marked.append(char)
    return ''.join(marked)


def _unmark(token: str) -> str:
    """Drop the literal marks, leaving the token as it was written."""
    return token.replace(_QUOTED, '')


def _is_pattern(token: str) -> bool:
    """Whether ``token`` holds a wildcard that was not quoted."""
    return any(
        char in _WILDCARDS and token[index - 1 : index] != _QUOTED
        for index, char in enumerate(token)
    )


def _match(pattern: str) -> list[str]:
    """Match ``pattern`` against the session, as sorted absolute paths.

    The leading wildcard-free segments become the glob's base rather than
    part of the pattern it walks: an absolute pattern is matched against a
    path relative to that base and so could never match from the cwd, and
    ``sub/*.md`` walks ``sub`` instead of every sibling of it.

    Hidden entries join the candidates only when the pattern's last segment
    asks for them with a leading dot, which is the pathlib and shell rule.

    The core glob walks the whole subtree below the base and tests every
    entry, so a shallow pattern still costs a full recursive listing. A
    bounded walk belongs in that glob, where every caller gets it, rather
    than in a second matcher here.

    Args:
        pattern: One prompt token, known to hold an unquoted wildcard.

    Returns:
        The matching paths in sorted order, empty when nothing matched.
    """
    segments = pattern.split('/')
    fixed = list(takewhile(lambda segment: not _is_pattern(segment), segments))
    base = '/'.join(fixed) or ('/' if pattern.startswith('/') else None)
    tail = '/'.join(segments[len(fixed) :])
    try:
        matches = current_fs().glob(
            tail, base, all=tail.rpartition('/')[2].startswith('.')
        )
        return sorted(str(path) for path in matches)
    except StorageError:
        # a base that is not there is a pattern matching nothing rather than
        # a line that failed, which is what a shell reports for `nosuch/*`
        return []


def _expand_globs(argv: list[str]) -> list[str]:
    """Replace the glob patterns in ``argv`` with what they match.

    The outer shell cannot do this: the paths are in the backend, so a
    pattern typed at the prompt reaches the command untouched and the
    command reports a path that never existed. Expanding the whole line here
    instead of per command is what makes it uniform, and is where a shell
    does it too.

    The command name and any option token are left alone, because a pattern
    is only a pattern in a path position: a wildcard in the command name is
    a command that does not exist, which Click says better than a matcher
    can, and a leading ``-`` is an option however it is spelled. A redirect
    target is already split off by the time this runs and stays literal for
    the same reason: it names a file being written, not one to be found.

    Args:
        argv: The tokenized line, with any redirect already split off.

    Returns:
        The line with each pattern replaced by its matches in argument
        order, and every quoted wildcard restored as a plain character.

    Raises:
        ValueError: If a pattern matches nothing.
    """
    if not argv:
        return argv
    expanded = [_unmark(argv[0])]
    for token in argv[1:]:
        if token.startswith('-') or not _is_pattern(token):
            expanded.append(_unmark(token))
            continue
        matches = _match(token)
        if not matches:
            msg = f'no matches: {token}'
            raise ValueError(msg)
        expanded.extend(matches)
    return expanded


def _parse_input(line: str, aliases: dict[str, str]) -> list[str]:
    """Parse a prompt line into tokenized argv, expanding aliases if defined.

    The tokens carry the literal marks ``_mark_quoted`` left, which
    ``_expand_globs`` reads and removes.
    """
    argv = shlex.split(_mark_quoted(line))
    return expand_alias(argv, aliases) if (argv and aliases) else argv


def _last_word(text: str) -> str:
    """The trailing word of ``text``, exactly as it was typed.

    The extent to replace on the line, which the tokens cannot give: they
    have already lost the quotes and escapes the buffer still holds. Split on
    the last space the user did not escape, so a path written with an escaped
    space stays one word.
    """
    for index in range(len(text) - 1, -1, -1):
        if text[index].isspace() and text[index - 1 : index] != '\\':
            return text[index + 1 :]
    return text


def _pattern_at_cursor(text: str) -> tuple[str, str] | None:
    """The word at the cursor and the pattern it holds, or None.

    Returns the word as typed together with the token it tokenizes to, which
    is the form ``_match`` wants (marks included, as ``_expand_globs`` passes
    them).

    None means Tab completes instead of expanding, which is every word
    without an unquoted wildcard, plus three that hold one and are still not
    patterns: a word carrying a quote (the quotes are what make the wildcard
    a plain character, and a matcher that never sees them cannot tell), the
    command name (a wildcard there is a command that does not exist, which
    Click says better than a matcher can), and an option (a leading ``-`` is
    an option however it is spelled). The last two are the positions
    ``_expand_globs`` leaves alone on Enter as well.

    Args:
        text: The line up to the cursor.
    """
    word = _last_word(text)
    if not word or word.startswith('-') or '"' in word or "'" in word:
        return None
    if not text[: len(text) - len(word)].strip():
        return None
    try:
        tokens = shlex.split(_mark_quoted(word))
    except ValueError:
        # an unfinished escape is a word still being typed, not a pattern
        return None
    if not tokens or not _is_pattern(tokens[0]):
        return None
    return word, tokens[0]


def _expansion(matches: Sequence[str], pattern: str) -> str:
    """The text ``matches`` become on the line, at the depth as typed.

    ``_match`` answers in absolute paths, and putting those back on the line
    would lose what the user chose to write: ``ls *.md`` in a deep directory
    would grow into a line of full paths for names the cwd already fixes.
    Only a pattern written absolute expands to absolute names, which is what
    a shell shows.

    The names are escaped rather than quoted, so one holding a space survives
    the tokenizer the line goes back through, and a trailing space follows
    several of them: an expansion to more than one name is finished, where a
    single one is often a path being completed a component at a time.

    Args:
        matches: The absolute paths the pattern matched.
        pattern: The token that matched them, as it was typed.
    """
    if pattern.startswith('/'):
        names = list(matches)
    else:
        cwd = str(current_fs().pwd())
        names = [posixpath.relpath(match, cwd) for match in matches]
    line = ' '.join(_escape_shell_path(name) for name in names)
    return f'{line} ' if len(names) > 1 else line


def _expand_on_line(buffer: Buffer) -> None:
    """Replace the pattern at the cursor with what it matches, in place.

    Seeing the names before the line runs is the point: an expansion that
    only ever happened on Enter leaves the user to trust that ``rm *.tmp``
    selected what they meant.

    A pattern that matches nothing is left alone, pattern and all, rather
    than emptied. zsh does the same, and the alternative destroys the one
    thing the user can correct.

    Args:
        buffer: The prompt buffer whose line is rewritten.
    """
    at_cursor = _pattern_at_cursor(buffer.document.text_before_cursor)
    if at_cursor is None:
        return
    word, pattern = at_cursor
    matches = _match(pattern)
    if not matches:
        return
    buffer.delete_before_cursor(len(word))
    buffer.insert_text(_expansion(matches, pattern))


def _banner(fs: Storix) -> None:
    """State what the session is, once, instead of on every prompt.

    Which profile and stage are in force is the one thing a prompt showing
    only the cwd cannot tell you, and the thing a wrong answer is most
    expensive on. ``whereami`` reprints it later.
    """
    console.print('[bold blue]storix shell[/bold blue]')
    where = f'connected to [green]{type(fs.base_backend).__name__}[/green]'
    profile, environment = selection()
    if profile:
        stage = f' (stage: {environment})' if environment else ''
        where += f' as [green]{profile}[/green]{stage}'
    console.print(where)
    summary = layer_summary(fs)
    if summary:
        tip = ' · type [cyan]refresh[/cyan] to clear' if cache_layer(fs) else ''
        console.print(f'[green]{summary}[/green]{tip}')
    console.print(
        "type 'help' for commands, 'whereami' for this session, 'exit' to quit\n"
    )


def start_shell(fs: Storix | None = None) -> None:
    """Run the interactive shell over ``fs`` (or the default session)."""
    if fs is not None:
        use_fs(fs)
    fs = current_fs()

    prefs = load_prefs()
    command = get_command(app)
    commands = {
        name: sub.get_short_help_str(60) for name, sub in _subcommands(command).items()
    }
    alias_cmds = {name: f"alias: '{target}'" for name, target in prefs.alias.items()}
    session: PromptSession[str] = PromptSession(
        completer=_ShellCompleter({**commands, **alias_cmds, **_BUILTINS}),
        history=_history(),
        complete_while_typing=False,
        complete_in_thread=True,
        # the grid every shell's completion uses, rather than prompt_toolkit's
        # single tall column: a directory of 20 entries is three rows instead
        # of twenty, so the listing stays on screen beside the line it is
        # completing
        complete_style=CompleteStyle.MULTI_COLUMN,
        style=_MENU_STYLE,
    )
    # the hint needs the session (it writes its toolbar) and the bindings need
    # the hint, so it is wired after construction rather than in the call
    hint = _ExitHint(session)
    session.key_bindings = _key_bindings(hint)
    _left_align_menu(session)

    _banner(fs)

    # two presses of the same key leave and one never does; the pair and its
    # hint live in the key bindings, which is the only place that can show the
    # hint under the live prompt (see _ExitHint). Reaching here means a key
    # asked to exit, or a line is ready to run.
    while True:
        try:
            line = session.prompt(_prompt(current_fs())).strip()
        except (EOFError, KeyboardInterrupt):
            console.print('[yellow]bye[/yellow]')
            return

        hint.disarm()
        if line and not _run_line(command, line, prefs.alias):
            console.print('[yellow]bye[/yellow]')
            return


def _run_line(command: click.Command, line: str, aliases: dict[str, str]) -> bool:
    """Execute one prompt line.

    Args:
        command: The shared Click group every non-built-in goes through.
        line: The line as typed, already stripped and known non-empty.
        aliases: Alias table from the preferences.

    Returns:
        False when the line asked the shell to exit, True otherwise.
    """
    try:
        argv, redirect, append = _split_redirect(_parse_input(line, aliases))
    except ValueError as exc:
        console.print(f'[red]parse error: {exc}[/red]')
        return True
    if not argv:
        console.print('[red]parse error: redirect needs a command[/red]')
        return True

    try:
        argv = _expand_globs(argv)
    except ValueError as exc:
        # nothing runs on an unmatched pattern: the command could be `rm`,
        # and handing it the pattern would either report a path that never
        # existed or address a literal `*` object
        console.print(f'[red]{exc}[/red]')
        return True
    if redirect is not None:
        redirect = _unmark(redirect)

    name = argv[0]
    if name in {'exit', 'quit'}:
        return False
    if _builtin(name, command):
        return True

    if redirect is None:
        _dispatch(command, argv)
    else:
        try:
            current_fs().echo(
                _capture(command, argv), redirect, mode='a' if append else 'w'
            )
        except StorageError as exc:
            console.print(f'[red]{name}: {exc}[/red]')
    return True


def _builtin(name: str, command: click.Command) -> bool:
    """Run the shell built-in called ``name``, if it is one.

    Args:
        name: The first token of the line.
        command: The shared Click group, which ``help`` lists.

    Returns:
        True when ``name`` was a built-in and has now run.
    """
    if name == 'help':
        _help(_subcommands(command))
    elif name == 'clear':
        console.clear()
    elif name == 'refresh':
        layer = cache_layer(current_fs())
        if layer is None:
            console.print('[yellow]no cache layer active[/yellow]')
        else:
            layer.clear()
            console.print('[green]cache cleared[/green]')
    else:
        return False
    return True


def _dispatch(command: click.Command, argv: list[str]) -> None:
    """Feed one line to the shared Click parser, swallowing its exits."""
    try:
        command.main(argv, prog_name='', standalone_mode=False)
    except click.ClickException as exc:
        exc.show()
    except (click.exceptions.Abort, SystemExit):
        pass
    except Exception as exc:  # noqa: BLE001 - the REPL must survive any command
        console.print(f'[red]{exc}[/red]')
