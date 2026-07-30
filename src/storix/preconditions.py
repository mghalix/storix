"""Write preconditions: the optimistic-concurrency vocabulary (ADR 0033).

Flavor-neutral, so both the async source of truth and its generated sync
twin import the same sentinel and the same validator: a precondition is a
request argument, never a control-flow difference between flavors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from storix.enums import Capability
from storix.errors import UnsupportedOperationError


if TYPE_CHECKING:
    from storix.models import Capabilities
    from storix.types import EchoMode


IF_MATCH_ABSENT: Final[str] = '*'
"""Precondition sentinel: write only if nothing exists at the path yet.

The HTTP wildcard itself, because that is exactly what it becomes on the
wire (``If-None-Match: *``), and ``O_EXCL`` on local disk. It cannot
collide with a real validator: an ETag is a quoted string and a GCS
generation is a number, so neither is ever the bare ``*``."""


def validate_precondition(
    if_match: str | None, *, mode: EchoMode, capabilities: Capabilities
) -> None:
    """Validate a write precondition before a backend applies it.

    Returns immediately for the unconditional default, so a write that
    asks for nothing pays nothing.

    Each form is checked against its own capability, because they are
    separate guarantees: a store can create exclusively without being able
    to compare a version, and the reverse.

    Args:
        if_match: The requested precondition: ``None`` for an
            unconditional write, ``IF_MATCH_ABSENT`` for create-only, or
            a version read from a previous ``stat``.
        mode: The write mode the precondition would apply to.
        capabilities: What the receiving backend advertises.

    Raises:
        ValueError: If a precondition accompanies ``mode='a'``: an append
            is defined by the store's own concatenation semantics, and
            there is no validator for the file as it will be after other
            appends.
        UnsupportedOperationError: If the form asked for is not one this
            backend can apply atomically, naming the capability that is
            missing rather than the one that is present.
    """
    if if_match is None:
        return
    if mode == 'a':
        msg = "if_match cannot be combined with mode='a'"
        raise ValueError(msg)
    needed = (
        Capability.EXCLUSIVE_CREATE
        if if_match == IF_MATCH_ABSENT
        else Capability.CONDITIONAL_WRITES
    )
    if not capabilities.supports(needed):
        raise UnsupportedOperationError(needed)
