"""Interactive REPL for the storix CLI, one module per job (ADR 0034 D3).

The dependency direction is one way: ``parsing`` knows nothing of the
session, ``globbing`` uses ``parsing`` and the session, ``completion`` and
``keys`` use both, and ``loop`` uses all of them and the command tree.
Nothing below ``loop`` imports ``loop``.
"""

from .loop import start_shell


__all__ = ['start_shell']
