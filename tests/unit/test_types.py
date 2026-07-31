import mimetypes

import pytest

from storix import utils
from storix.types import StorixPath


def test_storixpath_maybe_file_and_maybe_dir() -> None:
    assert StorixPath('file.txt').maybe_file() is True
    assert StorixPath('file.txt').maybe_dir() is False

    assert StorixPath('dir').maybe_file() is False
    assert StorixPath('dir').maybe_dir() is True


def test_a_session_path_renders_with_forward_slashes_on_every_platform() -> None:
    """Given a joined session path, when rendered, then it uses '/'.

    StorixPath subclasses PurePosixPath so a backend key never depends on
    the host that wrote it. It was PurePath once, which on Windows renders
    every separator as a backslash and silently changes the shape of every
    stored key, while a POSIX-only test run stays green. The base class is
    asserted alongside the rendering because only the base class can fail
    the invariant on a POSIX host.
    """
    from pathlib import PurePosixPath

    assert issubclass(StorixPath, PurePosixPath)

    joined = StorixPath('/data') / 'nested' / 'file.txt'

    assert str(joined) == '/data/nested/file.txt'
    assert '\\' not in str(joined)
    # a backslash is an ordinary name character here, never a separator
    assert StorixPath('one\\two').parts == ('one\\two',)


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


def test_named_as_directory_reads_the_path_as_written() -> None:
    """Given a trailing separator, when the path is built, then it remembers.

    str() cannot answer this: the separator is normalized out of the
    rendered form, so the question is asked of the segments as given.
    """
    assert StorixPath('nodir/').named_as_directory is True
    assert StorixPath('nodir').named_as_directory is False
    assert str(StorixPath('nodir/')) == 'nodir'  # still normalized


def test_named_as_directory_survives_every_way_of_building_the_path() -> None:
    """Given the same name by several routes, when asked, then all agree."""
    from pathlib import PurePosixPath

    assert StorixPath(StorixPath('nodir/')).named_as_directory is True
    assert StorixPath(PurePosixPath('nodir/')).named_as_directory is True
    assert (StorixPath('a') / 'nodir/').named_as_directory is True
    assert StorixPath('a').joinpath('nodir/').named_as_directory is True


def test_a_derived_path_asserts_nothing() -> None:
    """Given a path derived from one, when asked, then it makes no claim.

    Only the segment someone wrote can carry the separator.
    """
    assert StorixPath('nodir/x').parent.named_as_directory is False
    assert (StorixPath('nodir/') / 'x').named_as_directory is False
