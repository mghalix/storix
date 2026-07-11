import dataclasses

from storix.enums import Capability, PathKind
from storix.models import Capabilities


def test_capability_members_mirror_capabilities_fields():
    """The enum and the flags dataclass must never drift apart."""
    members = {member.value for member in Capability}
    fields = {field.name for field in dataclasses.fields(Capabilities)}
    assert members == fields


def test_pathkind_values():
    assert PathKind.FILE == 'file'
    assert PathKind.DIRECTORY == 'directory'


def test_pathkind_members_are_strings():
    """StrEnum contract: members are usable anywhere a str is expected."""
    assert isinstance(PathKind.FILE, str)
    assert PathKind('file') is PathKind.FILE
