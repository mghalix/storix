"""The commands that change the store: mkdir, touch, echo, edit, rm, cp, mv."""

from __future__ import annotations

import sys
import tempfile

from pathlib import Path
from typing import Annotated

import typer

from storix.constants import DEFAULT_SOURCE_READ_SIZE
from storix.errors import PathNotFoundError, StorageError

from ..failure import _die  # pyright: ignore[reportPrivateUsage]
from ..registry import (
    _WRITE,  # pyright: ignore[reportPrivateUsage]
    app,
)
from ..render import close_line, console, launch_editor
from ..state import _fs  # pyright: ignore[reportPrivateUsage]


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
