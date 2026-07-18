"""Persistent sx preferences: the prefs slice of ADR 0015's config file.

Connection config ("which backend, how to connect") stays shared at
``STORIX_*`` env / ``[tool.storix]`` and is read by ``get_storage``; this
module reads only CLI presentation preferences. The declarative
``[[layers]]`` stack DSL stays deferred per ADR 0015 - no layer config
lives here.

Precedence, strongest first: command-line flags (applied by the caller),
the nearest project config, ``STORIX_CLI_*`` env, the XDG user file,
defaults.
"""

from __future__ import annotations

import os
import tomllib

from functools import cache
from pathlib import Path
from typing import Any, Final, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError


_MISPLACED: Final[dict[str, str]] = {
    'home': 'STORIX_LOCAL_BASE / the provider settings (env or .env)',
    'base': 'STORIX_LOCAL_BASE (env or .env)',
    'account_name': 'STORIX_AZURE_* (env or .env)',
    'connection_string': 'STORIX_AZURE_* (env or .env)',
}
"""Credentials and anchors users reach for here. How to *connect* is
shared with the library (ADR 0015), so name their real home instead of
ignoring them. ``provider`` is the deliberate exception: see CliPrefs."""


class CliPrefs(BaseModel):
    """User preferences for sx (display and UX, not credentials)."""

    model_config = ConfigDict(extra='forbid')

    icons: bool = True
    """Decorate listings with Nerd Font icons (needs a patched font)."""

    dir_contents: bool = True
    """Show whether a directory is empty in flat listings, which a plain
    listing cannot know: it costs one extra listing per subdirectory (a
    round trip each on object stores, free under a cache layer). Set false
    to trade the distinction for one request per ``ls``."""

    provider: str | None = None
    """Which backend sx opens by default, overriding ``STORIX_PROVIDER``
    for this CLI only (``-p/--provider`` still wins). ADR 0022 admits this
    one connection key: "which provider do I explore by default" is a CLI
    habit, and forcing it through the shared env would drag a service's
    library sessions onto the same provider. Credentials stay shared."""

    layers: list[dict[str, Any]] = Field(default_factory=list)
    """Declarative layer stack (ADR 0015's ``[[layers]]`` DSL): ordered
    ``{name = ..., **kwargs}`` entries, innermost first. Applied to every
    session unless a layer flag (``--cache``/``--sandbox``) replaces the
    whole stack for that invocation. Names resolve in
    ``state.stack_from_prefs``."""


def _section(document: Any, *keys: str) -> dict[str, Any] | None:
    """Descend ``keys`` into a parsed TOML document; None when absent."""
    node: object = document
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return None
        node = cast('dict[str, Any]', node)[key]
    return cast('dict[str, Any]', node) if isinstance(node, dict) else None


def _read(file: Path) -> dict[str, Any]:
    """Parse a TOML file, dying with a readable message on bad syntax.

    Raises:
        SystemExit: If the file exists but is not valid TOML.
    """
    try:
        return tomllib.loads(file.read_text('utf-8'))
    except tomllib.TOMLDecodeError as exc:
        message = f'sx: invalid config {file}: {exc}'
        raise SystemExit(message) from exc
    except OSError:
        return {}


def _project_prefs() -> dict[str, Any]:
    """The nearest project config, ruff-style: walk upward from cwd.

    Per directory, ``storix.toml`` wins over ``.storix.toml`` (their
    ``[cli]`` table), else a ``pyproject.toml`` carrying
    ``[tool.storix.cli]``. The first file found anchors the project and
    stops the walk, even when it holds no CLI preferences.
    """
    cwd = Path.cwd()
    for directory in (cwd, *cwd.parents):
        for name in ('storix.toml', '.storix.toml'):
            file = directory / name
            if file.is_file():
                return _section(_read(file), 'cli') or {}
        pyproject = directory / 'pyproject.toml'
        if pyproject.is_file():
            found = _section(_read(pyproject), 'tool', 'storix', 'cli')
            if found is not None:
                return found
    return {}


def _user_prefs() -> dict[str, Any]:
    """The personal defaults: ``~/.config/storix/config.toml`` (XDG)."""
    base = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    file = base / 'storix' / 'config.toml'
    if not file.is_file():
        return {}
    return _section(_read(file), 'cli') or {}


def _env_prefs() -> dict[str, Any]:
    """``STORIX_CLI_*`` overrides (e.g. ``STORIX_CLI_ICONS=false``)."""
    prefs: dict[str, Any] = {}
    for field in CliPrefs.model_fields:
        if field == 'layers':  # a stack is not expressible as one env value
            continue
        value = os.environ.get(f'STORIX_CLI_{field.upper()}')
        if value is not None:
            prefs[field] = value
    return prefs


@cache
def load_prefs() -> CliPrefs:
    """Load and merge the persistent preferences (cached per process).

    Raises:
        SystemExit: If a config file is malformed, holds an unknown key,
            or a value has the wrong type. Connection settings that do not
            belong here are rejected naming where they do belong, so a
            misplaced key never silently does nothing.
    """
    merged: dict[str, Any] = {**_user_prefs(), **_env_prefs(), **_project_prefs()}
    for key, home in _MISPLACED.items():
        if key in merged:
            message = (
                f'sx: {key!r} is not a CLI preference - it is connection config, '
                f'shared with the library. Set it via {home}.'
            )
            raise SystemExit(message)
    try:
        return CliPrefs(**merged)
    except ValidationError as exc:
        known = ', '.join(CliPrefs.model_fields)
        message = f'sx: invalid CLI config ({exc}). Known preferences: {known}.'
        raise SystemExit(message) from exc
