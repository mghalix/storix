from enum import StrEnum, auto
from typing import Final


class Permissions(StrEnum):
    """Filesystem permisssions."""

    READ = auto()
    """Read the content, properties, metadata etc.
        Use the file as the source of a read operation."""
    CREATE = auto()
    """Write a new file."""
    WRITE = auto()
    """Create or write content, properties, metadata. Lease the file."""
    DELETE = auto()
    """Delete the file."""
    EXECUTE = auto()
    """Get the status (system defined properties) and ACL of any file in the directory.
        If the caller is the owner, set access control on any file in the directory.
    """
    ADD = auto()
    """Append data to the file."""
    MOVE = auto()
    """Move any file in the directory to a new location. Note the move operation can
        optionally be restricted to the child file or directory owner or the parent
        directory owner if the said parameter is included in the token and the sticky
        bit is set on the parent directory.
    """


SAS_EXPIRY_SECONDS: Final[int] = 3600
SAS_PERMISSIONS: Final[frozenset[Permissions]] = frozenset({Permissions.READ})
