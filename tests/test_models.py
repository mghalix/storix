import dataclasses
import datetime as dt

import pytest

from storix.enums import PathKind
from storix.models import Capabilities, Entry, FileProperties, RawStat


NOW = dt.datetime(2026, 7, 10, 12, 0, 0, tzinfo=dt.UTC)


def make_rawstat() -> RawStat:
    return RawStat(kind=PathKind.FILE, size=5, created=NOW, modified=NOW)


def test_entry_tuple_unpacking():
    name, is_dir, size = Entry('a.txt', is_dir=False)
    assert name == 'a.txt'
    assert is_dir is False
    assert size is None


def test_rawstat_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        make_rawstat().size = 6  # type: ignore[misc]


def test_rawstat_keyword_only():
    with pytest.raises(TypeError):
        RawStat(PathKind.FILE, 5, NOW, NOW)  # type: ignore[misc]


def test_rawstat_accessed_defaults_to_none():
    assert make_rawstat().accessed is None


def test_every_capability_defaults_to_off():
    """New capabilities must default to False so adding one is non-breaking
    for existing backends.
    """
    caps = Capabilities()
    for field in dataclasses.fields(Capabilities):
        assert getattr(caps, field.name) is False


def test_capabilities_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        Capabilities().content_type = True  # type: ignore[misc]


def test_fileproperties_kind_coerces_from_plain_string():
    """Legacy providers construct with kind='file'; pydantic must coerce
    the plain string into the PathKind member.
    """
    props = FileProperties(name='a', size=1, created=NOW, modified=NOW, kind='file')
    assert props.kind is PathKind.FILE


def test_fileproperties_kind_compares_equal_to_string():
    props = FileProperties(
        name='a',
        size=1,
        created=NOW,
        modified=NOW,
        kind=PathKind.DIRECTORY,
    )
    assert props.kind == 'directory'
