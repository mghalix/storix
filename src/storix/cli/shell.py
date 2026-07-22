"""Interactive REPL for the storix CLI.

Reuses the Typer/Click parser from ``app`` - every command and flag works
identically to the one-shot CLI, so there is no second argument parser to
keep in sync. Only shell built-ins (exit/help/clear) are handled here.
"""

from __future__ import annotations

import shlex

from typing import TYPE_CHECKING

import click

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style
from typer.main import get_command

from .app import app
from .config import expand_alias, load_prefs
from .icons import lookup_entry_decor
from .render import console, entry_decor
from .state import (
    cache_layer,
    current_fs,
    layer_summary,
    use_fs,
)


if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from prompt_toolkit.completion import CompleteEvent
    from prompt_toolkit.document import Document

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

_MENU_STYLE = Style.from_dict(
    {
        'completion-menu': 'bg:ansibrightblack ansiwhite',
        'completion-menu.completion.current': 'bg:ansiblue ansiwhite bold',
        'completion-menu.meta.completion': 'bg:ansibrightblack ansibrightblue',
        'completion-menu.meta.completion.current': 'bg:ansiblue ansiwhite',
    }
)
"""Completion menu colors (ansi names so they follow the terminal theme)."""


def _escape_shell_path(name: str) -> str:
    """Escape spaces and shell special characters for CLI completion."""
    return (
        name.replace(' ', '\\ ')
        .replace('(', '\\(')
        .replace(')', '\\)')
        .replace('[', '\\[')
        .replace(']', '\\]')
        .replace("'", "\\'")
        .replace('"', '\\"')
        .replace('&', '\\&')
        .replace('$', '\\$')
    )


def _parse_completion_context(text_before_cursor: str) -> tuple[str, int, str]:  # noqa: PLR0911
    """Parse text before cursor into (cmd_name, arg_index, current_word).

    arg_index is 1-based index of the argument being typed:
    - 0 if cursor is on the command name itself
    - 1 for the first argument after command
    - 2 for the second argument after command, etc.
    """
    lstripped = text_before_cursor.lstrip()
    if not lstripped:
        return '', 0, ''

    ends_with_space = text_before_cursor[-1].isspace()
    try:
        tokens = shlex.split(text_before_cursor)
    except ValueError:
        tokens = text_before_cursor.split()

    if not tokens:
        return '', 0, ''

    cmd = tokens[0]
    if len(tokens) == 1:
        if text_before_cursor.rstrip() != text_before_cursor:
            return cmd, 1, ''
        return cmd, 0, tokens[0]

    raw_trailing_space = text_before_cursor[-1].isspace() and not (
        len(text_before_cursor) > 1 and text_before_cursor[-2] == '\\'
    )

    if raw_trailing_space:
        if ends_with_space:
            return cmd, 1, ''
        return cmd, 0, tokens[0]

    if ends_with_space:
        return cmd, len(tokens), ''

    return cmd, len(tokens) - 1, tokens[-1]


def _get_remote_completions(word: str) -> Iterator[Completion]:
    """Yield remote backend completions for `word`."""
    fragment = word.rpartition('/')[2]
    parent = word[: len(word) - len(fragment)]  # '' or ends with '/'
    try:
        entries = sorted(
            current_fs().scandir(parent or None, all=fragment.startswith('.')),
            key=lambda entry: entry.name,
        )
    except Exception:  # noqa: BLE001 - completion must never break the prompt
        return
    for entry in entries:
        if not entry.name.startswith(fragment):
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
        entries = sorted(target_dir.iterdir(), key=lambda p: p.name)
    except Exception:  # noqa: BLE001 - completion must never break prompt
        return

    show_hidden = fragment.startswith('.')
    for path in entries:
        name = path.name
        if not show_hidden and name.startswith('.'):
            continue
        if not name.startswith(fragment):
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
    not per-line ones: the start banner states them once and ``provider``
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


def _help() -> None:
    console.print('[bold blue]storix shell[/bold blue] - unix over any backend\n')
    console.print(
        '  [cyan]navigate[/cyan]  ls  pwd  cd  tree\n'
        '  [cyan]read[/cyan]      cat  stat  du  url\n'
        '  [cyan]write[/cyan]     touch  echo  mkdir\n'
        '  [cyan]remove[/cyan]    rm  rmdir\n'
        '  [cyan]move[/cyan]      mv  cp\n'
        '  [cyan]transfer[/cyan]  push  pull\n'
        '  [cyan]session[/cyan]   provider  provision  exists\n'
        '  [cyan]shell[/cyan]     help  clear  refresh  exit\n'
    )
    console.print('[dim]any command supports --help, e.g. `ls --help`[/dim]')


def _parse_input(line: str, aliases: dict[str, str]) -> list[str]:
    """Parse a prompt line into tokenized argv, expanding aliases if defined."""
    argv = shlex.split(line)
    return expand_alias(argv, aliases) if (argv and aliases) else argv


def start_shell(fs: Storix | None = None) -> None:
    """Run the interactive shell over ``fs`` (or the default session)."""
    if fs is not None:
        use_fs(fs)
    fs = current_fs()

    prefs = load_prefs()
    command = get_command(app)
    commands = (
        {name: sub.get_short_help_str(60) for name, sub in command.commands.items()}
        if isinstance(command, click.Group)
        else {}
    )
    alias_cmds = {name: f"alias: '{target}'" for name, target in prefs.alias.items()}
    session: PromptSession[str] = PromptSession(
        completer=_ShellCompleter({**commands, **alias_cmds, **_BUILTINS}),
        complete_while_typing=False,
        complete_in_thread=True,
        style=_MENU_STYLE,
    )

    console.print('[bold blue]storix shell[/bold blue]')
    console.print(f'connected to [green]{type(fs.base_backend).__name__}[/green]')
    summary = layer_summary(fs)
    if summary:
        tip = ' · type [cyan]refresh[/cyan] to clear' if cache_layer(fs) else ''
        console.print(f'[green]{summary}[/green]{tip}')
    console.print("type 'help' for commands, 'exit' to quit, tab to complete\n")

    while True:
        try:
            line = session.prompt(_prompt(current_fs())).strip()
        except (EOFError, KeyboardInterrupt):
            console.print('\n[yellow]bye[/yellow]')
            return

        if not line:
            continue
        try:
            argv = _parse_input(line, prefs.alias)
        except ValueError as exc:
            console.print(f'[red]parse error: {exc}[/red]')
            continue

        name = argv[0]
        if name in {'exit', 'quit'}:
            console.print('[yellow]bye[/yellow]')
            return
        if name == 'help':
            _help()
            continue
        if name == 'clear':
            console.clear()
            continue
        if name == 'refresh':
            layer = cache_layer(current_fs())
            if layer is None:
                console.print('[yellow]no cache layer active[/yellow]')
            else:
                layer.clear()
                console.print('[green]cache cleared[/green]')
            continue

        _dispatch(command, argv)


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
