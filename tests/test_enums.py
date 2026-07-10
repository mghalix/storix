from storix.enums import PathKind


def test_pathkind_values():
    assert PathKind.FILE == 'file'
    assert PathKind.DIRECTORY == 'directory'


def test_pathkind_members_are_strings():
    """StrEnum contract: members are usable anywhere a str is expected."""
    assert isinstance(PathKind.FILE, str)
    assert PathKind('file') is PathKind.FILE
