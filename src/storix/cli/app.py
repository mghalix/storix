"""Storix CLI: unix-like commands over any storix backend.

The typer command surface only. Session state and stack access live in
``state``, presentation in ``render``, persistent preferences in
``config``, the REPL in ``shell``.
"""

from __future__ import annotations

import sys

from collections import defaultdict
from contextlib import contextmanager, suppress
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

from storix import ObservabilityLayer, TransferEvent
from storix.enums import PathKind
from storix.errors import StorageError

from .config import load_prefs
from .render import (
    console,
    dir_state_of,
    entry_decor,
    entry_label,
    err,
    human_size,
)
from .state import (
    _fs,  # pyright: ignore[reportPrivateUsage]
    _session,  # pyright: ignore[reportPrivateUsage]
    apply_layers,
    build_base,
    build_session,
    current_fs,
    empty_all,
    icons_enabled,
    layer_summary,
    set_icons,
    stat_all,
    use_fs,
)


if TYPE_CHECKING:
    from collections.abc import Generator

    from storix import Storix
    from storix.models import DirEntry, RawStat
    from storix.types import StorixPath


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


def _count_label(count: int, singular: str, plural: str) -> str:
    """Choose a count-sensitive label.

    Args:
        count: Quantity the label describes.
        singular: Label used for exactly one item.
        plural: Label used for every other count.
    """
    return singular if count == 1 else plural


# --- listing / navigation ---


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
    """List directory contents (hidden entries need -a).

    The per-entry backend lookups a listing does not carry for free -
    directory emptiness (the folder glyph), mtime (``-t``), a missing file
    size (``-l``) - are batched concurrently (``state.empty_all`` /
    ``stat_all``), so a directory of N entries on a cloud backend costs one
    round trip's worth of latency, not N.
    """
    fs = _fs()
    base = fs.resolve(path)
    try:
        entries = sorted(fs.scandir(path, all=all_), key=lambda e: e.name)
    except StorageError as exc:
        _die('ls', exc)

    show_empty = icons_enabled() and load_prefs().dir_contents
    empty: dict[str, bool | None] = {}
    if show_empty:
        dir_names = [e.name for e in entries if e.is_dir]
        empty = dict(zip(dir_names, empty_all(fs, base, dir_names), strict=True))

    entry_stats: dict[str, RawStat] = {}

    if (time_sort and len(entries) > 1) or long:
        fetched_stats = stat_all(fs, [base / e.name for e in entries])
        entry_stats = {e.name: s for e, s in zip(entries, fetched_stats, strict=True)}

    if time_sort and len(entries) > 1:
        entries.sort(key=lambda e: entry_stats[e.name].modified, reverse=True)
    if reverse:
        entries.reverse()

    def label(entry: DirEntry) -> Text:
        if entry.is_dir and show_empty:
            is_empty = empty.get(entry.name)
            populated = None if is_empty is None else not is_empty
            state = dir_state_of(populated=populated)
        else:
            state = 'closed'
        return entry_label(entry, dir_state=state)

    if not long:
        cells = [label(entry) for entry in entries]
        console.print(Columns(cells, padding=(0, 2))) if cells else None
        return

    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column()  # kind ('d' or '-')
    table.add_column(justify='right')  # size
    table.add_column(style='dim')  # date & time
    table.add_column()  # icon + name
    for entry in entries:
        s = entry_stats[entry.name]
        kind = Text('d' if entry.is_dir else '-', style='dim')
        if entry.is_dir:
            size_text = Text('-', style='dim')
        else:
            size_text = Text(human_size(s.size), style='green')
        mtime_text = Text(s.modified.strftime('%d %b %H:%M'), style='dim')
        table.add_row(kind, size_text, mtime_text, label(entry))
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


def _sorted_entries(fs: Storix, entries: list[DirEntry], sort: str) -> list[DirEntry]:
    """Order a directory's entries for ``tree`` by the chosen key.

    ``name`` sorts alphabetically; ``time`` newest first; ``size`` largest
    first, with directories (no meaningful size) sinking to the bottom.
    ``time`` and ``size`` need a stat per entry the listing did not carry,
    so those are batched concurrently (``stat_all``), one round trip's
    latency for the level rather than one per entry.
    """
    if sort == 'time':
        stats = stat_all(fs, [e.path for e in entries])
        mtime = {e.name: s.modified for e, s in zip(entries, stats, strict=True)}
        return sorted(entries, key=lambda e: mtime[e.name], reverse=True)
    if sort == 'size':
        missing = [e.path for e in entries if not e.is_dir and e.size is None]
        extra = dict(zip(missing, (s.size for s in stat_all(fs, missing)), strict=True))

        def size_of(entry: DirEntry) -> int:
            if entry.is_dir:
                return -1
            return entry.size if entry.size is not None else extra[entry.path]

        return sorted(entries, key=size_of, reverse=True)
    return sorted(entries, key=lambda e: e.name)


@app.command()
def tree(
    path: Annotated[str | None, typer.Argument()] = None,
    *,
    all_: Annotated[bool, typer.Option('-a', '--all')] = False,
    level: Annotated[
        int | None,
        typer.Option('-L', '--level', help='descend at most this many levels'),
    ] = None,
    long: Annotated[
        bool,
        typer.Option('-l', '--long', help='show size and kind columns (eza-style)'),
    ] = False,
    sort: Annotated[
        str, typer.Option('--sort', help='order siblings by name | time | size')
    ] = 'name',
) -> None:
    """Print a directory tree (unix tree style, with the closing count).

    -L caps the depth, -l adds eza-style size and kind columns, --sort
    orders siblings by name (default), time, or size.
    """
    fs = _fs()
    if sort not in {'name', 'time', 'size'}:
        _die('tree', ValueError(f'sort must be name, time or size, got {sort!r}'))
    dirs: int = 1  # unix tree counts the root directory
    files: int = 0

    def children_of(target: str) -> list[DirEntry]:
        try:
            return _sorted_entries(fs, list(fs.scandir(target, all=all_)), sort)
        except StorageError as exc:
            _die('tree', exc)

    def columns(entry: DirEntry) -> Text:
        """The eza-style 'kind size' prefix for -l, else nothing.

        Built by appending styled spans onto a base-less ``Text``: a base
        style would propagate through the ``+`` concatenation and dim the
        branch lines and entry names too.
        """
        prefix = Text()
        if not long:
            return prefix
        prefix.append('d ' if entry.is_dir else '- ', style='dim')
        if entry.is_dir:
            prefix.append(f'{"-":>7}  ', style='dim')
        else:
            size = entry.size if entry.size is not None else fs.stat(entry.path).size
            prefix.append(f'{human_size(size):>7}  ', style='green')
        return prefix

    def walk(children: list[DirEntry], target: str, prefix: str, depth: int) -> None:
        nonlocal dirs, files
        for i, child in enumerate(children):
            last = i == len(children) - 1
            branch = '└── ' if last else '├── '
            if child.is_dir:
                dirs += 1
                inner = f'{target}/{child.name}'
                expand = level is None or depth < level
                sub = children_of(inner) if expand else []
                # only claim empty/full when we actually looked inside
                state = 'closed' if not expand else dir_state_of(populated=bool(sub))
                label = entry_label(child, slash=False, dir_state=state)
                console.print(columns(child) + Text(f'{prefix}{branch}') + label)
                if expand:
                    walk(sub, inner, prefix + ('    ' if last else '│   '), depth + 1)
            else:
                files += 1
                console.print(
                    columns(child) + Text(f'{prefix}{branch}') + entry_label(child)
                )

    root = str(fs.resolve(path))
    console.print(f'[bold blue]{root}[/bold blue]')
    walk(children_of(root), root, '', 1)
    d = _count_label(dirs, 'directory', 'directories')
    f = _count_label(files, 'file', 'files')
    console.print(f'\n{dirs} {d}, {files} {f}')


@app.command()
def find(
    path: Annotated[str | None, typer.Argument()] = None,
    *,
    name: Annotated[
        str | None,
        typer.Option('--name', help='glob matched against the basename (e.g. "*.py")'),
    ] = None,
    type_: Annotated[
        str | None,
        typer.Option('--type', help='restrict to f (files) or d (directories)'),
    ] = None,
    all_: Annotated[
        bool, typer.Option('-a', '--all', help='include hidden entries')
    ] = False,
) -> None:
    """Recursively find entries by name glob and/or type (unix find)."""
    fs = _fs()
    kind = {'f': PathKind.FILE, 'd': PathKind.DIRECTORY}.get(type_) if type_ else None
    if type_ is not None and kind is None:
        _die('find', ValueError(f"type must be 'f' or 'd', got {type_!r}"))
    try:
        entries = list(fs.find(path, name=name, kind=kind, all=all_))
    except StorageError as exc:
        _die('find', exc)
    for entry in entries:
        icon, style = entry_decor(entry)
        text = f'{icon} {entry.path}' if icon else str(entry.path)
        console.print(Text(text, style=style))


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
    summary: Annotated[
        bool, typer.Option('-s', '--summary', help='one grand total only (du -s)')
    ] = False,
    all_: Annotated[
        bool, typer.Option('-a', '--all', help='include files, not just directories')
    ] = False,
    max_depth: Annotated[
        int | None,
        typer.Option('-d', '--max-depth', help='report entries at most this deep'),
    ] = None,
    human: Annotated[
        bool, typer.Option('-h', '--human', help='human-readable size (e.g. 165M)')
    ] = False,
) -> None:
    """Disk usage: a cumulative size per directory, ending with the total.

    Bottom-up like unix du (apparent content bytes). -s for the grand
    total only, -a to include files, -d to cap the reported depth.
    """
    fs = _fs()
    target = fs.resolve(path)
    shown = path if path is not None else str(target)

    def emit(size: int, entry_path: StorixPath) -> None:
        if entry_path == target:
            label = shown
        else:
            label = f'{shown.rstrip("/")}/{entry_path.relative_to(target).as_posix()}'
        console.print(f'{human_size(size) if human else size}\t{label}')

    try:
        if summary or fs.isfile(target):
            emit(fs.du(target), target)
            return
        # one post-order walk: children accumulate into their parent before
        # the parent is emitted, so every subtree is summed exactly once.
        sizes: dict[StorixPath, int] = defaultdict(int)
        for entry in fs.walk(target, all=True, top_down=False):
            if entry.is_dir:
                size = sizes[entry.path]
            elif entry.size is not None:
                size = entry.size
            else:
                size = fs.stat(entry.path).size
            sizes[entry.path.parent] += size
            depth = len(entry.path.relative_to(target).parts)
            if (entry.is_dir or all_) and (max_depth is None or depth <= max_depth):
                emit(size, entry.path)
        emit(sizes[target], target)
    except StorageError as exc:
        _die('du', exc)


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
def _transfer_progress(fs: Storix, label: str, total: int) -> Generator[Storix]:
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

        overall_bytes = 0
        last_file_bytes = 0

        def on_event(event: TransferEvent) -> None:
            nonlocal overall_bytes, last_file_bytes
            if event.transferred < last_file_bytes:
                last_file_bytes = 0
            delta = event.transferred - last_file_bytes
            last_file_bytes = event.transferred
            overall_bytes += delta
            progress.update(task, completed=overall_bytes)

        yield fs.with_layer(
            ObservabilityLayer,
            sink=on_event,
        )


@app.command()
def pull(
    remote: Annotated[
        str, typer.Argument(help='Remote source file or directory path on backend')
    ],
    local: Annotated[
        str | None, typer.Argument(help='Local destination path on host machine')
    ] = None,
) -> None:
    """Copy a file or directory from the storix backend to the local disk."""
    from pathlib import Path

    fs = _fs()
    src = fs.resolve(remote)
    try:
        st = fs.stat(src)
    except StorageError as exc:
        _die('pull', exc)

    if st.kind is PathKind.DIRECTORY:
        dst = Path(local).expanduser() if local else Path(src.name)
        remote_files = [e for e in fs.walk(src, all=True) if not e.is_dir]
        stats = stat_all(fs, [e.path for e in remote_files])
        total_bytes = sum(s.size for s in stats)
        try:
            with _transfer_progress(fs, src.name, total_bytes) as obs:
                for entry in remote_files:
                    rel = entry.path.relative_to(src)
                    out_path = dst / rel
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    with out_path.open('wb') as out:
                        for chunk in obs.stream(entry.path):
                            out.write(chunk)
        except StorageError as exc:
            _die('pull', exc)
        console.print(f'{remote} -> {dst} ({len(remote_files)} files)')
        return

    dst = Path(local).expanduser() if local else Path(src.name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        with (
            _transfer_progress(fs, src.name, st.size) as obs,
            dst.open('wb') as out,
        ):
            for chunk in obs.stream(src):
                out.write(chunk)
    except StorageError as exc:
        _die('pull', exc)
    console.print(f'{remote} -> {dst}')


@app.command()
def push(
    local: Annotated[
        str, typer.Argument(help='Local source file or directory path on host machine')
    ],
    remote: Annotated[
        str | None, typer.Argument(help='Remote destination path on backend')
    ] = None,
) -> None:
    """Copy a file or directory from the local disk to the storix backend."""
    from pathlib import Path

    from storix.utils import detect_mimetype

    src = Path(local).expanduser()
    if not src.exists():
        _die('push', FileNotFoundError(local))

    fs = _fs()

    if src.is_dir():
        dst = fs.resolve(remote) if remote else fs.pwd() / src.name
        with suppress(StorageError):
            fs.mkdir(dst, parents=True)
        files = [f for f in src.rglob('*') if f.is_file()]
        total_bytes = sum(f.stat().st_size for f in files)
        try:
            with _transfer_progress(fs, src.name, total_bytes) as obs:
                for file_path in files:
                    rel_path = file_path.relative_to(src)
                    remote_file = dst / rel_path
                    with suppress(StorageError):
                        fs.mkdir(remote_file.parent, parents=True)
                    with file_path.open('rb') as data:
                        content_type = None
                        if fs.backend.capabilities.content_type:
                            content_type = detect_mimetype(
                                buf=data.read(4096), path=file_path.name
                            )
                            data.seek(0)
                        obs.echo(data, remote_file, content_type=content_type)
        except StorageError as exc:
            _die('push', exc)
        console.print(f'{local} -> {dst} ({len(files)} files)')
        return

    dst = fs.resolve(remote) if remote else fs.pwd() / src.name
    try:
        with (
            _transfer_progress(fs, src.name, src.stat().st_size) as obs,
            src.open('rb') as data,
        ):
            content_type = None
            if fs.backend.capabilities.content_type:
                content_type = detect_mimetype(buf=data.read(4096), path=src.name)
                data.seek(0)
            obs.echo(data, dst, content_type=content_type)
    except StorageError as exc:
        _die('push', exc)
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
def _main(  # pyright: ignore[reportUnusedFunction]
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
    from .config import expand_alias, load_prefs

    prefs = load_prefs()
    if prefs.alias and len(sys.argv) > 1:
        sys.argv = [sys.argv[0], *expand_alias(sys.argv[1:], prefs.alias)]
    app()
