"""The one way an sx command reports a failure and stops.

Every command module shares it, so a provider error reads the same
whichever command hit it, and ``--debug`` prints the same chain. It sits
here rather than in ``registry``, which stays free of CLI imports, and
rather than in ``render``, which presents output rather than ending a run.
"""

# pyright: reportUnusedFunction=false
# every helper below is used by a sibling module rather than by this one,
# which is what pyright's file-private reading of a leading underscore
# cannot see. Splitting them across modules is the point (ADR 0034).

from __future__ import annotations

from typing import NoReturn

import typer

from rich.markup import escape

from .render import err
from .state import debug_enabled


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
