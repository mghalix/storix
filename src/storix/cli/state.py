"""Session state and backend-stack access for the storix CLI.

One process-wide session holds the live filesystem (so cwd persists
across shell commands) and the display preferences; the helpers here walk
the layer stack and read directory entries at the port level. Everything
presentation-related lives in ``render``; the typer surface in ``app``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from storix import CacheLayer, SandboxLayer, cache as cache_op, get_storage, pathops
from storix.enums import PathKind
from storix.models import Entry


if TYPE_CHECKING:
    from collections.abc import Callable

    from storix import Storix
    from storix.backends import StorageBackend


_CLI_READ_CAP: Final[int] = 8 * 1024 * 1024
"""Cache cap for file content in the CLI (8 MiB), so `cat`ing a huge
file never balloons the session's memory."""


class _Session:
    """Holds the one live filesystem so state (cwd) persists across commands."""

    fs: Storix | None = None
    icons: bool | None = None
    """Whether listings decorate entries with icons; None = unresolved
    (falls back to the persistent preferences on first use)."""


_session = _Session()


def _fs() -> Storix:
    if _session.fs is None:
        _session.fs = stack_from_prefs(get_storage())
    return _session.fs


def current_fs() -> Storix:
    """The active session filesystem (public entry point for the shell)."""
    return _fs()


def use_fs(fs: Storix) -> None:
    """Point the session at ``fs`` (public entry point for the shell)."""
    _session.fs = fs


def icons_enabled() -> bool:
    """Whether listings decorate with icons (flag > config > default)."""
    if _session.icons is None:
        from .config import load_prefs

        _session.icons = load_prefs().icons
    return _session.icons


def set_icons(enabled: bool) -> None:  # noqa: FBT001 - a setter takes the value
    """Force icons on or off for this process (the flag override)."""
    _session.icons = enabled


def apply_layers(
    fs: Storix, *, cache: bool, cache_ttl: float | None, sandbox: str | None
) -> Storix:
    """Wrap the session in the requested layers - sandbox innermost."""
    if sandbox is not None:
        fs = fs.with_layer(SandboxLayer, root=sandbox)
    if cache:
        fs = _cached(fs, ttl=cache_ttl)
    return fs


def _cached(
    fs: Storix, *, ttl: float | None = None, max_bytes: int = _CLI_READ_CAP
) -> Storix:
    """The CLI cache stack: metadata + du + bounded read (ADR 0015)."""
    return fs.with_layer(
        CacheLayer,
        metadata=True,
        du=True,
        read=cache_op(max_bytes=max_bytes),
        ttl=ttl,
    )


def _sandboxed(fs: Storix, *, root: str) -> Storix:
    return fs.with_layer(SandboxLayer, root=root)


_LAYER_BUILDERS: Final[dict[str, Callable[..., Storix]]] = {
    'cache': _cached,
    'sandbox': _sandboxed,
}
"""Config-file layer names -> builders (the curated CLI set, ADR 0015)."""


def stack_from_prefs(fs: Storix) -> Storix:
    """Apply the configured ``[[cli.layers]]`` stack to a session.

    Entries apply in listed order, each wrapping the previous, so the
    last entry is outermost. A no-op with no configured layers.

    Raises:
        SystemExit: If an entry names an unknown layer or passes options
            its builder does not accept, naming the offending entry.
    """
    from .config import load_prefs

    for spec in load_prefs().layers:
        name = spec.get('name')
        builder = _LAYER_BUILDERS.get(name) if isinstance(name, str) else None
        if builder is None:
            known = ', '.join(sorted(_LAYER_BUILDERS))
            message = f'sx: unknown layer {name!r} in config (known: {known})'
            raise SystemExit(message)
        options = {key: value for key, value in spec.items() if key != 'name'}
        try:
            fs = builder(fs, **options)
        except TypeError as exc:
            message = f'sx: bad options for config layer {name!r}: {exc}'
            raise SystemExit(message) from exc
    return fs


def cache_layer(fs: Storix) -> CacheLayer | None:
    """The active ``CacheLayer`` in the session's stack, if any."""
    node: StorageBackend | None = fs.backend
    while node is not None:
        if isinstance(node, CacheLayer):
            return node
        node = getattr(node, '_inner', None)
    return None


def base_backend(fs: Storix) -> StorageBackend:
    """The innermost real backend under any layers (the actual provider)."""
    node: StorageBackend = fs.backend
    while (inner := getattr(node, '_inner', None)) is not None:
        node = inner
    return node


def prompt_label(fs: Storix) -> str:
    """Provider name annotated with active layers, e.g. ``AzureBackend(cache)``."""
    tags: list[str] = []
    node: StorageBackend | None = fs.backend
    while node is not None:
        if isinstance(node, CacheLayer):
            tags.append('cache')
        elif isinstance(node, SandboxLayer):
            tags.append('sandbox')
        node = getattr(node, '_inner', None)
    base = type(base_backend(fs)).__name__
    return f'{base}({", ".join(tags)})' if tags else base


# op name -> the CLI verbs it accelerates, for the layer summary
_CACHE_VERBS = {'metadata': 'ls/stat', 'du': 'du', 'read': 'cat', 'url': 'url'}


def layer_summary(fs: Storix) -> str | None:
    """A one-line description of the active layer stack (outermost first)."""
    parts: list[str] = []
    node: StorageBackend | None = fs.backend
    while node is not None:
        if isinstance(node, CacheLayer):
            verbs = '/'.join(_CACHE_VERBS[o] for o in node.enabled if o in _CACHE_VERBS)
            via = '+'.join(node.store_names())
            parts.append(f'cache {verbs} via {via}')
        elif isinstance(node, SandboxLayer):
            parts.append(f'sandbox {node.to_real("/")}')  # public audit handle
        node = getattr(node, '_inner', None)
    return ' · '.join(parts) if parts else None


def list_entries(
    fs: Storix, path: str | None = None, *, all: bool = False
) -> list[Entry]:
    """Sorted directory entries with kind info, straight from the port.

    ``fs.ls`` flattens the port's ``Entry`` DTO into bare paths; the CLI
    needs ``is_dir`` (and any free ``size``) to decorate output without a
    stat call per entry, so it asks the backend stack directly. Mirrors
    ``ls`` semantics: listing a file returns the file itself, and hidden
    entries are excluded unless ``all`` is set.

    Args:
        fs: The session to list through (its full layer stack applies).
        path: Directory (or file) to list; the session cwd when None.
        all: Include hidden (dot-prefixed) entries.

    Raises:
        StorageError: Propagated from the backend (e.g. a missing path).
    """
    target = fs.resolve(path)
    raw = fs.backend.stat(target)
    if raw.kind is PathKind.FILE:
        return [Entry(target.name, is_dir=False, size=raw.size)]
    entries = (
        entry
        for entry in fs.backend.list_dir(target)
        if all or not pathops.is_hidden(entry.name)
    )
    return sorted(entries, key=lambda entry: entry.name)
