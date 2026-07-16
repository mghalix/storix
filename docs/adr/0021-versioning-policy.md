# 21. Versioning policy (0.x shift-down)

Status: accepted

## Context
storix is pre-1.0 and iterating fast: frequent additive features, occasional
breaking changes. We need one documented rule for when a change bumps MINOR
versus PATCH, because the SemVer spec deliberately does not supply one for 0.x,
and the ambiguity already cost churn (an ADR was mistakenly tagged 0.2.3 after
0.4.0 had shipped; conflicting advice circulated on feature->minor vs
feature->patch).

What the spec actually says: SemVer 2.0.0 items 6/7/8 (the patch/minor/major
MUST rules) are each guarded `| x > 0` / `| X > 0`, so they do not apply while
the major is 0. The only clause governing `0.y.z` is item 4: "Major version zero
(0.y.z) is for initial development. Anything MAY change at any time." So 0.x
minor-vs-patch discipline is a convention we choose, not a spec rule.

## Decision
Adopt the "shift-down" convention for the whole 0.x series - every rule shifts
one slot right of normal SemVer:

| change                          | 1.x and up | storix 0.x            |
|---------------------------------|------------|-----------------------|
| breaking public API change      | major      | MINOR (0.4.0 -> 0.5.0)|
| new backward-compatible feature | minor      | PATCH (0.4.0 -> 0.4.1)|
| bug fix                         | patch      | PATCH (0.4.0 -> 0.4.1)|

In 0.x, **MINOR is the breaking-change dial**: a minor bump means "something may
break you", a patch bump means "safe to take". Chosen over treating 0.x like 1.x
(feature->minor) precisely because that would erase the breaking signal from the
number while pre-1.0, which is exactly when breakage is most frequent.

Two invariants hold regardless:

- Published versions are immutable (item 3) and pip resolves the highest, so the
  series is monotonic: never tag or propose a version <= the latest published
  tag. (This is why 0.2.3 was impossible once 0.4.0 shipped.)
- At 1.0.0 the convention flips to standard SemVer (feature->minor,
  breaking->major). Until then, shift-down.

## Consequences
Consumers pin `storix>=0.4,<0.5` and know a `0.4.x` bump is safe to take while
`0.5.0` may break. Contributors and agents have one rule with an objective test:
did the public API change incompatibly? MINOR; otherwise PATCH. The rule is
stated for users on the docs site (how to pin) and for maintainers/agents in the
AGENTS.md "Releasing" section; this ADR is the rationale both point back to.
Cost: one rule to relearn at 1.0 (one-time, acceptable).

Applies to all 0.x releases.
