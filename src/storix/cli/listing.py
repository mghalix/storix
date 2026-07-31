"""What ``ls`` and ``tree`` share: argument handling, ordering, columns.

The two commands list the same thing, so they resolve their arguments the
same way, order entries by the same key, and pay for the stats a listing
does not carry in the same batched shape. Keeping that here is what stops
the second command from growing its own answer (ADR 0034 D1).
"""

# pyright: reportUnusedFunction=false
# every helper below is used by a sibling module rather than by this one,
# which is what pyright's file-private reading of a leading underscore
# cannot see. Splitting them across modules is the point (ADR 0034).

from __future__ import annotations

from enum import auto
from functools import partial
from typing import TYPE_CHECKING

from rich.table import Table
from rich.text import Text

from storix._sync._compat import concurrent
from storix.enums import StorixEnum
from storix.errors import StorageError

from .failure import _die  # pyright: ignore[reportPrivateUsage]
from .render import human_size
from .state import empty_all, stat_all


if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from storix import Storix
    from storix.models import DirEntry, RawStat
    from storix.types import StorixPath


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
