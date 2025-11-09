from __future__ import annotations


class StorixError(Exception):
    """Base class for Storix-specific exceptions."""


class PathNotFoundError(FileNotFoundError, ValueError, StorixError):
    """Raised when a logical Storix path does not exist.

    Subclasses both FileNotFoundError and ValueError to preserve backward
    compatibility with existing callers/tests that catch ValueError while also
    allowing users to catch the more specific FileNotFoundError.
    """

