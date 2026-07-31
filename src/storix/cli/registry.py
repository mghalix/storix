"""The typer application every command module registers itself on.

A command module has to reference the app to register on it, and the app
has to import the command modules to have them registered, so whichever
module holds both is a cycle. This one holds the app and nothing else, and
imports nothing from the CLI, which is what lets the command modules keep
their decorators (ADR 0034 D2).

The help panels live here for the same reason: a command names its panel
beside the function that implements it, so the constant it names has to be
somewhere both can see.
"""

from __future__ import annotations

from typing import Final

import typer


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
