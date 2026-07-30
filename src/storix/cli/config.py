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
import shlex

from functools import cache
from typing import Any, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from storix.config import find_project_config, find_user_config


_GLOBAL_VALUE_OPTIONS: Final[set[str]] = {
    '-p',
    '--provider',
    '--cache-ttl',
    '--sandbox',
    '--base',
    '--bucket',
    '--container',
    '--account-name',
    '--region',
    '--endpoint',
    '--root',
    '--kind',
    '--set',
}


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

    completion_case: Literal['sensitive', 'insensitive', 'smart'] = 'smart'
    """How tab completion matches what you have typed. ``smart`` (the
    default) ignores case until you type an uppercase letter, then matches
    exactly - the fzf/vim rule that modern shells settled on, because a
    lowercase prefix is almost never a statement about case.
    ``insensitive`` ignores case always, ``sensitive`` never does."""

    editor: str | None = None
    """Command that ``sx edit`` and ``sx config edit`` open files with,
    ahead of ``$VISUAL`` and ``$EDITOR``. Set it when the environment has
    no editor to inherit (a fresh Windows shell) or when sx should use a
    different one from the rest of the system."""

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

    alias: dict[str, str] = Field(default_factory=dict)
    """Command shortcuts (e.g. ``{"lt": "tree --level=2", "la": "ls -a"}``).
    Expanded in one-shot CLI commands and interactive shell inputs when the
    subcommand matches an alias key."""


def _normalize_prefs(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize alias/aliases key variations in preferences dict."""
    data = dict(raw)
    if 'aliases' in data:
        aliases = data.pop('aliases')
        if isinstance(aliases, dict):
            existing = data.get('alias')
            data['alias'] = (
                {**aliases, **existing} if isinstance(existing, dict) else aliases
            )
    return data


def _extract_file_prefs(doc: dict[str, Any]) -> dict[str, Any]:
    """Extract CLI preferences from a discovered config document.

    Checks the ``[cli]`` table first; if absent, extracts top-level CLI
    fields (leaving provider sections to the library loader). Top-level
    ``[alias]`` / ``[aliases]`` tables are merged in as compatibility
    spellings. Provider tables (``[local]``, ``[s3]``, ...) are ignored
    here: they are connection config the library loader owns.
    """
    cli_table = doc.get('cli')
    prefs: dict[str, Any]
    if isinstance(cli_table, dict):
        prefs = cast('dict[str, Any]', cli_table)
    else:
        prefs = {
            k: v
            for k, v in doc.items()
            if k in CliPrefs.model_fields or k in ('alias', 'aliases')
        }

    for key in ('alias', 'aliases'):
        node = doc.get(key)
        if isinstance(node, dict):
            table = cast('dict[str, Any]', node)
            existing = prefs.get(key)
            if isinstance(existing, dict):
                prefs[key] = {**table, **cast('dict[str, Any]', existing)}
            else:
                prefs[key] = dict(table)

    return _normalize_prefs(prefs)


def _project_prefs() -> dict[str, Any]:
    """The ``[cli]`` slice of the nearest project config (shared discovery)."""
    disc = find_project_config()
    return _extract_file_prefs(disc.data) if disc is not None else {}


def _user_prefs() -> dict[str, Any]:
    """The ``[cli]`` slice of the XDG user config (shared discovery)."""
    disc = find_user_config()
    return _extract_file_prefs(disc.data) if disc is not None else {}


def _env_prefs() -> dict[str, Any]:
    """``STORIX_CLI_*`` overrides (e.g. ``STORIX_CLI_ICONS=false``)."""
    prefs: dict[str, Any] = {}
    for field in CliPrefs.model_fields:
        if field in {'layers', 'alias'}:  # complex structures not expressible in env
            continue

        value = os.environ.get(f'STORIX_CLI_{field.upper()}')
        if value is not None:
            prefs[field] = value
    return prefs


@cache
def load_prefs() -> CliPrefs:
    """Load and merge the persistent preferences (cached per process).

    Provider tables (``[local]``, ``[s3]``, ...) are now legal config the
    library loader owns, so an unknown key inside ``[cli]`` is simply an
    unknown preference (``extra='forbid'``): connection settings belong in
    a provider table or the ``STORIX_*`` environment.

    Raises:
        SystemExit: If a config file holds an unknown ``[cli]`` key or a
            value has the wrong type.
        ConfigurationError: If a discovered file is malformed or holds an
            unknown top-level table (raised by the shared loader).
    """
    merged: dict[str, Any] = {**_user_prefs(), **_env_prefs(), **_project_prefs()}
    try:
        return CliPrefs(**merged)
    except ValidationError as exc:
        known = ', '.join(CliPrefs.model_fields)
        message = f'sx: invalid CLI config ({exc}). Known preferences: {known}.'
        raise SystemExit(message) from exc


def expand_alias(argv: list[str], aliases: dict[str, str]) -> list[str]:
    """Expand a command alias in ``argv`` when the subcommand matches an alias key.

    Alias expansion applies strictly to the subcommand position (the first non-option
    token, or token after root options). Positional arguments (e.g. filenames in
    ``touch lt``) are never expanded.

    Args:
        argv: Command line arguments list (e.g. ``sys.argv[1:]`` or REPL tokens).
        aliases: Mapping of alias name to target string (e.g. ``{"lt": "tree -L 2"}``).

    Returns:
        New arguments list with the subcommand expanded if it matched an alias.
    """
    if not argv or not aliases:
        return list(argv)

    cmd_idx: int | None = None
    i = 0
    if argv[i] == 'sx' or argv[i].endswith('/sx'):
        i += 1

    while i < len(argv):
        token = argv[i]
        if token in _GLOBAL_VALUE_OPTIONS:
            i += 2  # skip option and its value argument
            continue
        if token.startswith('-'):
            i += 1  # skip boolean flag option
            continue
        cmd_idx = i
        break

    if cmd_idx is None or cmd_idx >= len(argv):
        return list(argv)

    subcommand = argv[cmd_idx]
    if subcommand not in aliases:
        return list(argv)

    seen: set[str] = set()
    current_tokens: list[str] = [subcommand]

    while current_tokens and current_tokens[0] in aliases:
        cmd_name = current_tokens[0]
        if cmd_name in seen:
            break
        seen.add(cmd_name)
        target = aliases[cmd_name]
        try:
            expanded = shlex.split(target)
        except ValueError:
            break
        if not expanded:
            break
        current_tokens = expanded + current_tokens[1:]

    return argv[:cmd_idx] + current_tokens + argv[cmd_idx + 1 :]
