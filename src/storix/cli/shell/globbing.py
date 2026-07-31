"""Glob patterns at the prompt: detecting them, matching them, expanding them.

The outer shell cannot expand a backend path, so the prompt does it: once
over the whole line before it runs, and once on the line itself when Tab
is pressed on a pattern (ADR 0034 D3).
"""

# pyright: reportUnusedFunction=false
# every helper below is used by a sibling module rather than by this one,
# which is what pyright's file-private reading of a leading underscore
# cannot see. Splitting them across modules is the point (ADR 0034).

from __future__ import annotations

import posixpath
import shlex

from itertools import takewhile
from typing import TYPE_CHECKING

from storix.errors import StorageError

from ..state import current_fs
from .parsing import (
    _QUOTED,  # pyright: ignore[reportPrivateUsage]
    _WILDCARDS,  # pyright: ignore[reportPrivateUsage]
    _escape_shell_path,  # pyright: ignore[reportPrivateUsage]
    _last_word,  # pyright: ignore[reportPrivateUsage]
    _mark_quoted,  # pyright: ignore[reportPrivateUsage]
    _unmark,  # pyright: ignore[reportPrivateUsage]
)


if TYPE_CHECKING:
    from collections.abc import Sequence

    from prompt_toolkit.buffer import Buffer


def _is_pattern(token: str) -> bool:
    """Whether ``token`` holds a wildcard that was not quoted."""
    return any(
        char in _WILDCARDS and token[index - 1 : index] != _QUOTED
        for index, char in enumerate(token)
    )


def _match(pattern: str) -> list[str]:
    """Match ``pattern`` against the session, as sorted absolute paths.

    The leading wildcard-free segments become the glob's base rather than
    part of the pattern it walks: an absolute pattern is matched against a
    path relative to that base and so could never match from the cwd, and
    ``sub/*.md`` walks ``sub`` instead of every sibling of it.

    Hidden entries join the candidates only when the pattern's last segment
    asks for them with a leading dot, which is the pathlib and shell rule.

    The core glob walks the whole subtree below the base and tests every
    entry, so a shallow pattern still costs a full recursive listing. A
    bounded walk belongs in that glob, where every caller gets it, rather
    than in a second matcher here.

    Args:
        pattern: One prompt token, known to hold an unquoted wildcard.

    Returns:
        The matching paths in sorted order, empty when nothing matched.
    """
    segments = pattern.split('/')
    fixed = list(takewhile(lambda segment: not _is_pattern(segment), segments))
    base = '/'.join(fixed) or ('/' if pattern.startswith('/') else None)
    tail = '/'.join(segments[len(fixed) :])
    try:
        matches = current_fs().glob(
            tail, base, all=tail.rpartition('/')[2].startswith('.')
        )
        return sorted(str(path) for path in matches)
    except StorageError:
        # a base that is not there is a pattern matching nothing rather than
        # a line that failed, which is what a shell reports for `nosuch/*`
        return []


def _expand_globs(argv: list[str]) -> list[str]:
    """Replace the glob patterns in ``argv`` with what they match.

    The outer shell cannot do this: the paths are in the backend, so a
    pattern typed at the prompt reaches the command untouched and the
    command reports a path that never existed. Expanding the whole line here
    instead of per command is what makes it uniform, and is where a shell
    does it too.

    The command name and any option token are left alone, because a pattern
    is only a pattern in a path position: a wildcard in the command name is
    a command that does not exist, which Click says better than a matcher
    can, and a leading ``-`` is an option however it is spelled. A redirect
    target is already split off by the time this runs and stays literal for
    the same reason: it names a file being written, not one to be found.

    Args:
        argv: The tokenized line, with any redirect already split off.

    Returns:
        The line with each pattern replaced by its matches in argument
        order, and every quoted wildcard restored as a plain character.

    Raises:
        ValueError: If a pattern matches nothing.
    """
    if not argv:
        return argv
    expanded = [_unmark(argv[0])]
    for token in argv[1:]:
        if token.startswith('-') or not _is_pattern(token):
            expanded.append(_unmark(token))
            continue
        matches = _match(token)
        if not matches:
            msg = f'no matches: {token}'
            raise ValueError(msg)
        expanded.extend(matches)
    return expanded


def _pattern_at_cursor(text: str) -> tuple[str, str] | None:
    """The word at the cursor and the pattern it holds, or None.

    Returns the word as typed together with the token it tokenizes to, which
    is the form ``_match`` wants (marks included, as ``_expand_globs`` passes
    them).

    None means Tab completes instead of expanding, which is every word
    without an unquoted wildcard, plus three that hold one and are still not
    patterns: a word carrying a quote (the quotes are what make the wildcard
    a plain character, and a matcher that never sees them cannot tell), the
    command name (a wildcard there is a command that does not exist, which
    Click says better than a matcher can), and an option (a leading ``-`` is
    an option however it is spelled). The last two are the positions
    ``_expand_globs`` leaves alone on Enter as well.

    Args:
        text: The line up to the cursor.
    """
    word = _last_word(text)
    if not word or word.startswith('-') or '"' in word or "'" in word:
        return None
    if not text[: len(text) - len(word)].strip():
        return None
    try:
        tokens = shlex.split(_mark_quoted(word))
    except ValueError:
        # an unfinished escape is a word still being typed, not a pattern
        return None
    if not tokens or not _is_pattern(tokens[0]):
        return None
    return word, tokens[0]


def _expansion(matches: Sequence[str], pattern: str) -> str:
    """The text ``matches`` become on the line, at the depth as typed.

    ``_match`` answers in absolute paths, and putting those back on the line
    would lose what the user chose to write: ``ls *.md`` in a deep directory
    would grow into a line of full paths for names the cwd already fixes.
    Only a pattern written absolute expands to absolute names, which is what
    a shell shows.

    The names are escaped rather than quoted, so one holding a space survives
    the tokenizer the line goes back through, and a trailing space follows
    several of them: an expansion to more than one name is finished, where a
    single one is often a path being completed a component at a time.

    Args:
        matches: The absolute paths the pattern matched.
        pattern: The token that matched them, as it was typed.
    """
    if pattern.startswith('/'):
        names = list(matches)
    else:
        cwd = str(current_fs().pwd())
        names = [posixpath.relpath(match, cwd) for match in matches]
    line = ' '.join(_escape_shell_path(name) for name in names)
    return f'{line} ' if len(names) > 1 else line


def _expand_on_line(buffer: Buffer) -> None:
    """Replace the pattern at the cursor with what it matches, in place.

    Seeing the names before the line runs is the point: an expansion that
    only ever happened on Enter leaves the user to trust that ``rm *.tmp``
    selected what they meant.

    A pattern that matches nothing is left alone, pattern and all, rather
    than emptied. zsh does the same, and the alternative destroys the one
    thing the user can correct.

    Args:
        buffer: The prompt buffer whose line is rewritten.
    """
    at_cursor = _pattern_at_cursor(buffer.document.text_before_cursor)
    if at_cursor is None:
        return
    word, pattern = at_cursor
    matches = _match(pattern)
    if not matches:
        return
    buffer.delete_before_cursor(len(word))
    buffer.insert_text(_expansion(matches, pattern))
