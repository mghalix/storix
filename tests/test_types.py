import mimetypes

import pytest

import storix.utils as utils

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
