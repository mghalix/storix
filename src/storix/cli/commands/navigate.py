"""The commands that locate things: ls, pwd, cd, tree, find, exists."""

from __future__ import annotations

from collections import defaultdict
from functools import partial
from typing import TYPE_CHECKING, Annotated

import typer

from rich.columns import Columns
from rich.markup import escape
from rich.text import Text

from storix._sync._compat import concurrent
from storix.enums import PathKind
from storix.errors import StorageError

from ..config import load_prefs
from ..failure import _die  # pyright: ignore[reportPrivateUsage]
from ..icons import Icons
from ..listing import (
    _ListingSort,  # pyright: ignore[reportPrivateUsage]
    _arguments,  # pyright: ignore[reportPrivateUsage]
    _checked_stats,  # pyright: ignore[reportPrivateUsage]
    _listing_blocks,  # pyright: ignore[reportPrivateUsage]
    _long_table,  # pyright: ignore[reportPrivateUsage]
    _needs_stat,  # pyright: ignore[reportPrivateUsage]
    _scan,  # pyright: ignore[reportPrivateUsage]
    _sorted_entries,  # pyright: ignore[reportPrivateUsage]
)
from ..registry import (
    _NAVIGATE,  # pyright: ignore[reportPrivateUsage]
    app,
)
from ..render import (
    _count_label,
    console,
    dir_state_of,
    entry_decor,
    entry_label,
    human_size,
)
from ..state import (
    _fs,  # pyright: ignore[reportPrivateUsage]
    icons_enabled,
    stat_all,
)


if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from storix.models import DirEntry
    from storix.types import StorixPath


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


# --- queries ---


@app.command(rich_help_panel=_NAVIGATE)
def exists(paths: Annotated[list[str], typer.Argument()]) -> None:
    """Exit 0 only if every path exists."""
    fs = _fs()
    if not all(fs.exists(p) for p in paths):
        raise typer.Exit(1)
