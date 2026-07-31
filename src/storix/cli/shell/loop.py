"""The REPL itself: the prompt loop, dispatch, built-ins, banner and help.

Reuses the Typer/Click parser from ``app`` - every command and flag works
identically to the one-shot CLI, so there is no second argument parser to
keep in sync. Only shell built-ins (exit/help/clear) are handled here.
"""

from __future__ import annotations

import contextlib
import io

from typing import TYPE_CHECKING

import click

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.shortcuts import CompleteStyle
from typer.main import get_command

from storix.config import user_config_path
from storix.errors import StorageError

from ..app import app
from ..config import load_prefs
from ..render import console, unstyled
from ..state import (
    cache_layer,
    current_fs,
    layer_summary,
    selection,
    use_fs,
)
from .completion import _ShellCompleter  # pyright: ignore[reportPrivateUsage]
from .globbing import _expand_globs  # pyright: ignore[reportPrivateUsage]
from .keys import (
    _ExitHint,  # pyright: ignore[reportPrivateUsage]
    _key_bindings,  # pyright: ignore[reportPrivateUsage]
)
from .layout import (
    _MENU_STYLE,  # pyright: ignore[reportPrivateUsage]
    _left_align_menu,  # pyright: ignore[reportPrivateUsage]
)
from .parsing import (
    _parse_input,  # pyright: ignore[reportPrivateUsage]
    _split_redirect,  # pyright: ignore[reportPrivateUsage]
    _unmark,  # pyright: ignore[reportPrivateUsage]
)


if TYPE_CHECKING:
    from collections.abc import Mapping

    from storix import Storix


_MAX_CWD = 30

_BUILTINS: dict[str, str] = {
    'clear': 'clear the screen',
    'exit': 'leave the shell',
    'help': 'show commands',
    'quit': 'leave the shell',
    'refresh': 'clear the cache layer',
}
"""Shell built-ins and the descriptions their completions display."""


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
