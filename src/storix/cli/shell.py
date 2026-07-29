"""Interactive REPL for the storix CLI.

Reuses the Typer/Click parser from ``app`` - every command and flag works
identically to the one-shot CLI, so there is no second argument parser to
keep in sync. Only shell built-ins (exit/help/clear) are handled here.
"""

from __future__ import annotations

import contextlib
import io
import shlex

from typing import TYPE_CHECKING

import click

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.filters import completion_is_selected
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from typer.main import get_command

from storix.config import user_config_path
from storix.errors import StorageError

from .app import app
from .config import expand_alias, load_prefs
from .icons import lookup_entry_decor
from .render import console, entry_decor
from .state import (
    cache_layer,
    current_fs,
    layer_summary,
    selection,
    use_fs,
)


if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from prompt_toolkit.completion import CompleteEvent
    from prompt_toolkit.document import Document
    from prompt_toolkit.key_binding.key_processor import KeyPressEvent

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


def _key_bindings() -> KeyBindings:
    """Make Enter accept a highlighted completion instead of submitting.

    prompt_toolkit's default runs the line the moment you press Enter on a
    menu entry, so tab-completing a path and pressing Enter executes a
    half-written command. Every shell instead puts the completion on the
    line and waits, which is what lets you complete a second argument.
    """
    bindings = KeyBindings()

    @bindings.add('enter', filter=completion_is_selected)
    def _accept(event: KeyPressEvent) -> None:  # pyright: ignore[reportUnusedFunction]
        event.current_buffer.complete_state = None

    return bindings


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
        entries = sorted(target_dir.iterdir(), key=lambda p: p.name)
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
    """
    collected = io.BytesIO()
    text = io.TextIOWrapper(collected, encoding='utf-8', newline='')
    with contextlib.redirect_stdout(text):
        _dispatch(command, argv)
        text.flush()
    return collected.getvalue()


def _parse_input(line: str, aliases: dict[str, str]) -> list[str]:
    """Parse a prompt line into tokenized argv, expanding aliases if defined."""
    argv = shlex.split(line)
    return expand_alias(argv, aliases) if (argv and aliases) else argv


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
        key_bindings=_key_bindings(),
        complete_while_typing=False,
        complete_in_thread=True,
        style=_MENU_STYLE,
    )

    _banner(fs)

    # two Ctrl+C in a row leave; a single one never does. The first of the
    # pair discards whatever was being typed, which is what makes Ctrl+C safe
    # to reach for mid-command - and it still counts as the first press, so
    # clearing a line then pressing again exits rather than asking a third
    # time.
    warned = False

    while True:
        try:
            line = session.prompt(_prompt(current_fs())).strip()
        except KeyboardInterrupt:
            if warned:
                console.print('[yellow]bye[/yellow]')
                return
            warned = True
            console.print('[dim]press Ctrl+C again to exit[/dim]')
            continue
        except EOFError:
            # end of input, not an interrupt: one press, like any shell
            console.print('\n[yellow]bye[/yellow]')
            return

        warned = False
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
