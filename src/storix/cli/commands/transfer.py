"""The commands that move bytes between the local disk and a backend."""

from __future__ import annotations

import signal
import threading

from contextlib import contextmanager
from functools import partial
from typing import TYPE_CHECKING, Annotated, NoReturn

import typer

from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TransferSpeedColumn,
)

from storix import ObservabilityLayer, TransferEvent
from storix._sync._compat import concurrent
from storix.config import StorixSettings
from storix.constants import DEFAULT_CONCURRENCY, DEFAULT_TRANSFER_RANGES
from storix.enums import PathKind
from storix.errors import StorageError, TransferStoppedError

from ..failure import _die  # pyright: ignore[reportPrivateUsage]
from ..registry import (
    _TRANSFER,  # pyright: ignore[reportPrivateUsage]
    app,
)
from ..render import _count_label, console
from ..state import (
    _fs,  # pyright: ignore[reportPrivateUsage]
    stat_all,
)


if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path, PurePosixPath
    from types import FrameType

    from storix import Storix
    from storix.types import StorixPath


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
