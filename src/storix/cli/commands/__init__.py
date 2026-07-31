"""The sx commands, one module per help panel (ADR 0034 D1).

Import order is registration order, and registration order is what
``sx --help`` shows: typer lists commands in the order they registered and
opens each panel where its first command appears. So these lines are load
bearing rather than incidental - reordering them reorders the help - and
``test_help_panels_appear_in_registration_order`` pins the result.
"""

# pyright: reportUnusedImport=false
# importing a command module is what registers its commands, so none of
# these names is meant to be referenced here.

from . import navigate  # noqa: I001 - panel order, not alphabetical order
from . import write
from . import read
from . import transfer
from . import session
from . import config
from . import maintenance
