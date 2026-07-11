# 4. Errors: raise always, carry facts, dual-inherit stdlib

Status: accepted

## Context
0.1.x mixed raising with log-and-return-False, with hand-written
message strings drifting per provider.

## Decision
Every failure raises a typed error. `PathError` subclasses carry the
offending path as data (`.path`, plus OSError-convention `.filename`
and a real `errno`), dual-inherit the stdlib namesake
(`PathNotFoundError(FileNotFoundError)`...) so idiomatic handlers keep
working, and build default messages from one template per class.
Backends translate native failures at their boundary (`from_os_error`
table; azure error-code map). Learned the hard way: OSError.__str__
hijacks formatting once filename/errno are set (override __str__), and
OSError.__init__ resets its slots (assign facts after super().__init__).

## Consequences
`except StorageError` catches everything; layers can re-scope errors by
rebuilding them from facts; messages have exactly one home. The
`ValueError` leg of 0.1.x is gone (breaking).
