"""Storix CLI: unix-like commands over any storix backend.

The typer command surface only. Session state and stack access live in
``state``, presentation in ``render``, persistent preferences in
``config``, the REPL in ``shell``.
"""

from __future__ import annotations

import ctypes
import os
import signal
import sys
import tempfile
import threading

from collections import defaultdict
from contextlib import contextmanager, suppress
from enum import auto
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Final, NoReturn

import typer

from rich.columns import Columns
from rich.markup import escape
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
from storix._sync._compat import concurrent
from storix.config import StorixSettings, resolve_profile
from storix.constants import (
    DEFAULT_CONCURRENCY,
    DEFAULT_SOURCE_READ_SIZE,
    DEFAULT_TRANSFER_RANGES,
)
from storix.enums import PathKind, StorixEnum
from storix.errors import PathNotFoundError, StorageError, TransferStoppedError

from . import config_cmds, maintenance
from .config import load_prefs
from .icons import Icons
from .render import (
    close_line,
    console,
    dir_state_of,
    entry_decor,
    entry_label,
    err,
    human_size,
    launch_editor,
)
from .state import (
    _fs,  # pyright: ignore[reportPrivateUsage]
    _session,  # pyright: ignore[reportPrivateUsage]
    apply_layers,
    build_base,
    build_overrides,
    build_session,
    current_fs,
    debug_enabled,
    empty_all,
    icons_enabled,
    layer_summary,
    open_later,
    resolve_provider,
    resolve_selection,
    selection,
    set_debug,
    set_icons,
    stat_all,
    use_fs,
)


if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator, Mapping, Sequence
    from pathlib import PurePosixPath
    from types import FrameType

    from storix import Storix
    from storix.models import DirEntry, RawStat
    from storix.types import StorixPath


__all__ = ['app', 'current_fs', 'main', 'use_fs']


_M_MMAP_THRESHOLD: Final[int] = -3
"""glibc ``mallopt`` parameter selecting the dynamic mmap threshold."""


_NAVIGATE: Final[str] = 'Navigate'
"""Help panel for commands that locate things."""

_READ: Final[str] = 'Read'
"""Help panel for commands that report without changing anything."""

_WRITE: Final[str] = 'Write'
"""Help panel for commands that change the store."""

_TRANSFER: Final[str] = 'Transfer'
"""Help panel for commands that move bytes between local and remote."""

_SETUP: Final[str] = 'Session and setup'
"""Help panel for commands about the session itself, not its contents."""

_CONNECTION: Final[str] = 'Connection'
"""Option panel for the coordinates of the store to talk to."""

_SELECTION: Final[str] = 'Profile and overrides'
"""Option panel for choosing configuration rather than spelling it out."""

_SESSION: Final[str] = 'Session'
"""Option panel for how this one invocation behaves."""

_INSPECT: Final[str] = 'Inspect'
"""Option panel for asking sx about itself."""


app = typer.Typer(
    rich_markup_mode='rich',
    help='Storix - unix-like filesystem commands over any backend.',
    epilog=(
        'Ask sx about itself: [cyan]sx config show --effective[/cyan] '
        '(what this session will do, and where each value came from), '
        '[cyan]sx doctor[/cyan] (installation, config, reachability), '
        '[cyan]sx config sources[/cyan] (which files are read, in which order).'
    ),
    no_args_is_help=False,
    add_completion=False,
)


def _die(cmd: str, exc: Exception) -> NoReturn:
    if debug_enabled():
        import traceback

        # the raw provider detail (request IDs, HTTP context) lives on
        # the cause chain the concise message deliberately leaves out
        err.print(
            ''.join(traceback.format_exception(exc)), markup=False, highlight=False
        )
    err.print(f'[red]{cmd}: {escape(str(exc))}[/red]')
    raise typer.Exit(1) from exc


def _count_label(count: int, singular: str, plural: str) -> str:
    """Choose a count-sensitive label.

    Args:
        count: Quantity the label describes.
        singular: Label used for exactly one item.
        plural: Label used for every other count.
    """
    return singular if count == 1 else plural


def _transferred(files: int, directories: int) -> str:
    """Summarize what a directory transfer moved.

    Both counts are reported because a transfer can be entirely
    directories: an empty tree moves no bytes and still reproduces its
    shape at the destination, and a files-only summary would read as a
    transfer that did nothing.

    Args:
        files: How many files the transfer copied.
        directories: How many directories it created, including the
            destination root itself.
    """
    f = _count_label(files, 'file', 'files')
    d = _count_label(directories, 'directory', 'directories')
    return f'{files} {f}, {directories} {d}'


class _ListingSort(StorixEnum):
    """Key a listing is ordered by, shared by ``ls`` and ``tree``.

    One vocabulary for both commands: they list the same thing, so they
    order it the same way (``--sort`` plus ``-r``), and ``ls`` keeps ``-t``
    as the coreutils shorthand.
    """

    NAME = auto()
    TIME = auto()
    SIZE = auto()


def _listing_order(name: str) -> tuple[str, str]:
    """Sort key for a displayed name: case-insensitive, like ls and eza.

    Byte order would file every capitalized name above every lowercase one
    (``Zebra.txt`` before ``a.txt``), which neither coreutils under a UTF-8
    locale nor eza does. The exact name breaks ties so the order is total.

    Args:
        name: An entry name, or a path argument as it was written.
    """
    return name.lower(), name


def _needs_stat(entry: DirEntry, sort: _ListingSort) -> bool:
    """Whether ordering by ``sort`` still needs a stat for ``entry``.

    A time order needs every entry's modification time. A size order needs
    only a file whose listing did not carry its size, since a directory has
    no size of its own to compete on.

    Args:
        entry: The entry about to be ordered.
        sort: The key it will be ordered by.
    """
    return sort is _ListingSort.TIME or (not entry.is_dir and entry.size is None)


def _arguments(fs: Storix, paths: Sequence[str] | None) -> list[tuple[str, StorixPath]]:
    """Each path argument as it was written, beside its resolved target.

    No argument at all means the session cwd, the one implicit target the
    listing commands have always had; it is labelled by its absolute path,
    since the user wrote no name for it to be reported under.

    Args:
        fs: Session the arguments resolve against.
        paths: The path arguments, empty or ``None`` for the cwd.
    """
    if not paths:
        cwd = fs.resolve()
        return [(str(cwd), cwd)]
    return [(path, fs.resolve(path)) for path in paths]


def _checked_stats(
    cmd: str, fs: Storix, targets: Sequence[StorixPath]
) -> list[RawStat]:
    """Stat every argument in one batch, refusing the run if any is bad.

    sx checks every argument before it acts on any of them, where coreutils
    takes them one at a time and reports failures as it goes: ``sx du a nope``
    reports nothing where unix du reports ``a`` first. Deliberate, and the
    same contract ``cat`` already keeps. One concurrent batch, so K arguments
    cost one round trip's latency rather than K.

    Args:
        cmd: Command name the failure is reported under.
        fs: Session to stat through.
        targets: The resolved arguments.

    Raises:
        SystemExit: Through ``_die`` if any argument cannot be stat'd.
    """
    try:
        return stat_all(fs, targets)
    except StorageError as exc:
        _die(cmd, exc)


def _scan(fs: Storix, target: StorixPath, *, all: bool) -> list[DirEntry]:
    """One argument's listing, materialized so it can be run in a batch.

    A thunk over this is what lets several arguments list concurrently; a
    lazy iterator handed to ``concurrent`` would do its I/O back on the
    calling thread, one argument at a time.

    Args:
        fs: Session to list through.
        target: The resolved argument to list.
        all: Include hidden (dot-prefixed) entries.
    """
    return list(fs.scandir(target, all=all))


type _ListingBlock = tuple[str | None, list[DirEntry], Mapping[str, bool | None]]
"""One printed section of an ``ls``: its header (``None`` for the group of
file arguments, and for a lone argument, which ls never heads), its
entries, and the emptiness of whichever of them are directories."""


def _listing_blocks(
    fs: Storix,
    arguments: Sequence[tuple[str, StorixPath]],
    listings: Sequence[list[DirEntry]],
    *,
    reverse: bool,
    show_empty: bool,
) -> list[_ListingBlock]:
    """Group ``ls`` arguments into the sections unix ls prints.

    The plain files come first as one unheaded group, then the directories
    each under their own ``name:`` header, ordered by the argument as it was
    written. A header appears only when there is more than one argument to
    tell apart.

    Args:
        fs: Session the emptiness lookups go through.
        arguments: Each argument as written, beside its resolved target.
        listings: Each argument's entries, aligned with ``arguments``.
        reverse: Invert the order of the directory sections, as ls -r does.
        show_empty: Whether the folder glyph needs each directory's emptiness.
    """
    files: list[DirEntry] = []
    directories: list[tuple[str, StorixPath, list[DirEntry]]] = []
    for (shown, target), entries in zip(arguments, listings, strict=True):
        # a file argument lists as itself, so an entry whose path is the
        # argument proves the argument was not a directory; a directory's
        # entries always sit below it
        if len(entries) == 1 and entries[0].path == target:
            files.append(entries[0])
        else:
            directories.append((shown, target, entries))
    directories.sort(key=lambda item: _listing_order(item[0]))
    if reverse:
        directories.reverse()

    empty: list[Mapping[str, bool | None]] = [{} for _ in directories]
    if show_empty:
        names = [[e.name for e in entries if e.is_dir] for _, _, entries in directories]
        # one batch across every argument, not one listing per argument
        batched = concurrent(
            partial(empty_all, fs, base, group)
            for (_, base, _), group in zip(directories, names, strict=True)
        )
        empty = [
            dict(zip(group, flags, strict=True))
            for group, flags in zip(names, batched, strict=True)
        ]

    headed = len(arguments) > 1
    blocks: list[_ListingBlock] = [(None, files, {})] if files else []
    blocks += [
        (f'{shown}:' if headed else None, entries, flags)
        for (shown, _, entries), flags in zip(directories, empty, strict=True)
    ]
    return blocks


def _long_table(
    entries: Sequence[DirEntry],
    stats: Mapping[StorixPath, RawStat],
    label: Callable[[DirEntry], Text],
) -> Table:
    """The ``ls -l`` columns for one block: kind, size, mtime, name.

    Args:
        entries: The block's entries, in the order they print.
        stats: The stat batch every entry's size and mtime is read from.
        label: Renders one entry's icon and name.
    """
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column()  # kind ('d' or '-')
    table.add_column(justify='right')  # size
    table.add_column(style='dim')  # date & time
    table.add_column()  # icon + name
    for entry in entries:
        s = stats[entry.path]
        kind = Text('d' if entry.is_dir else '-', style='dim')
        if entry.is_dir:
            size_text = Text('-', style='dim')
        else:
            size_text = Text(human_size(s.size), style='green')
        mtime_text = Text(s.modified.strftime('%d %b %H:%M'), style='dim')
        table.add_row(kind, size_text, mtime_text, label(entry))
    return table


def _sorted_entries(
    fs: Storix,
    entries: list[DirEntry],
    sort: _ListingSort,
    *,
    reverse: bool = False,
    stats: Mapping[StorixPath, RawStat] | None = None,
) -> list[DirEntry]:
    """Order one directory's entries by the key the listing commands share.

    ``name`` collates case-insensitively (``_listing_order``), ``time`` puts
    the newest first, ``size`` the largest first, and ``reverse`` inverts
    whichever was chosen. The name collation is applied first, so entries
    tying on a time or a size still come out alphabetical.

    ``time`` and ``size`` need a stat a listing does not always carry, so
    what the caller already holds is reused (``ls -l`` batches stats for its
    own columns), a listing that carried the size is taken at its word, and
    only what is left over is fetched - in one concurrent batch
    (``stat_all``), one round trip's latency rather than one per entry.

    Args:
        fs: Session used to fetch any stat the chosen key still needs.
        entries: One directory's entries, in any order.
        sort: Key to order by.
        reverse: Invert the chosen order, as ``ls -r`` and ``tree -r`` do.
        stats: Stats the caller already holds, keyed by entry path. Keyed by
            path rather than by name because ``ls`` orders one group of file
            arguments that may come from different directories, where two
            entries can share a basename.

    Raises:
        StorageError: If a stat the chosen key needs cannot be read.
    """
    ordered = sorted(entries, key=lambda e: _listing_order(e.name))
    if sort is not _ListingSort.NAME and len(ordered) > 1:
        known = dict(stats or {})
        needed = [e for e in ordered if e.path not in known and _needs_stat(e, sort)]
        known |= {
            e.path: s
            for e, s in zip(needed, stat_all(fs, [e.path for e in needed]), strict=True)
        }

        def size_of(entry: DirEntry) -> int:
            # a directory has no meaningful size of its own - ls -l and
            # tree -l both render '-' in its size column - so it cannot
            # compete on one: -1 sinks every directory below the files,
            # identically in both commands
            if entry.is_dir:
                return -1
            batched = known.get(entry.path)
            # absent from the batch means the listing carried the size
            return batched.size if batched is not None else (entry.size or 0)

        if sort is _ListingSort.TIME:
            ordered.sort(key=lambda e: known[e.path].modified, reverse=True)
        else:
            ordered.sort(key=size_of, reverse=True)
    if reverse:
        ordered.reverse()
    return ordered


# --- listing / navigation ---


@app.command(rich_help_panel=_NAVIGATE)
def ls(
    paths: Annotated[list[str] | None, typer.Argument()] = None,
    *,
    long: Annotated[bool, typer.Option('-l', '--long')] = False,
    all_: Annotated[bool, typer.Option('-a', '--all')] = False,
    sort: Annotated[
        _ListingSort,
        typer.Option('--sort', help='order entries by name | time | size'),
    ] = _ListingSort.NAME,
    time_sort: Annotated[
        bool,
        typer.Option('-t', '--time', help='shorthand for --sort time (newest first)'),
    ] = False,
    reverse: Annotated[
        bool, typer.Option('-r', '--reverse', help='invert the order')
    ] = False,
) -> None:
    """List directory contents (hidden entries need -a).

    Several arguments list the way unix ls does: the plain files first as
    one group, then each directory under its own ``name:`` header with a
    blank line between blocks, and no header at all for a single argument.
    Every argument is read and grouped before anything prints, so one
    unreadable argument refuses the whole listing rather than half of it.

    --sort orders the entries within each block by name (default), time
    (newest first) or size (largest first, directories last); -t is the
    coreutils shorthand for --sort time. Directory arguments are always
    ordered by name, whatever --sort says, since ordering them by a stat
    would cost a round trip nothing else here needs. -r inverts both the
    entry order and the order of the directory blocks.

    The per-entry backend lookups a listing does not carry for free -
    directory emptiness (the folder glyph), mtime (``-t``), a missing file
    size (``-l``, ``--sort size``) - are batched concurrently
    (``state.empty_all`` / ``stat_all``) across every argument at once, so
    K arguments over N entries on a cloud backend cost one round trip's
    worth of latency, not K x N.
    """
    fs = _fs()
    arguments = _arguments(fs, paths)
    try:
        # one batch for every argument's listing, not one round trip each
        listings = concurrent(
            partial(_scan, fs, target, all=all_) for _, target in arguments
        )
    except StorageError as exc:
        _die('ls', exc)

    show_empty = icons_enabled() and load_prefs().dir_contents
    blocks = _listing_blocks(
        fs, arguments, listings, reverse=reverse, show_empty=show_empty
    )

    # -t is the shorthand, so it wins when both ways of asking are given
    order = _ListingSort.TIME if time_sort else sort
    needed = [
        entry
        for _, entries, _ in blocks
        for entry in entries
        if long
        or (
            order is not _ListingSort.NAME
            and len(entries) > 1
            and _needs_stat(entry, order)
        )
    ]
    try:
        # every block's stats in one batch, so the ordering below and the -l
        # columns both read from it instead of paying per block
        stats = dict(
            zip(
                (entry.path for entry in needed),
                stat_all(fs, [entry.path for entry in needed]),
                strict=True,
            )
        )
    except StorageError as exc:
        _die('ls', exc)

    def label(entry: DirEntry, flags: Mapping[str, bool | None]) -> Text:
        if entry.is_dir and show_empty:
            is_empty = flags.get(entry.name)
            populated = None if is_empty is None else not is_empty
            state = dir_state_of(populated=populated)
        else:
            state = 'closed'
        return entry_label(entry, dir_state=state)

    for index, (header, entries, flags) in enumerate(blocks):
        if index:  # ls separates its blocks with one blank line
            console.print()
        if header is not None:
            console.print(f'[bold blue]{escape(header)}[/bold blue]')
        ordered = _sorted_entries(fs, entries, order, reverse=reverse, stats=stats)
        decorate = partial(label, flags=flags)
        if long:
            console.print(_long_table(ordered, stats, decorate))
        elif ordered:
            console.print(
                Columns([decorate(entry) for entry in ordered], padding=(0, 2))
            )


@app.command(rich_help_panel=_NAVIGATE)
def pwd() -> None:
    """Print the working directory."""
    console.print(str(_fs().pwd()))


@app.command(rich_help_panel=_NAVIGATE)
def cd(path: Annotated[str | None, typer.Argument()] = None) -> None:
    """Change directory (no argument: home, '-' for the previous one)."""
    fs = _fs()
    try:
        fs.cd(path)
    except StorageError as exc:
        _die('cd', exc)
    if path == '-':
        # unix cd echoes where '-' landed, because you did not name it. The
        # jump glyph (zoxide's convention) marks it as a destination rather
        # than one more line of output, and drops out when icons are off.
        arrow = (
            f'{Icons.ARROW_JUMP} ' if icons_enabled() and console.is_terminal else ''
        )
        # dim, and one style across the glyph and the path: this line answers
        # a question the user did not ask, so it should be legible without
        # competing with the output of whatever they run next.
        # highlight=False because rich's path highlighter otherwise repaints
        # the directory magenta on top of the style it was handed, which is
        # what made the arrow and the path two different colors
        console.print(f'[dim]{arrow}{fs.pwd()}[/dim]', highlight=False)


class _LevelBuffer:
    """Group a top-down walk by parent, pulled one complete level at a time.

    ``tree`` streams: it renders each line as soon as the walk has produced
    enough of the tree to draw it, instead of materializing the whole
    traversal first. Requires ``walk(order='level')``: only that order
    emits each level whole in stable order, making entry depth monotone
    non-decreasing, so the first entry deeper than a requested level (or
    stream exhaustion) proves that level complete. The deeper entry is
    buffered too; it belongs to its own level.
    """

    def __init__(self, walked: Iterator[DirEntry], root: StorixPath) -> None:
        self._walked = walked
        self._root_depth = len(root.parts)
        self._grouped: defaultdict[StorixPath, list[DirEntry]] = defaultdict(list)
        self._complete = 0
        self._exhausted = False

    def ensure_level(self, depth: int) -> None:
        """Pull walk entries into the buffer until level ``depth`` is whole.

        Raises:
            StorageError: If the underlying walk fails mid-stream.
        """
        while not self._exhausted and self._complete < depth:
            entry = next(self._walked, None)
            if entry is None:
                self._exhausted = True
                return
            self._grouped[entry.path.parent].append(entry)
            depth_of = len(entry.path.parts) - self._root_depth
            self._complete = max(self._complete, depth_of - 1)

    def children_of(self, parent: StorixPath) -> list[DirEntry]:
        """Already-buffered entries directly under ``parent``."""
        return self._grouped.get(parent, [])


@app.command(rich_help_panel=_NAVIGATE)
def tree(
    paths: Annotated[list[str] | None, typer.Argument()] = None,
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
        _ListingSort,
        typer.Option('--sort', help='order siblings by name | time | size'),
    ] = _ListingSort.NAME,
    reverse: Annotated[
        bool, typer.Option('-r', '--reverse', help='invert the order')
    ] = False,
) -> None:
    """Print a directory tree (unix tree style, with the closing count).

    -L caps the depth and -l adds eza-style size and kind columns. Siblings
    take the same ordering as ls: --sort by name (default), time (newest
    first) or size (largest first, directories last), and -r inverts it.

    Several arguments each get their own tree, in the order they were
    written, and the closing count is the combined total over all of them,
    as unix tree reports it. Every argument is checked before the first
    line prints, so a bad one refuses them all.
    """
    fs = _fs()
    if level is not None and level < 1:
        _die('tree', ValueError(f'level must be at least 1, got {level}'))
    arguments = _arguments(fs, paths)
    # unix tree counts its root: a directory argument, or the one file a
    # file argument names (the walk under it is empty either way). One batch
    # answers that for every argument, and validates them at the same time.
    kinds = [raw.kind for raw in _checked_stats('tree', fs, [t for _, t in arguments])]
    dirs: int = sum(kind is PathKind.DIRECTORY for kind in kinds)
    files: int = sum(kind is PathKind.FILE for kind in kinds)

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

    def render(
        buffer: _LevelBuffer, parent: StorixPath, prefix: str, depth: int
    ) -> None:
        nonlocal dirs, files
        buffer.ensure_level(depth)
        children = _sorted_entries(
            fs, buffer.children_of(parent), sort, reverse=reverse
        )
        for i, child in enumerate(children):
            last = i == len(children) - 1
            branch = '└── ' if last else '├── '
            if child.is_dir:
                dirs += 1
                expanded = level is None or depth < level
                if expanded:
                    # the empty/full glyph needs the child's own listing
                    buffer.ensure_level(depth + 1)
                # only claim empty/full when the walk actually looked inside
                state = (
                    'closed'
                    if not expanded
                    else dir_state_of(populated=bool(buffer.children_of(child.path)))
                )
                label = entry_label(child, slash=False, dir_state=state)
                console.print(columns(child) + Text(f'{prefix}{branch}') + label)
                if expanded:
                    render(
                        buffer,
                        child.path,
                        prefix + ('    ' if last else '│   '),
                        depth + 1,
                    )
            else:
                files += 1
                console.print(
                    columns(child) + Text(f'{prefix}{branch}') + entry_label(child)
                )

    for _, root in arguments:
        # one core walk per argument carries its traversal (concurrent,
        # depth-bounded); everything below is presentation over entries
        # pulled on demand, so lines print while deeper levels are still
        # being listed. order='level' keeps sibling groups contiguous, which
        # _LevelBuffer's monotone-depth rule (and tree's sibling sorting)
        # depends on.
        walked = fs.walk(root, all=all_, max_depth=level, order='level')
        console.print(f'[bold blue]{root}[/bold blue]')
        try:
            render(_LevelBuffer(walked, root), root, '', 1)
        except StorageError as exc:  # the walk pull or a --sort stat batch can fail
            _die('tree', exc)
    d = _count_label(dirs, 'directory', 'directories')
    f = _count_label(files, 'file', 'files')
    console.print(f'\n{dirs} {d}, {files} {f}')


@app.command(rich_help_panel=_NAVIGATE)
def find(
    paths: Annotated[list[str] | None, typer.Argument()] = None,
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
    """Recursively find entries by name glob and/or type (unix find).

    Several arguments are searched in turn, in the order they were written,
    and every one of them is checked before the first match prints.
    """
    fs = _fs()
    kind = {'f': PathKind.FILE, 'd': PathKind.DIRECTORY}.get(type_) if type_ else None
    if type_ is not None and kind is None:
        _die('find', ValueError(f"type must be 'f' or 'd', got {type_!r}"))
    arguments = _arguments(fs, paths)
    # searched for its refusal, not for the stats: find needs nothing about
    # an argument except that it is there, and one bad argument has to
    # refuse the run before any match prints
    _checked_stats('find', fs, [target for _, target in arguments])
    try:
        # print as the walk yields, like unix find; partial output before
        # a mid-stream error is fine
        for _, target in arguments:
            for entry in fs.find(target, name=name, kind=kind, all=all_):
                icon, style = entry_decor(entry)
                text = f'{icon} {entry.path}' if icon else str(entry.path)
                console.print(Text(text, style=style))
    except StorageError as exc:
        _die('find', exc)


# --- creating / writing ---


@app.command(rich_help_panel=_WRITE)
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


@app.command(rich_help_panel=_WRITE)
def touch(files: Annotated[list[str], typer.Argument()]) -> None:
    """Create files (or refresh their mtime)."""
    try:
        _fs().touch(*files)
    except StorageError as exc:
        _die('touch', exc)


@app.command(rich_help_panel=_WRITE)
def echo(
    text: Annotated[str | None, typer.Argument()] = None,
    file: Annotated[str | None, typer.Option('-f', '--file')] = None,
    *,
    append: Annotated[bool, typer.Option('-a', '--append')] = False,
    no_newline: Annotated[
        bool, typer.Option('-n', '--no-newline', help='omit the trailing newline')
    ] = False,
) -> None:
    """Print text, or write it to a file with -f.

    Left without TEXT the data comes from a pipe, so a producer writes
    straight into storage (``prog | sx echo -f /dest.bin``). The pipe is
    handed to the core as a stream, which pulls it in bounded reads, and
    it is stored byte for byte: piped data arrives with its own encoding
    and its own line endings, so nothing decodes it and nothing appends a
    newline to it, which is what -n asks for anyway.

    A terminal is never read as data, because the REPL's stdin is the
    prompt being typed into; there, a missing TEXT is unix echo's empty
    operand list and prints just the newline. A lone ``-`` stays literal
    text: this argument is content, not a file name, so overloading it
    would leave no way to print a dash.
    """
    piped = text is None and not sys.stdin.isatty()
    payload = text or ''
    if not no_newline:
        payload += '\n'

    if file is None:
        last: str | bytes
        if piped:
            # the pipe's own last byte is what says whether the line was left
            # open, not `payload`: piped bytes are copied verbatim, so neither
            # -n nor the newline a text operand gets ever applied to them
            last = b''
            while chunk := sys.stdin.buffer.read(DEFAULT_SOURCE_READ_SIZE):
                sys.stdout.buffer.write(chunk)
                last = chunk[-1:]
        else:
            # literal, like unix echo: rich would read '[bold]' as markup (and
            # raise MarkupError on a lone '[/]') and wrap at the console width
            sys.stdout.write(payload)
            last = payload[-1:]
        sys.stdout.flush()
        close_line(last)
        return
    try:
        _fs().echo(
            sys.stdin.buffer if piped else payload,
            file,
            mode='a' if append else 'w',
        )
    except StorageError as exc:
        _die('echo', exc)


@app.command(rich_help_panel=_WRITE)
def edit(path: Annotated[str, typer.Argument()]) -> None:
    """Open a file in $VISUAL/$EDITOR, writing it back if it changed.

    The backend file is staged into a temporary directory under its own
    name (so the editor shows the name you asked for, and picks its syntax
    highlighting from the extension), then written back only when the
    bytes actually differ - an editor that exits without saving costs no
    write, and on an object store no new version.

    A path that does not exist yet opens empty and is created on save,
    like opening a new file in any editor. Concurrent edits are last-write
    wins; nothing here locks the object.
    """
    fs = _fs()
    try:
        before = fs.cat(path)
    except PathNotFoundError:
        before = None  # a new file: open empty, create it only if written to
    except StorageError as exc:
        _die('edit', exc)

    with tempfile.TemporaryDirectory(prefix='sx-edit-') as staging:
        staged = Path(staging) / fs.resolve(path).name
        staged.write_bytes(before or b'')
        launch_editor(staged)
        after = staged.read_bytes()

    if after == (before or b''):
        console.print('[dim]unchanged[/dim]')
        return
    try:
        fs.echo(after, path)
    except StorageError as exc:
        _die('edit', exc)


# --- reading ---


@app.command(rich_help_panel=_READ)
def cat(
    files: Annotated[list[str], typer.Argument()],
    *,
    binary: Annotated[bool, typer.Option('-b', '--binary')] = False,
) -> None:
    """Concatenate and print files.

    Streams over the core's bounded ``stream`` and writes the bytes
    straight out: file contents are data, and rich would wrap them to the
    console width and expand tabs. A file larger than memory prints fine.
    """
    fs = _fs()
    out = sys.stdout.buffer
    last = b''
    try:
        for i, chunk in enumerate(fs.stream(*files)):
            # the binary guard reads the first chunk only, so a NUL that
            # appears later still prints; widen it if that bites
            if i == 0 and not binary and b'\x00' in chunk:
                err.print('[yellow]cat: binary file; use -b[/yellow]')
                return
            out.write(chunk)
            last = chunk[-1:] or last
    except StorageError as exc:
        _die('cat', exc)

    out.flush()
    close_line(last)


@app.command(rich_help_panel=_READ)
def stat(paths: Annotated[list[str], typer.Argument()]) -> None:
    """Show each path's properties.

    Several arguments print one block each, in the order they were written
    and with no added header, as unix stat does - each block already names
    its own path. All of them are read in one concurrent batch, so a bad
    argument refuses the whole run.
    """
    fs = _fs()
    try:
        properties = concurrent(partial(fs.stat, path) for path in paths)
    except StorageError as exc:
        _die('stat', exc)
    for props in properties:
        console.print(str(props))


@app.command(rich_help_panel=_READ)
def du(
    paths: Annotated[list[str] | None, typer.Argument()] = None,
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

    Several arguments each get their own report, in the order they were
    written, with no header and no combined grand total - unix du reports
    them the same way. Every argument is checked before the first line
    prints, so a bad one refuses them all.
    """
    fs = _fs()
    arguments = _arguments(fs, paths)
    # du needs to know whether each argument is a file (a file reports one
    # line, a directory a whole breakdown); one batch answers that for every
    # argument, and validates them at the same time
    kinds = [raw.kind for raw in _checked_stats('du', fs, [t for _, t in arguments])]

    def report(shown: str, target: StorixPath, *, is_file: bool) -> None:
        def emit(size: int, entry_path: StorixPath) -> None:
            if entry_path == target:
                label = shown
            else:
                label = (
                    f'{shown.rstrip("/")}/{entry_path.relative_to(target).as_posix()}'
                )
            console.print(f'{human_size(size) if human else size}\t{label}')

        if summary or is_file:
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

    try:
        for (shown, target), kind in zip(arguments, kinds, strict=True):
            report(shown, target, is_file=kind is PathKind.FILE)
    except StorageError as exc:
        _die('du', exc)


@app.command(rich_help_panel=_READ)
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


@app.command(rich_help_panel=_WRITE)
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


@app.command(rich_help_panel=_WRITE)
def rmdir(directories: Annotated[list[str], typer.Argument()]) -> None:
    """Remove empty directories (use rm -r for non-empty)."""
    try:
        _fs().rmdir(*directories)
    except StorageError as exc:
        _die('rmdir', exc)


# --- moving / copying ---


@app.command(rich_help_panel=_WRITE)
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


@app.command(rich_help_panel=_WRITE)
def mv(paths: Annotated[list[str], typer.Argument()]) -> None:
    """Move/rename; the last argument is the destination."""
    try:
        _fs().mv(*paths)
    except (StorageError, TypeError) as exc:
        _die('mv', exc)


# --- queries ---


@app.command(rich_help_panel=_NAVIGATE)
def exists(paths: Annotated[list[str], typer.Argument()]) -> None:
    """Exit 0 only if every path exists."""
    fs = _fs()
    if not all(fs.exists(p) for p in paths):
        raise typer.Exit(1)


# --- local <-> remote transfer ---


@contextmanager
def _cancellable() -> Generator[threading.Event]:
    """Make the next Ctrl+C ask a transfer to stop instead of interrupting.

    A transfer runs its files on worker threads, and a thread blocked in a
    socket read cannot be interrupted: ``KeyboardInterrupt`` only ever
    reaches the main thread, so the prompt would come back while the
    transfer kept running. Instead the first Ctrl+C sets an event that the
    progress sink checks once per chunk (the one place every transfer path
    already calls into ``sx``), so each stream unwinds at its next chunk
    boundary and nothing outlives the command. A second Ctrl+C restores the
    normal interrupt for an immediate, ungraceful exit.

    Yields:
        The event, set when the user has asked for the transfer to stop.

    Raises:
        KeyboardInterrupt: On the second Ctrl+C, from the default handler.
    """
    stop = threading.Event()

    def ask_to_stop(signum: int, frame: FrameType | None) -> None:
        del frame
        if stop.is_set():
            signal.signal(signal.SIGINT, previous)
            raise KeyboardInterrupt(signum)
        stop.set()
        console.print('[yellow]stopping...[/yellow]')

    try:
        previous = signal.signal(signal.SIGINT, ask_to_stop)
    except ValueError:
        # not the main thread (an embedded sx): no handler to install, and
        # the transfer simply keeps today's uninterruptible behavior
        yield stop
        return
    try:
        yield stop
    finally:
        signal.signal(signal.SIGINT, previous)


def _cancelled(cmd: str) -> NoReturn:
    """Report an interrupted transfer and exit with the shell's SIGINT code."""
    console.print(f'[yellow]{cmd}: stopped[/yellow]')
    raise typer.Exit(130)


@contextmanager
def _transfer_progress(
    fs: Storix, label: str, total: int, stop: threading.Event | None = None
) -> Generator[Storix]:
    """Session emitting into a live bar; sx owns ``total`` (ADR 0019).

    Wraps ``fs`` in an outermost ``ObservabilityLayer`` whose sink moves a
    rich progress bar; the percentage is ``transferred`` over the total the
    caller already owns. The wrapped session starts at home, so callers
    must pass absolute paths.

    The sink tracks cumulative bytes per stream - keyed by path *and*
    starting offset, since a parallel ``download`` reads one file through
    several ranges that each count from zero - so events from concurrently
    transferring streams may interleave in any order and the bar still
    shows the true sum. Directory transfers run their per-file thunks
    through the core ``concurrent`` helper, so the sink is called from
    worker threads:
    rich's ``Progress.update`` takes its own internal ``RLock``, and our
    lock keeps the tally read-modify-write and the bar update one atomic,
    monotonic step.

    The sink is also the transfer's cancellation point: it runs once per
    chunk on every path, in whichever thread produced that chunk, so
    checking ``stop`` there is what lets a Ctrl+C unwind every stream.

    Args:
        fs: The session to wrap.
        label: Bar description, typically the file's basename.
        total: The transfer's total size in bytes.
        stop: Event that asks the transfer to stop; ``None`` never stops.

    Yields:
        The wrapped session; use it for the one transfer.

    Raises:
        TransferStoppedError: From a worker thread, once ``stop`` is set.
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

        lock = threading.Lock()
        seen: dict[tuple[PurePosixPath, int], int] = {}
        completed = 0

        def on_event(event: TransferEvent) -> None:
            nonlocal completed
            if stop is not None and stop.is_set():
                raise TransferStoppedError
            stream = (event.path, event.offset)
            with lock:
                completed += event.transferred - seen.get(stream, 0)
                seen[stream] = event.transferred
                progress.update(task, completed=completed)

        yield fs.with_layer(
            ObservabilityLayer,
            sink=on_event,
        )


def _range_budget(files: int) -> int:
    """How many ranges one file of a transfer may open at once.

    Range parallelism spends the fan-out budget the transfer is not using
    rather than adding to it, so a wide transfer keeps today's shape and a
    narrow one (few files, or one large file) fills the same number of
    connections instead of idling (ADR 0032). The core still declines to
    split a file below ``MIN_RANGE_SIZE``.

    ``STORIX_MAX_TRANSFER_RANGES`` lowers the ceiling for anyone who would
    rather spend fewer requests; 1 keeps every file on one stream. Read per
    transfer rather than cached, so exporting it takes effect immediately.

    Args:
        files: How many files this transfer has in flight.
    """
    ceiling = min(DEFAULT_TRANSFER_RANGES, StorixSettings().max_transfer_ranges)
    return max(1, min(ceiling, DEFAULT_CONCURRENCY // max(files, 1)))


@app.command(rich_help_panel=_TRANSFER)
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
        walked = list(fs.walk(src, all=True))
        remote_files = [e for e in walked if not e.is_dir]
        stats = stat_all(fs, [e.path for e in remote_files])
        total_bytes = sum(s.size for s in stats)
        targets = [(e.path, dst / e.path.relative_to(src)) for e in remote_files]
        # every directory the walk saw, not only the parents the files
        # imply: a directory holding no files is still part of the structure
        # being copied, and deriving the set from the files alone silently
        # drops it. walk never yields its own starting directory, so dst is
        # added here, which is what makes an entirely empty source land at
        # all. mkdir dedupes through the set and parents=True absorbs the
        # ancestors, so this stays one call per directory.
        dirs = {dst} | {dst / e.path.relative_to(src) for e in walked if e.is_dir}
        for directory in dirs:
            directory.mkdir(parents=True, exist_ok=True)
        done: set[Path] = set()
        done_lock = threading.Lock()
        try:
            with (
                _cancellable() as stop,
                _transfer_progress(fs, src.name, total_bytes, stop) as obs,
            ):
                ranges = _range_budget(len(targets))

                def fetch(remote_file: StorixPath, out_path: Path) -> None:
                    with out_path.open('wb') as out:
                        obs.download(remote_file, out, ranges=ranges)
                    with done_lock:
                        done.add(out_path)

                # per-file streams batched through the core concurrent
                # helper, not N serial round trips (see state.py)
                concurrent(
                    partial(fetch, remote_file, out_path)
                    for remote_file, out_path in targets
                )
        except TransferStoppedError:
            # every destination this transfer did not finish, removed here
            # rather than by each worker: a stopped transfer returns without
            # joining its threads (ADR 0032), so worker-side cleanup would
            # race the caller. Unlinking a file a straggler still holds open
            # is fine - it keeps writing to an unlinked inode and the
            # directory entry is already gone.
            for _, out_path in targets:
                if out_path not in done:
                    out_path.unlink(missing_ok=True)
            _cancelled('pull')
        except StorageError as exc:
            _die('pull', exc)
        moved = _transferred(len(remote_files), len(dirs))
        console.print(f'{remote} -> {dst} ({moved})')
        return

    dst = Path(local).expanduser() if local else Path(src.name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        with (
            _cancellable() as stop,
            _transfer_progress(fs, src.name, st.size, stop) as obs,
            dst.open('wb') as out,
        ):
            obs.download(src, out, ranges=_range_budget(1))
    except TransferStoppedError:
        dst.unlink(missing_ok=True)
        _cancelled('pull')
    except StorageError as exc:
        _die('pull', exc)
    console.print(f'{remote} -> {dst}')


@app.command(rich_help_panel=_TRANSFER)
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
        # one traversal classified as it goes: the directories are as much
        # of the tree as the files are, and a set derived from the files
        # alone loses every directory holding none of them
        files: list[Path] = []
        dirs = {dst}
        for entry in src.rglob('*'):
            if entry.is_dir():
                dirs.add(dst / entry.relative_to(src))
            elif entry.is_file():
                files.append(entry)
        total_bytes = sum(f.stat().st_size for f in files)
        targets = [(f, dst / f.relative_to(src)) for f in files]
        # the whole set in one core-batched mkdir, not one round-trip-heavy
        # mkdir per directory; parents=True already
        # makes existing directories a silent success, so any failure
        # here is real (permission, an intermediate file, a missing
        # bucket) and must die, not be suppressed (ADR 0029)
        try:
            fs.mkdir(*sorted(dirs), parents=True)
            with (
                _cancellable() as stop,
                _transfer_progress(fs, src.name, total_bytes, stop) as obs,
            ):

                def send(file_path: Path, remote_file: StorixPath) -> None:
                    with file_path.open('rb') as data:
                        content_type = None
                        if fs.backend.capabilities.content_type:
                            content_type = detect_mimetype(
                                buf=data.read(4096), path=file_path.name
                            )
                            data.seek(0)
                        obs.echo(data, remote_file, content_type=content_type)

                # per-file streams batched through the core concurrent
                # helper, not N serial round trips (see state.py)
                concurrent(
                    partial(send, file_path, remote_file)
                    for file_path, remote_file in targets
                )
        except TransferStoppedError:
            # the remote file being written when the stop arrived keeps
            # whatever the backend had already accepted; re-running the
            # push overwrites it
            _cancelled('push')
        except StorageError as exc:
            _die('push', exc)
        console.print(f'{local} -> {dst} ({_transferred(len(files), len(dirs))})')
        return

    dst = fs.resolve(remote) if remote else fs.pwd() / src.name
    try:
        # scaffold missing destination parents inside the storage root,
        # exactly as the directory arm does (ADR 0029); echo() itself
        # stays strict about them
        fs.mkdir(dst.parent, parents=True)
        with (
            _cancellable() as stop,
            _transfer_progress(fs, src.name, src.stat().st_size, stop) as obs,
            src.open('rb') as data,
        ):
            content_type = None
            if fs.backend.capabilities.content_type:
                content_type = detect_mimetype(buf=data.read(4096), path=src.name)
                data.seek(0)
            obs.echo(data, dst, content_type=content_type)
    except TransferStoppedError:
        _cancelled('push')
    except StorageError as exc:
        _die('push', exc)
    console.print(f'{local} -> {dst}')


# --- session ---


@app.command(rich_help_panel=_SETUP)
def whereami() -> None:
    """Show what this session is connected to, and where it stands.

    The one question a session cannot answer from its prompt: which
    account, which container, under which profile and stage. Cheap by
    construction - it reads the open session and the loader, and opens no
    connection of its own.
    """
    fs = _fs()
    console.print(f'[green]backend:[/green]  {type(fs.base_backend).__name__}')
    profile, environment = selection()
    if profile:
        stage = environment or resolve_profile(profile, environment).environment
        shown = f'{profile} [dim](stage: {stage or "none"})[/dim]'
        console.print(f'[green]profile:[/green]  {shown}')
    console.print(f'[green]root uri:[/green] {fs.locate("/")}')
    console.print(f'[green]cwd:[/green]      {fs.pwd()}')
    console.print(f'[green]home:[/green]     {fs.home}')
    summary = layer_summary(fs)
    if summary:
        console.print(f'[green]layers:[/green]   {summary}')


# the old name for the same answer, kept working and out of the help
app.command('provider', hidden=True)(whereami)


@app.command(rich_help_panel=_SETUP)
def provision() -> None:
    """Create the backend's storage root if missing (idempotent).

    ADLS creates a missing filesystem; local and memory report it already
    present. S3/R2/GCS and Azure Blob (opendal, data-plane only) cannot
    create a root - use your provider tooling. ``mkdir`` never creates a
    root.
    """
    fs = _fs()
    try:
        created = fs.provision()
    except StorageError as exc:
        _die('provision', exc)
    root = fs.locate('/')
    console.print(f'provisioned: {root}' if created else f'already present: {root}')


@app.command(rich_help_panel=_SETUP)
def shell() -> None:
    """Start the interactive shell."""
    from .shell import start_shell

    start_shell(_fs())


# registered last so the help lists the filesystem commands a user came for
# above the ones about sx itself; panels appear in registration order
app.add_typer(config_cmds.config_app, rich_help_panel=_SETUP)
app.command('update', rich_help_panel=_SETUP)(maintenance.update)
app.command('install', rich_help_panel=_SETUP)(maintenance.install)
app.command('uninstall', rich_help_panel=_SETUP)(maintenance.uninstall)
app.command('doctor', rich_help_panel=_SETUP)(maintenance.doctor)


def _version_callback(value: bool) -> None:  # noqa: FBT001 - typer eager callback
    """Print ``sx <version>`` and exit, building no backend (D6)."""
    if not value:
        return
    from importlib.metadata import version

    console.print(f'sx {version("storix")}')
    raise typer.Exit


@app.callback(invoke_without_command=True)
def _main(  # noqa: PLR0913  # pyright: ignore[reportUnusedFunction]
    ctx: typer.Context,
    *,
    version: Annotated[
        bool,
        typer.Option(
            '--version',
            callback=_version_callback,
            is_eager=True,
            help='show the sx version and exit',
            rich_help_panel=_INSPECT,
        ),
    ] = False,
    provider_: Annotated[
        str | None,
        typer.Option(
            '-p',
            '--provider',
            help='local | memory | azure | azblob | s3 | gcs',
            rich_help_panel=_CONNECTION,
        ),
    ] = None,
    base: Annotated[
        str | None,
        typer.Option(
            '--base', help='local base directory', rich_help_panel=_CONNECTION
        ),
    ] = None,
    bucket: Annotated[
        str | None,
        typer.Option('--bucket', help='s3 / gcs bucket', rich_help_panel=_CONNECTION),
    ] = None,
    container: Annotated[
        str | None,
        typer.Option(
            '--container', help='azure container', rich_help_panel=_CONNECTION
        ),
    ] = None,
    account_name: Annotated[
        str | None,
        typer.Option(
            '--account-name',
            help='azure storage account',
            rich_help_panel=_CONNECTION,
        ),
    ] = None,
    region: Annotated[
        str | None,
        typer.Option('--region', help='s3 region', rich_help_panel=_CONNECTION),
    ] = None,
    endpoint: Annotated[
        str | None,
        typer.Option(
            '--endpoint', help='custom endpoint URL', rich_help_panel=_CONNECTION
        ),
    ] = None,
    root: Annotated[
        str | None,
        typer.Option(
            '--root', help='key prefix anchoring "/"', rich_help_panel=_CONNECTION
        ),
    ] = None,
    kind: Annotated[
        str | None,
        typer.Option(
            '--kind',
            help='azure surface: auto | adls | blob',
            rich_help_panel=_CONNECTION,
        ),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option(
            '--profile',
            help='named profile from a config file (sx config profiles)',
            rich_help_panel=_SELECTION,
        ),
    ] = None,
    environment: Annotated[
        str | None,
        typer.Option(
            '--environment',
            '--env',
            help='stage overlay within the selected profile',
            rich_help_panel=_SELECTION,
        ),
    ] = None,
    set_: Annotated[
        list[str] | None,
        typer.Option(
            '--set',
            help='provider.field=value override, repeatable (e.g. --set s3.root=/x)',
            rich_help_panel=_SELECTION,
        ),
    ] = None,
    cache: Annotated[
        bool,
        typer.Option(
            '--cache',
            help='read-through cache: du/ls/stat/cat',
            rich_help_panel=_SESSION,
        ),
    ] = False,
    cache_ttl: Annotated[
        float | None,
        typer.Option(
            '--cache-ttl',
            help='seconds before cached entries expire',
            rich_help_panel=_SESSION,
        ),
    ] = None,
    sandbox: Annotated[
        str | None,
        typer.Option(
            '--sandbox',
            help='jail the session under this path',
            rich_help_panel=_SESSION,
        ),
    ] = None,
    icons: Annotated[
        bool | None,
        typer.Option(
            '--icons/--no-icons',
            help='Nerd Font icons in listings (default: persistent prefs)',
            rich_help_panel=_SESSION,
        ),
    ] = None,
    debug: Annotated[
        bool,
        typer.Option(
            '--debug',
            '--traceback',
            help='print the full provider traceback when a command fails',
            rich_help_panel=_INSPECT,
        ),
    ] = False,
    interactive: Annotated[
        bool,
        typer.Option(
            '-i',
            '--interactive',
            help='start the sx shell instead of running one command',
            rich_help_panel=_SESSION,
        ),
    ] = False,
) -> None:
    """Set up the session; launch the shell when no command is given."""
    set_debug(debug)
    if icons is not None:
        set_icons(icons)
    coordinates = {
        'base': base,
        'bucket': bucket,
        'container': container,
        'account_name': account_name,
        'region': region,
        'endpoint': endpoint,
        'root': root,
        'kind': kind,
    }
    # every line typed in the shell re-enters this callback, carrying none of
    # the flags sx was started with; re-deriving the session there would swap
    # `sx --profile prod` for whatever the config file pins, one command in
    said = (
        provider_ is not None
        or profile is not None
        or environment is not None
        or any(value is not None for value in coordinates.values())
        or bool(set_)
        or cache
        or sandbox is not None
    )
    if said or (_session.fs is None and _session.pending is None):
        selected_profile, selected_environment = resolve_selection(
            profile, environment, provider_
        )
        _session.profile = selected_profile
        _session.environment = selected_environment
        overrides = build_overrides(
            resolve_provider(provider_, selected_profile),
            flags=coordinates,
            sets=set_ or [],
        )
        # rebuild on an explicit --provider, a coordinate override, or any
        # layer flag, else keep the persistent session (so cwd survives across
        # shell commands); layer flags replace the configured [[cli.layers]]
        if (
            provider_ is not None
            or selected_profile is not None
            or overrides
            or cache
            or sandbox is not None
        ):
            if cache or sandbox is not None:
                open_later(
                    lambda: apply_layers(
                        build_base(
                            provider_, overrides, selected_profile, selected_environment
                        ),
                        cache=cache,
                        cache_ttl=cache_ttl,
                        sandbox=sandbox,
                    )
                )
            else:
                open_later(
                    lambda: build_session(
                        provider_, overrides, selected_profile, selected_environment
                    )
                )

    if ctx.invoked_subcommand is None or interactive:
        from .shell import start_shell

        start_shell(_fs())


def _keep_transfer_buffers_returnable() -> None:
    """Stop glibc from hoarding freed transfer buffers (glibc only).

    glibc raises its mmap threshold to the size of the largest mmap'd block
    it has seen freed, and from then on carves same-sized allocations out of
    per-thread arenas, which are returned to the OS only when the free space
    happens to sit at the arena top. A finished bulk push measured 931 MB
    resident with about 30 MB of live Python objects behind it. Pinning the
    threshold keeps multi-MiB chunk buffers on mmap, where ``free`` hands
    them straight back, for one mmap/munmap pair per buffer. Best effort:
    anything other than glibc simply has nothing to pin.
    """
    with suppress(OSError, AttributeError):
        ctypes.CDLL('libc.so.6').mallopt(_M_MMAP_THRESHOLD, 128 * 1024)


def main() -> None:
    """Console-script entry point (`sx`); exits hard, without joining threads."""
    from storix.errors import ConfigurationError

    from .config import expand_alias, load_prefs

    _keep_transfer_buffers_returnable()
    code = 0
    try:
        prefs = load_prefs()
        if prefs.alias and len(sys.argv) > 1:
            sys.argv = [sys.argv[0], *expand_alias(sys.argv[1:], prefs.alias)]
        app()
    except ConfigurationError as exc:
        # a malformed or invalid config file: one clean line, no traceback
        err.print(f'[red]sx: {escape(str(exc))}[/red]')
        code = 1
    except SystemExit as exc:
        # os._exit below skips the interpreter's own SystemExit handling, so
        # a message-carrying exit (SystemExit('sx: ...'), which the config
        # loader and the override validator both raise) has to be printed
        # here or it would vanish and leave a bare exit status
        match exc.code:
            case None:
                code = 0
            case int() as status:
                code = status
            case message:
                err.print(f'[red]{escape(message)}[/red]')
                code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    # a cancelled push/pull leaves worker threads mid-upload that the
    # interpreter would otherwise join at shutdown (`bye` waiting on GiBs
    # of abandoned transfer); nothing here needs a graceful teardown
    os._exit(code)
