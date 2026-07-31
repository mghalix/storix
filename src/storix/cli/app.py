"""Storix CLI: unix-like commands over any storix backend.

The root callback and the entry point. The commands themselves live in
``commands``, one module per help panel, and importing that package is
what registers them on the ``registry`` app. Session state and stack
access live in ``state``, presentation in ``render``, persistent
preferences in ``config``, the REPL in ``shell``.
"""

from __future__ import annotations

import ctypes
import os
import sys

from contextlib import suppress
from typing import Annotated, Final

import typer

from rich.markup import escape

# importing this package is what registers every command on the app
from . import commands  # noqa: F401  # pyright: ignore[reportUnusedImport]
from .registry import (
    _CONNECTION,  # pyright: ignore[reportPrivateUsage]
    _INSPECT,  # pyright: ignore[reportPrivateUsage]
    _SELECTION,  # pyright: ignore[reportPrivateUsage]
    _SESSION,  # pyright: ignore[reportPrivateUsage]
    app,
)
from .render import console, err
from .state import (
    _fs,  # pyright: ignore[reportPrivateUsage]
    _session,  # pyright: ignore[reportPrivateUsage]
    apply_layers,
    build_base,
    build_overrides,
    build_session,
    current_fs,
    open_later,
    resolve_provider,
    resolve_selection,
    set_debug,
    set_icons,
    use_fs,
)


__all__ = ['app', 'current_fs', 'main', 'use_fs']


_M_MMAP_THRESHOLD: Final[int] = -3
"""glibc ``mallopt`` parameter selecting the dynamic mmap threshold."""


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
