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
from .render import console, entry_decor
from .state import (
    base_backend,
    cache_layer,
    current_fs,
    layer_summary,
    list_entries,
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


class _ShellCompleter(Completer):
    """Tab candidates: command names first, remote paths everywhere else.

    Commands complete with their one-line description; paths come from a
    single ``list_dir`` on the directory part of the word being completed
    (the session's cwd when there is none), so entries keep their kind and
    directories complete with a trailing slash, an icon, and color. An
    active cache layer makes repeat listings cheap. Hidden entries appear
    only when the typed fragment starts with a dot, like unix completion.
    """

    def __init__(self, commands: Mapping[str, str]) -> None:
        self._commands = dict(sorted(commands.items()))

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterator[Completion]:
        """Yield completions for the word before the cursor."""
        text = document.text_before_cursor
        word = document.get_word_before_cursor(WORD=True)
        if not text[: len(text) - len(word)].strip():  # first word: a command
            yield from (
                Completion(name, start_position=-len(word), display_meta=meta)
                for name, meta in self._commands.items()
                if name.startswith(word)
            )
            return
        fragment = word.rpartition('/')[2]
        parent = word[: len(word) - len(fragment)]  # '' or ends with '/'
        try:
            entries = list_entries(
                current_fs(), parent or None, all=fragment.startswith('.')
            )
        except Exception:  # noqa: BLE001 - completion must never break the prompt
            return
        for entry in entries:
            if not entry.name.startswith(fragment):
                continue
            icon = entry_decor(entry)[0]
            slash = '/' if entry.is_dir else ''
            label = f'{icon} {entry.name}{slash}' if icon else f'{entry.name}{slash}'
            yield Completion(
                f'{parent}{entry.name}{slash}',
                start_position=-len(word),
                display=label,
                style='fg:ansibrightblue bold' if entry.is_dir else '',
            )


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
        '  [cyan]transfer[/cyan]  upload  download\n'
        '  [cyan]session[/cyan]   provider  exists\n'
        '  [cyan]shell[/cyan]     help  clear  refresh  exit\n'
    )
    console.print('[dim]any command supports --help, e.g. `ls --help`[/dim]')


def start_shell(fs: Storix | None = None) -> None:
    """Run the interactive shell over ``fs`` (or the default session)."""
    if fs is not None:
        use_fs(fs)
    fs = current_fs()

    command = get_command(app)
    commands = (
        {name: sub.get_short_help_str(60) for name, sub in command.commands.items()}
        if isinstance(command, click.Group)
        else {}
    )
    session: PromptSession[str] = PromptSession(
        completer=_ShellCompleter({**commands, **_BUILTINS}),
        complete_while_typing=False,
        complete_in_thread=True,
        style=_MENU_STYLE,
    )

    console.print('[bold blue]storix shell[/bold blue]')
    console.print(f'connected to [green]{type(base_backend(fs)).__name__}[/green]')
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
            argv = shlex.split(line)
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
