# 7. Capabilities: advertise features, fail loudly, typed gates

Status: accepted

## Context
Backends are asymmetric (content types, metadata, presigned URLs).
Silently dropping unsupported arguments hides bugs; forcing uniformity
fakes it.

## Decision
A frozen `Capabilities` flags object per backend; the core gates gated
arguments and raises `UnsupportedOperationError` naming the capability.
A `Capability` StrEnum mirrors the field names (alignment-tested) so
raises are never stringly-typed. Capabilities describe *user-observable
features only* - never performance traits (those are method overrides).
ADR 0027 adds one deliberate exception: `bulk_listing` is an internal speed
gate with a silent fallback, never a feature request that can raise.
Layers may upgrade the capabilities of what they wrap. URL expiry is
advisory (`int | None`): None means provider default; providers without
expiring links ignore it.

## Consequences
opendal-style discovery, explicit failures, and the layer-upgrade
pattern (a wrapper can add presigned URLs to a local backend).
