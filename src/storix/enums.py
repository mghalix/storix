from enum import StrEnum, auto


class StorixEnum(StrEnum):
    """Base class for all storix enums.

    StrEnum members are strings: they compare equal to their values
    (``PathKind.FILE == 'file'``) and are usable anywhere a plain string
    is expected, so accepting or returning them never breaks callers that
    work with bare strings.
    """


class PathKind(StorixEnum):
    """The kind of object living at a path."""

    FILE = auto()
    DIRECTORY = auto()


class Capability(StorixEnum):
    """Optional backend features, mirroring ``Capabilities`` field names.

    Raise ``UnsupportedOperationError(Capability.X)`` instead of a bare
    string; the alignment test guarantees members and fields never drift.
    """

    CONTENT_TYPE = auto()
    CUSTOM_METADATA = auto()
    PRESIGNED_URLS = auto()
