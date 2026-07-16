"""The house-style DTO decorator: frozen, slotted, keyword-only dataclasses.

Internal. Public models (the validated pydantic surface) live in
``storix.models``; this decorator marks the other kind of record.
"""

import dataclasses

from typing import dataclass_transform


@dataclass_transform(frozen_default=True, kw_only_default=True)
def dto[T](cls: type[T]) -> type[T]:
    """Storix house-style DTO: a frozen, slotted, keyword-only dataclass.

    One decorator instead of a repeated ``@dataclasses.dataclass(frozen=True,
    slots=True, kw_only=True)`` on every DTO, so the options cannot drift per
    class (ADR 0012). Deliberately not named ``model``: storix models are the
    validated pydantic surface (``StorixBaseModel``), while DTOs are trusted
    records storix constructs internally and never validates. ``slots=True``
    rebuilds the class, so the result is a new class, not ``cls`` mutated.

    Args:
        cls: The class to rebuild as a house-style dataclass.

    Returns:
        The frozen, slotted, keyword-only dataclass built from ``cls``.
    """
    return dataclasses.dataclass(frozen=True, slots=True, kw_only=True)(cls)
