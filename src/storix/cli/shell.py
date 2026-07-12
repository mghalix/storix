"""Interactive REPL for the storix CLI.

Reuses the Typer/Click parser from ``app`` - every command and flag works
identically to the one-shot CLI, so there is no second argument parser to
keep in sync. Only shell built-ins (exit/help/clear) are handled here.
"""

from __future__ import annotations

import shlex

from typing import TYPE_CHECKING

import click

from rich.console import Console
from typer.main import get_command

from . import app as cli


if TYPE_CHECKING:
    from storix import Storix


console = Console()
_MAX_CWD = 30


def _prompt(fs: Storix) -> str:
    cwd = str(fs.pwd())
    if len(cwd) > _MAX_CWD:
        cwd = '...' + cwd[-(_MAX_CWD - 3) :]
    return f'{cli.prompt_label(fs)} {cwd} $ '


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
        cli.use_fs(fs)
    fs = cli.current_fs()

    command = get_command(cli.app)

    console.print('[bold blue]storix shell[/bold blue]')
    console.print(f'connected to [green]{cli.prompt_label(fs)}[/green]')
    summary = cli.layer_summary(fs)
    if summary:
        tip = ' · type [cyan]refresh[/cyan] to clear' if cli.cache_layer(fs) else ''
        console.print(f'[green]{summary}[/green]{tip}')
    console.print("type 'help' for commands, 'exit' to quit\n")

    while True:
        try:
            line = console.input(_prompt(cli.current_fs())).strip()
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
            layer = cli.cache_layer(cli.current_fs())
            if layer is None:
                console.print('[yellow]no cache layer active[/yellow]')
            else:
                layer.clear()
                console.print('[green]cache cleared[/green]')
            continue

        _dispatch(command, argv)


def _dispatch(command: click.BaseCommand, argv: list[str]) -> None:
    """Feed one line to the shared Click parser, swallowing its exits."""
    try:
        command.main(argv, prog_name='', standalone_mode=False)
    except click.ClickException as exc:
        exc.show()
    except (click.exceptions.Abort, SystemExit):
        pass
    except Exception as exc:  # noqa: BLE001 - the REPL must survive any command
        console.print(f'[red]{exc}[/red]')
