# 6. All concurrency flows through _compat.gather

Status: accepted

## Context
asyncio constructs do not survive unasync; unbounded gather can stampede
cloud APIs; TaskGroup wraps failures in ExceptionGroup, breaking the
error contract.

## Decision
One audited function: async `gather(*aws, limit=)` (semaphore-bounded,
per-call so recursive walks bound per level and cannot deadlock;
first exception propagates unwrapped). Its hand-written sync twin just
collects already-evaluated arguments - sync call sites degrade to
sequential execution naturally via ``*`` unpacking. The codegen forbids
`asyncio` anywhere else.

## Consequences
Parallel walks (du, delete_tree, copy_tree, multi-target ops) in async;
correct sequential behavior in sync; exactly one place where the
flavors' semantics differ.
