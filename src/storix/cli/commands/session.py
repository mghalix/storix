"""The commands about the session itself: whereami, provision, shell."""

from __future__ import annotations

from storix.config import resolve_profile
from storix.errors import StorageError

from ..failure import _die  # pyright: ignore[reportPrivateUsage]
from ..registry import (
    _SETUP,  # pyright: ignore[reportPrivateUsage]
    app,
)
from ..render import console
from ..state import (
    _fs,  # pyright: ignore[reportPrivateUsage]
    layer_summary,
    selection,
)


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
    from ..shell import start_shell

    start_shell(_fs())
