import mimetypes

import pytest

from storix import utils
from storix.types import StorixPath


def test_storixpath_maybe_file_and_maybe_dir() -> None:
    assert StorixPath('file.txt').maybe_file() is True
    assert StorixPath('file.txt').maybe_dir() is False

    assert StorixPath('dir').maybe_file() is False
    assert StorixPath('dir').maybe_dir() is True


def test_storixpath_guess_mimetype_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        utils,
        'guess_mimetype_from_path',
        lambda _path: 'application/x-storix',
    )

    assert StorixPath('anything.any').guess_mimetype() == 'application/x-storix'


def test_storixpath_guess_mimetype_unknown_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mimetypes, 'guess_type', lambda _p: (None, None))

    assert StorixPath('file.unknownext').guess_mimetype() is None


def test_path_kind_str_matches_enum():
    """PathKindStr must list exactly PathKind's values (sync guard).

    Add a PathKind case (e.g. a future symlink) and this fails until the
    PathKindStr Literal lists it too - so the ergonomic string form never
    drifts from the enum.
    """
    from typing import get_args

    from storix.enums import PathKind
    from storix.types import PathKindStr

    assert set(get_args(PathKindStr.__value__)) == {kind.value for kind in PathKind}


def test_a_trailing_separator_names_a_directory_whatever_the_suffix() -> None:
    """Given 'a.txt/', when its shape is judged, then it is a directory.

    The separator is the stronger signal: the check used to run after the
    argument became a pure path, which normalizes the separator away, so it
    never fired and a suffix decided on its own.
    """
    from storix.utils.paths import is_dir_approx, is_file_approx

    assert is_file_approx('a.txt/') is False
    assert is_dir_approx('a.txt/') is True
    assert is_file_approx('a.txt') is True
