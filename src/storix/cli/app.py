"""Storix CLI: unix-like commands over any storix backend.

The typer command surface only. Session state and stack access live in
``state``, presentation in ``render``, persistent preferences in
``config``, the REPL in ``shell``.
"""

from __future__ import annotations

import sys

from contextlib import contextmanager
from typing import TYPE_CHECKING, Annotated, NoReturn

import typer

from rich.columns import Columns
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TransferSpeedColumn,
)
from rich.table import Table
from rich.text import Text

from storix import ObservabilityLayer
from storix.errors import StorageError

from .config import load_prefs
from .render import (
    console,
    dir_state_of,
    entry_label,
    err,
    human_size,
)
from .state import (
    _fs,
    _session,
    apply_layers,
    build_base,
    build_session,
    current_fs,
    has_children,
    icons_enabled,
    layer_summary,
    list_entries,
    set_icons,
    use_fs,
)


if TYPE_CHECKING:
    from collections.abc import Iterator

    from storix import Storix
    from storix.models import Entry
    from storix.types import StorixPath

    from .render import DirState


__all__ = ['app', 'current_fs', 'main', 'use_fs']


app = typer.Typer(
    rich_markup_mode='rich',
    help='Storix - unix-like filesystem commands over any backend.',
    no_args_is_help=False,
    add_completion=False,
)


def _die(cmd: str, exc: Exception) -> NoReturn:
    err.print(f'[red]{cmd}: {exc}[/red]')
    raise typer.Exit(1) from exc


# --- listing / navigation ---


def _dir_state(fs: Storix, base: StorixPath, entry: Entry) -> DirState:
    """The folder glyph state for a flat-listing entry.

    A listing does not say whether a directory holds anything, so the
    honest default is the neutral 'closed' folder. When ``dir_contents``
    is on, look - one listing per subdirectory - so empty reads as empty.
    """
    if not entry.is_dir or not (icons_enabled() and load_prefs().dir_contents):
        return 'closed'
    return dir_state_of(populated=has_children(fs, base / entry.name))


@app.command()
def ls(
    path: Annotated[str | None, typer.Argument()] = None,
    *,
    long: Annotated[bool, typer.Option('-l', '--long')] = False,
    all_: Annotated[bool, typer.Option('-a', '--all')] = False,
    time_sort: Annotated[
        bool,
        typer.Option('-t', '--time', help='sort by modification time, newest first'),
    ] = False,
    reverse: Annotated[bool, typer.Option('-r', '--reverse')] = False,
) -> None:
    """List directory contents (hidden entries need -a)."""
    fs = _fs()
    base = fs.resolve(path)
    try:
        entries = list_entries(fs, path, all=all_)
        if time_sort and len(entries) > 1:
            # listings carry no mtime, so -t costs one stat per entry
            mtimes = {e.name: fs.backend.stat(base / e.name).modified for e in entries}
            entries.sort(key=lambda e: mtimes[e.name], reverse=True)
    except StorageError as exc:
        _die('ls', exc)
    if reverse:
        entries.reverse()

    def label(entry) -> Text:  # noqa: ANN001 - Entry, kept local to ls
        return entry_label(entry, dir_state=_dir_state(fs, base, entry))

    if not long:
        cells = [label(entry) for entry in entries]
        console.print(Columns(cells, padding=(0, 2))) if cells else None
        return

    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column()  # kind
    table.add_column(justify='right')  # size
    table.add_column()  # icon + name
    for entry in entries:
        if entry.is_dir:
            size_text = Text('-', style='dim')
        else:
            size = entry.size
            if size is None:
                size = fs.stat(base / entry.name).size
            size_text = Text(human_size(size), style='green')
        kind = Text('d' if entry.is_dir else '-', style='dim')
        table.add_row(kind, size_text, label(entry))
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
def tree(
    path: Annotated[str | None, typer.Argument()] = None,
    *,
    all_: Annotated[bool, typer.Option('-a', '--all')] = False,
) -> None:
    """Print a directory tree (unix tree style, with the closing count)."""
    fs = _fs()
    dirs, files = 1, 0  # unix tree counts the root directory

    def children_of(target: str) -> list[Entry]:
        try:
            return list_entries(fs, target, all=all_)
        except StorageError as exc:
            _die('tree', exc)

    def walk(children: list[Entry], target: str, prefix: str = '') -> None:
        nonlocal dirs, files
        for i, child in enumerate(children):
            last = i == len(children) - 1
            branch = '└── ' if last else '├── '
            if child.is_dir:
                dirs += 1
                inner = f'{target}/{child.name}'
                sub = children_of(inner)
                label = entry_label(
                    child, slash=False, dir_state='full' if sub else 'empty'
                )
                console.print(Text(f'{prefix}{branch}') + label)
                walk(sub, inner, prefix + ('    ' if last else '│   '))
            else:
                files += 1
                console.print(Text(f'{prefix}{branch}') + entry_label(child))

    root = str(fs.resolve(path))
    console.print(f'[bold blue]{root}[/bold blue]')
    walk(children_of(root), root)
    d = 'directory' if dirs == 1 else 'directories'
    f = 'file' if files == 1 else 'files'
    console.print(f'\n{dirs} {d}, {files} {f}')


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

    text = data.decode(errors='replace')
    # exact bytes when piped; a trailing newline in a terminal so the
    # shell prompt (and one-shot output) starts on a fresh line
    if text and not text.endswith('\n') and sys.stdout.isatty():
        text += '\n'
    # no markup/highlight: file contents are data, not rich markup
    console.print(text, end='', markup=False, highlight=False)


@app.command()
def stat(path: Annotated[str, typer.Argument()]) -> None:
    """Show a path's properties."""
    try:
        console.print(str(_fs().stat(path)))
    except StorageError as exc:
        _die('stat', exc)


@app.command()
def du(
    path: Annotated[str | None, typer.Argument()] = None,
    *,
    human: Annotated[
        bool, typer.Option('-h', '--human', help='human-readable size (e.g. 165M)')
    ] = False,
) -> None:
    """Total size in bytes of a tree (apparent content bytes)."""
    fs = _fs()
    try:
        total = fs.du(path)
    except StorageError as exc:
        _die('du', exc)
    shown = path if path is not None else str(fs.resolve(path))
    console.print(f'{human_size(total) if human else total}\t{shown}')


@app.command()
def url(
    path: Annotated[str, typer.Argument()],
    *,
    data: Annotated[
        bool, typer.Option('--data', help='inline base64 data: URL')
    ] = False,
    expire: Annotated[
        int | None,
        typer.Option('--expire', help='seconds until the presigned URL expires'),
    ] = None,
) -> None:
    """Print a shareable URL (presigned by default; --data for a data: URL)."""
    fs = _fs()
    try:
        console.print(fs.data_url(path) if data else fs.url(path, expires_in=expire))
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


@contextmanager
def _transfer_progress(fs: Storix, label: str, total: int) -> Iterator[Storix]:
    """Session emitting into a live bar; sx owns ``total`` (ADR 0019).

    Wraps ``fs`` in an outermost ``ObservabilityLayer`` whose sink moves a
    rich progress bar; the percentage is ``transferred`` over the total the
    caller already owns. The wrapped session starts at home, so callers
    must pass absolute paths.

    Args:
        fs: The session to wrap.
        label: Bar description, typically the file's basename.
        total: The transfer's total size in bytes.

    Yields:
        The wrapped session; use it for the one transfer.
    """
    with Progress(
        TextColumn('[progress.description]{task.description}'),
        BarColumn(),
        TaskProgressColumn(),
        DownloadColumn(binary_units=True),
        TransferSpeedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(label, total=total)
        yield fs.with_layer(
            ObservabilityLayer,
            sink=lambda event: progress.update(task, completed=event.transferred),
        )


@app.command()
def download(
    remote: Annotated[str, typer.Argument()],
    local: Annotated[str | None, typer.Argument()] = None,
) -> None:
    """Copy a file from the storix backend to the local disk."""
    from pathlib import Path

    fs = _fs()
    src = fs.resolve(remote)
    try:
        total = fs.stat(src).size
    except StorageError as exc:
        _die('download', exc)
    dst = Path(local) if local else Path(src.name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        with (
            _transfer_progress(fs, src.name, total) as obs,
            dst.open('wb') as out,
        ):
            for chunk in obs.stream(src):
                out.write(chunk)
    except StorageError as exc:
        _die('download', exc)
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
    dst = fs.resolve(remote) if remote else fs.pwd() / src.name
    try:
        with (
            _transfer_progress(fs, src.name, src.stat().st_size) as obs,
            src.open('rb') as data,
        ):
            content_type = None
            if fs.backend.capabilities.content_type:
                from storix.utils import detect_mimetype

                # extension first, libmagic sniff of the head as fallback
                content_type = detect_mimetype(buf=data.read(4096), path=src.name)
                data.seek(0)
            obs.echo(data, dst, content_type=content_type)
    except StorageError as exc:
        _die('upload', exc)
    console.print(f'{local} -> {dst}')


# --- session ---


@app.command()
def provider() -> None:
    """Show the active backend and where it is anchored."""
    fs = _fs()
    console.print(f'[green]backend:[/green] {type(fs.base_backend).__name__}')
    console.print(f'[green]cwd:[/green]     {fs.pwd()}')
    console.print(f'[green]home:[/green]    {fs.home}')
    console.print(f'[green]root uri:[/green] {fs.locate("/")}')
    summary = layer_summary(fs)
    if summary:
        console.print(f'[green]layers:[/green]  {summary}')


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
        str | None,
        typer.Option('-p', '--provider', help='local | memory | azure | ...'),
    ] = None,
    cache: Annotated[
        bool, typer.Option('--cache', help='read-through cache: du/ls/stat/cat')
    ] = False,
    cache_ttl: Annotated[
        float | None,
        typer.Option('--cache-ttl', help='seconds before cached entries expire'),
    ] = None,
    sandbox: Annotated[
        str | None, typer.Option('--sandbox', help='jail the session under this path')
    ] = None,
    icons: Annotated[
        bool | None,
        typer.Option(
            '--icons/--no-icons',
            help='Nerd Font icons in listings (default: persistent prefs)',
        ),
    ] = None,
    interactive: Annotated[bool, typer.Option('-i', '--interactive')] = False,
) -> None:
    """Set up the session; launch the shell when no command is given."""
    if icons is not None:
        set_icons(icons)
    # rebuild on an explicit --provider or any layer flag, else keep the
    # persistent session (so cwd survives across shell commands); layer
    # flags replace the configured [[cli.layers]] stack for the invocation
    if provider_ is not None or cache or sandbox is not None:
        if cache or sandbox is not None:
            base = build_base(provider_)
            _session.fs = apply_layers(
                base, cache=cache, cache_ttl=cache_ttl, sandbox=sandbox
            )
        else:
            _session.fs = build_session(provider_)

    if ctx.invoked_subcommand is None or interactive:
        from .shell import start_shell

        start_shell(_fs())


def main() -> None:
    """Console-script entry point (`sx`)."""
    app()
