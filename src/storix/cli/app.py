"""Storix CLI: unix-like commands over any storix backend."""

from __future__ import annotations

import sys

from typing import TYPE_CHECKING, Annotated, NoReturn

import typer

from rich.console import Console
from rich.table import Table

from storix import get_storage
from storix.errors import StorageError


if TYPE_CHECKING:
    from storix import Storix


app = typer.Typer(
    rich_markup_mode='rich',
    help='Storix - unix-like filesystem commands over any backend.',
    no_args_is_help=False,
    add_completion=False,
)
console = Console()
err = Console(stderr=True)


class _Session:
    """Holds the one live filesystem so state (cwd) persists across commands."""

    fs: Storix | None = None


_session = _Session()


def _fs() -> Storix:
    if _session.fs is None:
        _session.fs = get_storage()
    return _session.fs


def current_fs() -> Storix:
    """The active session filesystem (public entry point for the shell)."""
    return _fs()


def use_fs(fs: Storix) -> None:
    """Point the session at ``fs`` (public entry point for the shell)."""
    _session.fs = fs


def _die(cmd: str, exc: Exception) -> NoReturn:
    err.print(f'[red]{cmd}: {exc}[/red]')
    raise typer.Exit(1) from exc


# --- listing / navigation ---


@app.command()
def ls(
    path: Annotated[str | None, typer.Argument()] = None,
    *,
    long: Annotated[bool, typer.Option('-l', '--long')] = False,
    all_: Annotated[bool, typer.Option('-a', '--all')] = False,
) -> None:
    """List directory contents (hidden entries need -a)."""
    fs = _fs()
    try:
        entries = fs.ls(path, all=all_, abs=True)
    except StorageError as exc:
        _die('ls', exc)

    if not long:
        console.print(*(p.name for p in entries)) if entries else None
        return

    table = Table(show_header=False, box=None, pad_edge=False)
    for entry in entries:
        props = fs.stat(entry)
        is_dir = props.kind == 'directory'
        name = f'[bold blue]{entry.name}/[/bold blue]' if is_dir else entry.name
        table.add_row('d' if is_dir else '-', str(props.size), name)
    console.print(table)


@app.command()
def pwd() -> None:
    """Print the working directory."""
    console.print(str(_fs().pwd()))


@app.command()
def cd(path: Annotated[str | None, typer.Argument()] = None) -> None:
    """Change directory (no argument: home)."""
    try:
        _fs().cd(path)
    except StorageError as exc:
        _die('cd', exc)


@app.command()
def tree(path: Annotated[str | None, typer.Argument()] = None) -> None:
    """Print a directory tree."""
    fs = _fs()

    def walk(target: str, prefix: str = '') -> None:
        try:
            children = fs.ls(target, abs=True)
        except StorageError as exc:
            _die('tree', exc)
        for i, child in enumerate(sorted(children, key=lambda p: p.name)):
            last = i == len(children) - 1
            branch = '└── ' if last else '├── '
            is_dir = fs.isdir(child)
            label = f'[bold blue]{child.name}[/bold blue]' if is_dir else child.name
            console.print(f'{prefix}{branch}{label}')
            if is_dir:
                walk(str(child), prefix + ('    ' if last else '│   '))

    root = str(fs.resolve(path))
    console.print(f'[bold blue]{root}[/bold blue]')
    walk(root)


# --- creating / writing ---


@app.command()
def mkdir(
    directories: Annotated[list[str], typer.Argument()],
    *,
    parents: Annotated[bool, typer.Option('-p', '--parents')] = False,
) -> None:
    """Create directories (-p for parents / no error if existing)."""
    try:
        _fs().mkdir(*directories, parents=parents)
    except StorageError as exc:
        _die('mkdir', exc)


@app.command()
def touch(files: Annotated[list[str], typer.Argument()]) -> None:
    """Create files (or refresh their mtime)."""
    try:
        _fs().touch(*files)
    except StorageError as exc:
        _die('touch', exc)


@app.command()
def echo(
    text: Annotated[str, typer.Argument()],
    file: Annotated[str | None, typer.Option('-f', '--file')] = None,
    *,
    append: Annotated[bool, typer.Option('-a', '--append')] = False,
) -> None:
    """Print text, or write it to a file with -f."""
    if file is None:
        console.print(text)
        return
    try:
        _fs().echo(text + '\n', file, mode='a' if append else 'w')
    except StorageError as exc:
        _die('echo', exc)


# --- reading ---


@app.command()
def cat(
    files: Annotated[list[str], typer.Argument()],
    *,
    binary: Annotated[bool, typer.Option('-b', '--binary')] = False,
) -> None:
    """Concatenate and print files."""
    fs = _fs()
    try:
        data = fs.cat(*files)
    except StorageError as exc:
        _die('cat', exc)

    if binary:
        sys.stdout.buffer.write(data)
        return
    if b'\x00' in data:
        err.print(f'[yellow]cat: binary file ({len(data)} bytes); use -b[/yellow]')
        return
    console.print(data.decode(errors='replace'), end='')


@app.command()
def stat(path: Annotated[str, typer.Argument()]) -> None:
    """Show a path's properties."""
    try:
        console.print(str(_fs().stat(path)))
    except StorageError as exc:
        _die('stat', exc)


@app.command()
def du(path: Annotated[str | None, typer.Argument()] = None) -> None:
    """Total size in bytes of a tree (apparent content bytes)."""
    fs = _fs()
    try:
        console.print(f'{fs.du(path)}\t{fs.resolve(path)}')
    except StorageError as exc:
        _die('du', exc)


@app.command()
def url(
    path: Annotated[str, typer.Argument()],
    *,
    data: Annotated[
        bool, typer.Option('--data', help='inline base64 data: URL')
    ] = False,
) -> None:
    """Print a shareable URL (presigned by default; --data for a data: URL)."""
    fs = _fs()
    try:
        console.print(fs.data_url(path) if data else fs.url(path))
    except StorageError as exc:
        _die('url', exc)


# --- removing ---


@app.command()
def rm(
    files: Annotated[list[str], typer.Argument()],
    *,
    recursive: Annotated[bool, typer.Option('-r', '-R', '--recursive')] = False,
    force: Annotated[bool, typer.Option('-f', '--force')] = False,
) -> None:
    """Remove files; -r for directories/trees."""
    fs = _fs()
    try:
        fs.rm(*files, recursive=recursive)
    except StorageError as exc:
        if not force:
            _die('rm', exc)


@app.command()
def rmdir(directories: Annotated[list[str], typer.Argument()]) -> None:
    """Remove empty directories (use rm -r for non-empty)."""
    try:
        _fs().rmdir(*directories)
    except StorageError as exc:
        _die('rmdir', exc)


# --- moving / copying ---


@app.command()
def cp(
    paths: Annotated[list[str], typer.Argument()],
    *,
    recursive: Annotated[bool, typer.Option('-r', '-R', '--recursive')] = False,
) -> None:
    """Copy; the last argument is the destination (-r for directories)."""
    try:
        _fs().cp(*paths, recursive=recursive)
    except (StorageError, TypeError) as exc:
        _die('cp', exc)


@app.command()
def mv(paths: Annotated[list[str], typer.Argument()]) -> None:
    """Move/rename; the last argument is the destination."""
    try:
        _fs().mv(*paths)
    except (StorageError, TypeError) as exc:
        _die('mv', exc)


# --- queries ---


@app.command()
def exists(paths: Annotated[list[str], typer.Argument()]) -> None:
    """Exit 0 only if every path exists."""
    fs = _fs()
    if not all(fs.exists(p) for p in paths):
        raise typer.Exit(1)


# --- local <-> remote transfer ---


@app.command()
def download(
    remote: Annotated[str, typer.Argument()],
    local: Annotated[str | None, typer.Argument()] = None,
) -> None:
    """Copy a file from the storix backend to the local disk."""
    from pathlib import Path

    fs = _fs()
    try:
        data = fs.cat(remote)
    except StorageError as exc:
        _die('download', exc)
    dst = Path(local) if local else Path(fs.resolve(remote).name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    console.print(f'{remote} -> {dst}')


@app.command()
def upload(
    local: Annotated[str, typer.Argument()],
    remote: Annotated[str | None, typer.Argument()] = None,
) -> None:
    """Copy a file from the local disk to the storix backend."""
    from pathlib import Path

    src = Path(local)
    if not src.is_file():
        _die('upload', FileNotFoundError(local))
    fs = _fs()
    dst = remote or str(fs.pwd() / src.name)
    try:
        fs.echo(src.read_bytes(), dst)
    except StorageError as exc:
        _die('upload', exc)
    console.print(f'{local} -> {dst}')


# --- session ---


@app.command()
def provider() -> None:
    """Show the active backend and where it is anchored."""
    fs = _fs()
    console.print(f'[green]backend:[/green] {type(fs.backend).__name__}')
    console.print(f'[green]cwd:[/green]     {fs.pwd()}')
    console.print(f'[green]home:[/green]    {fs.home}')
    console.print(f'[green]root uri:[/green] {fs.locate("/")}')


@app.command()
def shell() -> None:
    """Start the interactive shell."""
    from .shell import start_shell

    start_shell(_fs())


@app.callback(invoke_without_command=True)
def _main(
    ctx: typer.Context,
    *,
    provider_: Annotated[
        str | None, typer.Option('-p', '--provider', help='local | azure | ...')
    ] = None,
    interactive: Annotated[bool, typer.Option('-i', '--interactive')] = False,
) -> None:
    """Set up the session; launch the shell when no command is given."""
    # rebuild only on explicit --provider, else keep the persistent session
    # (so cwd survives across shell commands)
    if provider_ is not None:
        _session.fs = get_storage(provider_)

    if ctx.invoked_subcommand is None or interactive:
        from .shell import start_shell

        start_shell(_fs())


def main() -> None:
    """Console-script entry point (`sx`)."""
    app()
