"""Tab candidates for the prompt: command names, backend paths, host paths."""

# pyright: reportUnusedClass=false
# pyright: reportUnusedFunction=false
# every helper below is used by a sibling module rather than by this one,
# which is what pyright's file-private reading of a leading underscore
# cannot see. Splitting them across modules is the point (ADR 0034).

from __future__ import annotations

from typing import TYPE_CHECKING

from prompt_toolkit.completion import Completer, Completion

from ..config import load_prefs
from ..icons import lookup_entry_decor
from ..render import entry_decor
from ..state import current_fs
from .parsing import (
    _escape_shell_path,  # pyright: ignore[reportPrivateUsage]
    _parse_completion_context,  # pyright: ignore[reportPrivateUsage]
)


if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from prompt_toolkit.completion import CompleteEvent
    from prompt_toolkit.document import Document


def _completion_matches(name: str, fragment: str) -> bool:
    """Whether ``name`` completes ``fragment``, per ``[cli] completion_case``.

    ``smart`` (the default) ignores case only until the user types an
    uppercase letter - at which point they clearly meant it.
    ``insensitive`` always ignores it, ``sensitive`` is the plain prefix
    test.

    Args:
        name: The candidate entry name.
        fragment: The word fragment the user has typed.
    """
    mode = load_prefs().completion_case
    if mode == 'insensitive' or (
        mode == 'smart' and not any(char.isupper() for char in fragment)
    ):
        return name.lower().startswith(fragment.lower())
    return name.startswith(fragment)


def _completion_order(name: str) -> tuple[str, str]:
    """Sort key for completions: the order a shell's own completion shows.

    Leading punctuation is ignored for the primary comparison, so
    ``_proto.py`` files between ``opendal.py`` and ``__pycache__`` rather
    than ahead of every letter. That is glibc's collation under a UTF-8
    locale, which is what coreutils `ls` and a zsh completion list both
    follow, and it is what stops a directory of dunder modules from opening
    with a block of underscores.

    Deliberately not the key `ls` uses: that listing follows eza, which
    files punctuation first, and the two are different views with different
    precedents rather than one inconsistency.

    Args:
        name: The entry name being ordered.
    """
    return name.lstrip('_.-').lower(), name.lower()


def _get_remote_completions(word: str) -> Iterator[Completion]:
    """Yield remote backend completions for `word`."""
    fragment = word.rpartition('/')[2]
    parent = word[: len(word) - len(fragment)]  # '' or ends with '/'
    try:
        entries = sorted(
            current_fs().scandir(parent or None, all=fragment.startswith('.')),
            key=lambda entry: _completion_order(entry.name),
        )
    except Exception:  # noqa: BLE001 - completion must never break the prompt
        return
    for entry in entries:
        if not _completion_matches(entry.name, fragment):
            continue
        icon = entry_decor(entry)[0]
        slash = '/' if entry.is_dir else ''
        label = f'{icon} {entry.name}{slash}' if icon else f'{entry.name}{slash}'
        escaped_name = _escape_shell_path(entry.name)
        yield Completion(
            f'{parent}{escaped_name}{slash}',
            start_position=-len(word),
            display=label,
            style='fg:ansibrightblue bold' if entry.is_dir else '',
        )


def _get_local_completions(word: str) -> Iterator[Completion]:
    """Yield local host machine completions for `word` (starting from cwd)."""
    from pathlib import Path

    if word == '~':
        yield Completion(
            '~/', start_position=-1, display='~/', style='fg:ansibrightblue bold'
        )
        return

    fragment = word.rpartition('/')[2]
    parent_str = word[: len(word) - len(fragment)]  # '' or ends with '/'

    target_dir = Path.cwd() if not parent_str else Path(parent_str).expanduser()
    fragment = word.rpartition('/')[2]
    parent_str = word[: len(word) - len(fragment)]  # '' or ends with '/'

    if not parent_str:
        target_dir = Path.cwd()
    elif parent_str.startswith('~/'):
        target_dir = Path.home() / parent_str[2:]
    else:
        target_dir = Path(parent_str)

    try:
        if not target_dir.is_dir():
            return
        entries = sorted(target_dir.iterdir(), key=lambda p: _completion_order(p.name))
    except Exception:  # noqa: BLE001 - completion must never break prompt
        return

    show_hidden = fragment.startswith('.')
    for path in entries:
        name = path.name
        if not show_hidden and name.startswith('.'):
            continue
        if not _completion_matches(name, fragment):
            continue

        try:
            is_dir = path.is_dir()
        except OSError:
            is_dir = False

        slash = '/' if is_dir else ''
        icon, _ = lookup_entry_decor(name, is_dir=is_dir)
        label = f'{icon} {name}{slash}' if icon else f'{name}{slash}'
        escaped_name = _escape_shell_path(name)

        yield Completion(
            f'{parent_str}{escaped_name}{slash}',
            start_position=-len(word),
            display=label,
            style='fg:ansibrightblue bold' if is_dir else '',
        )


class _ShellCompleter(Completer):
    """Tab candidates: command names first, context-aware path completion after.

    - push <1> <2>: <1> local host machine, <2> remote backend
    - pull <1> <2>: <1> remote backend, <2> local host machine
    - all other commands: remote backend paths
    """

    def __init__(self, commands: Mapping[str, str]) -> None:
        self._commands = dict(sorted(commands.items()))

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterator[Completion]:
        """Yield completions for the word before the cursor."""
        text = document.text_before_cursor
        cmd, arg_index, word = _parse_completion_context(text)

        if arg_index == 0:
            yield from (
                Completion(name, start_position=-len(word), display_meta=meta)
                for name, meta in self._commands.items()
                if name.startswith(word)
            )
            return

        if cmd == 'push':
            use_local = arg_index == 1
        elif cmd == 'pull':
            use_local = arg_index >= 2  # noqa: PLR2004
        else:
            use_local = False

        if use_local:
            yield from _get_local_completions(word)
        else:
            yield from _get_remote_completions(word)
