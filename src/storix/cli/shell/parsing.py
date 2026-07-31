"""Turning a typed line into structure: quotes, tokens, redirects, escapes.

Knows nothing about the session or the terminal, which is what makes it
the place an operator split (``&&``, ``||``, ``;``) can be added without
touching completion or rendering (ADR 0034 D3).
"""

# pyright: reportUnusedFunction=false
# every helper below is used by a sibling module rather than by this one,
# which is what pyright's file-private reading of a leading underscore
# cannot see. Splitting them across modules is the point (ADR 0034).

from __future__ import annotations

import shlex

from typing import Final

from ..config import expand_alias


_WILDCARDS: Final[str] = '*?'
"""The glob metacharacters a prompt token is scanned for.

``**`` is two of the first; the across-directories meaning of the pair
comes from the core glob, which is what does the matching."""

_QUOTED: Final[str] = '\x00'
"""Marks a wildcard the user quoted, so tokenizing cannot lose the quotes.

``shlex.split`` strips quotes, so ``'*.txt'`` and ``*.txt`` reach the
tokens as one string and a pattern that was protected is indistinguishable
from one that was meant. Marking the protected wildcards before the split
and dropping the marks after keeps the two apart without a second
tokenizer. A control character because no prompt line can contain one."""


_UNESCAPED_PUNCTUATION: Final[str] = '_@%+=:,./-'
"""The ASCII punctuation a completed name may carry with no backslash.

The set `shlex.quote` calls safe, which is the punctuation no tokenizer,
glob, or redirect operator reads as syntax."""


def _escape_shell_path(name: str) -> str:
    """Quote one path component so tokenizing the line returns it unchanged.

    The contract is the round trip: `_parse_input` on what this produces
    yields exactly `name`. That is stated as a rule (backslash every ASCII
    character that is neither alphanumeric nor `_UNESCAPED_PUNCTUATION`)
    rather than a list of the characters noticed so far, because a list is
    silently short until a filename finds the gap. A glob wildcard was one
    such gap: `report*.md` inserted bare is a pattern over the directory
    rather than the file that was picked.

    A literal backslash is why this cannot be a chain of replacements. It has
    to be escaped too, and escaping any other character first makes the
    backslashes just inserted indistinguishable from the one in the name, so
    a name carrying both a backslash and a space arrived as two tokens.

    Non-ASCII is left alone. It is syntax to no tokenizer, and a backslash
    before every accent or emoji only makes the line unreadable.

    Args:
        name: An entry name, or a POSIX path of them, as the backend or the
            host filesystem reports it. The `/` separator is safe punctuation
            and stays unescaped. A Windows host separator never reaches here,
            because a directory prefix the user typed is passed through as
            typed rather than escaped.

    Returns:
        The name as a single shell token.
    """
    return ''.join(
        char
        if char.isalnum() or not char.isascii() or char in _UNESCAPED_PUNCTUATION
        else f'\\{char}'
        for char in name
    )


def _parse_completion_context(text_before_cursor: str) -> tuple[str, int, str]:
    """Parse text before cursor into (cmd_name, arg_index, current_word).

    arg_index is the 1-based index of the argument being typed:
    - 0 if the cursor is on the command name itself
    - 1 for the first argument after the command
    - 2 for the second argument after the command, etc.

    A trailing unescaped space means a fresh (empty) argument has begun, so the
    index counts every completed token. An escaped trailing space (part of a
    completed path that contains a space) still belongs to the last token, so
    the index stays on that token.
    """
    if not text_before_cursor.lstrip():
        return '', 0, ''
    try:
        tokens = shlex.split(text_before_cursor)
    except ValueError:
        tokens = text_before_cursor.split()
    if not tokens:
        return '', 0, ''

    ends_with_new_arg = text_before_cursor[-1].isspace() and not (
        len(text_before_cursor) > 1 and text_before_cursor[-2] == '\\'
    )
    cmd = tokens[0]
    if ends_with_new_arg:
        return cmd, len(tokens), ''
    return cmd, len(tokens) - 1, tokens[-1]


def _split_redirect(argv: list[str]) -> tuple[list[str], str | None, bool]:
    """Split a trailing ``> path`` / ``>> path`` off a command line.

    Redirection only, not pipes: the target is a backend path and the
    operator is an output sink, which needs no process model. ``cmd1 |
    cmd2`` does, and is deliberately not here.

    Args:
        argv: The tokenized line, after alias expansion.

    Returns:
        The command's own argv, the redirect target (None when there is
        no operator), and whether it appends.

    Raises:
        ValueError: If the operator has no target, or more than one.
    """
    for i, token in enumerate(argv):
        if not token.startswith('>'):
            continue
        append = token.startswith('>>')
        attached = token[2:] if append else token[1:]
        rest = argv[i + 1 :]
        target = attached or (rest.pop(0) if rest else '')
        if not target or rest:
            msg = 'redirect needs exactly one target: cmd > path'
            raise ValueError(msg)
        return argv[:i], target, append
    return argv, None, False


def _mark_quoted(line: str) -> str:
    """Mark every quoted or escaped wildcard in ``line`` as a literal.

    Runs before ``shlex.split`` because the split is where the quotes go:
    the scan tracks only quote and escape state, which is all that decides
    whether a wildcard was protected, and leaves the tokenizing to shlex.

    Args:
        line: The line as typed.
    """
    marked: list[str] = []
    quote = ''
    escaped = False
    for char in line:
        if (escaped or quote) and char in _WILDCARDS:
            marked.append(_QUOTED)
        if escaped:
            escaped = False
        elif char == '\\' and quote != "'":
            escaped = True
        elif quote:
            quote = '' if char == quote else quote
        elif char in '\'"':
            quote = char
        marked.append(char)
    return ''.join(marked)


def _unmark(token: str) -> str:
    """Drop the literal marks, leaving the token as it was written."""
    return token.replace(_QUOTED, '')


def _parse_input(line: str, aliases: dict[str, str]) -> list[str]:
    """Parse a prompt line into tokenized argv, expanding aliases if defined.

    The tokens carry the literal marks ``_mark_quoted`` left, which
    ``_expand_globs`` reads and removes.
    """
    argv = shlex.split(_mark_quoted(line))
    return expand_alias(argv, aliases) if (argv and aliases) else argv


def _last_word(text: str) -> str:
    """The trailing word of ``text``, exactly as it was typed.

    The extent to replace on the line, which the tokens cannot give: they
    have already lost the quotes and escapes the buffer still holds. Split on
    the last space the user did not escape, so a path written with an escaped
    space stays one word.
    """
    for index in range(len(text) - 1, -1, -1):
        if text[index].isspace() and text[index - 1 : index] != '\\':
            return text[index + 1 :]
    return text
