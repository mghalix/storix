# 3. Port shape: wider port, generic fallbacks, plain DTOs

Status: accepted

## Context
Some operations have native fast paths (Azure rename is one call);
naive copy+delete would regress them. DTOs cross the port on hot paths.

## Decision
The port *requires* move/copy/delete_tree/du alongside primitives;
`generic.py` free functions provide fallbacks (backend-first args so
non-subclassers reuse them) and `BackendBase` pre-wires them - port
growth stays non-breaking for subclassers. DTOs (`Entry`, `RawStat`)
are plain NamedTuple/frozen dataclasses (trusted data, no validation
cost); `FileProperties` is the separate validated pydantic surface
(`from_raw()` bridges). Port paths are `PurePosixPath`, pre-resolved by
the core. `delete` removes leaves only (file or empty dir); `list_dir`
tolerates deletion of yielded entries; directory entries report
`size=None`; `du` is apparent content bytes (like `du -sb`), never
blocks.

## Consequences
Cloud performance preserved; every semantic pinned here is a
conformance test. Two model types must be kept aligned (one classmethod
does it).
