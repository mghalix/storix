# 11. Disposable and pinned workspaces

Status: accepted

## Context
Tests and pipelines need throwaway or reusable working areas; cloud
scratch space should not require new backend features.

## Decision
`temporary()` = zero-config local: mkdtemp-rooted backend it *owns*,
deleted on exit. `scratch(backend, root=None)` = composition on ANY
borrowed backend: unique subtree + SandboxLayer + delete_tree on exit;
a *pinned* root (named) is created-if-missing, reused, and persists -
named workspaces are yours, anonymous ones are disposable (auto-deleting
a typo'd name would be destructive). `fs.scratch()` runs it on the
session's own backend. Not a capability: temporariness is a lifecycle
around a namespace, not a per-operation feature.

## Consequences
Ephemeral agent/test workspaces on memory, disk, or Azure with zero
backend cooperation - SandboxLayer paying for itself again.
