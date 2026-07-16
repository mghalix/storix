# 12. Rejected and deferred (so they are not re-litigated)

Status: accepted

- **Sentinels for Entry.size** - rejected: None is not a valid size, so
  Optional is exact; sentinels are for when None is meaningful input.
- **Typestate (FileEntry | DirEntry)** - rejected for hot-path DTOs:
  forces narrowing at every loop for a bug class the walk structure
  already prevents; `is_dir` is the discriminant.
- **@model dataclass_transform decorator** - deferred until ~5+ models
  (deferred-decisions.md has the implementation). Adopted in 0.4.1 as
  `storix.models.model`: the fifth house-style DTO (TransferEvent,
  ADR 0019) hit the trigger.
- **tests/unit|integration dirs** - rejected: location mirrors source,
  *kind* is a pytest marker (`-m integration`).
- **exist_ok on mkdir** - rejected: unix -p already means both things;
  pathlib-style splits belong to the future pathlike adapter.
- **Blob-API (flat namespace) Azure backend** - rejected for 0.2.0:
  HNS-only with a loud hint; flat accounts arrive via the fsspec
  adapter (0.3.0).
- **MountLayer (multi-container compositor)** - deferred, designed
  (deferred-decisions.md), 0.2.x candidate.
- **Template-method _impl split in BackendBase** - direction accepted
  for the repeated stat-and-validate prologues (delete/list_dir/
  read_stream duplicate them across backends), deferred as an internal,
  non-breaking 0.2.x refactor. Blanket _impl for every method rejected
  as ceremony.
- **Legacy lazy-import machinery (_limp/__getattr__)** - dropped: it
  existed to dodge eager heavy providers; the new tree imports nothing
  heavy at top level, and the one heavy optional (azure SDK) stays lazy
  in exactly two places (backends __getattr__, factory builder).
