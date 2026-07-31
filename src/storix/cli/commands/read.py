"""The commands that report without changing anything: cat, stat, du, url."""

from __future__ import annotations

import sys

from collections import defaultdict
from functools import partial
from typing import TYPE_CHECKING, Annotated

import typer

from storix._sync._compat import concurrent
from storix.enums import PathKind
from storix.errors import StorageError

from ..failure import _die  # pyright: ignore[reportPrivateUsage]
from ..listing import (
    _arguments,  # pyright: ignore[reportPrivateUsage]
    _checked_stats,  # pyright: ignore[reportPrivateUsage]
)
from ..registry import (
    _READ,  # pyright: ignore[reportPrivateUsage]
    app,
)
from ..render import close_line, console, err, human_size
from ..state import _fs  # pyright: ignore[reportPrivateUsage]


if TYPE_CHECKING:
    from storix.types import StorixPath


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
