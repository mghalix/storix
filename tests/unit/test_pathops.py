from pathlib import PurePosixPath as P

import pytest

from storix.pathops import expand_home, is_hidden, make_absolute, normalize, resolve


HOME = P('/home/u')
CWD = P('/home/u/work')


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('/a/../b', '/b'),  # the case the legacy mixin gets wrong
        ('/..', '/'),
        ('/../..', '/'),
        ('/a/./b/.', '/a/b'),
        ('/a/b/../../c', '/c'),
        ('/a/...', '/a/...'),  # three dots are a filename, not traversal
        ('/', '/'),
    ],
)
def test_normalize(raw: str, expected: str):
    assert str(normalize(raw)) == expected


def test_normalize_rejects_relative():
    with pytest.raises(ValueError, match='absolute'):
        normalize('a/b')


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('~', '/home/u'),
        ('~/x', '/home/u/x'),
        ('/a/~/b', '/a/~/b'),  # mid-path tilde is an ordinary name
        ('~user', '~user'),  # ~user expansion is documented as unsupported
        ('a/b', 'a/b'),  # no tilde: untouched
    ],
)
def test_expand_home(raw: str, expected: str):
    assert str(expand_home(raw, home=HOME)) == expected


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('x/y', '/home/u/work/x/y'),
        ('/abs/path', '/abs/path'),  # absolute passes through untouched
        ('.', '/home/u/work'),
    ],
)
def test_make_absolute(raw: str, expected: str):
    assert str(make_absolute(raw, cwd=CWD)) == expected


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('../x', '/home/u/x'),  # relative traversal from cwd
        ('~/../other', '/home/other'),  # home expansion feeds normalization
        ('docs/./a.txt', '/home/u/work/docs/a.txt'),
        ('/', '/'),
    ],
)
def test_resolve_pipeline(raw: str, expected: str):
    assert str(resolve(raw, cwd=CWD, home=HOME)) == expected


def test_resolve_is_idempotent():
    once = resolve('~/../x/./y', cwd=CWD, home=HOME)
    assert resolve(once, cwd=CWD, home=HOME) == once


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('.env', True),
        ('/a/.b/c.txt', False),  # hidden ancestor does not hide the entry
        ('/a/.hidden', True),
        ('/', False),
        ('.', False),
    ],
)
def test_is_hidden(raw: str, expected: bool):
    assert is_hidden(raw) is expected
