# 1. Hexagonal architecture: one core, small backend port

Status: accepted

## Context
0.1.x had every provider implement the full ~30-method unix interface,
duplicated again for async (~1,900 lines, 4 copies of every behavior,
already drifting). Each fix had to be applied four times.

## Decision
One engine (`Storix`) owns all unix semantics; providers implement a
~15-method `StorageBackend` port (read/write/list/stat/delete...).
Providers do zero path logic and speak only storix errors. The pattern
follows fsspec/opendal/object_store.

## Consequences
Behavior is defined once and conformance-tested everywhere; a new
backend costs ~150 lines per flavor; core logic is testable against an
in-memory port. Cost: an indirection layer and a port contract that
must be documented and enforced (docstrings + conformance suite).
