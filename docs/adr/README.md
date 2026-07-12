# Architecture Decision Records

One file per decision, numbered, append-only: a decision is never
edited into something else - it is *superseded* by a new ADR that links
back. Format is MADR-lite: Status / Context / Decision / Consequences.

Why keep these: (1) future contributors learn *why*, not just *what*;
(2) settled arguments do not get re-litigated; (3) the owner's design
education is preserved. Prior art: Nygard ADRs and MADR (adr.github.io)
in industry; Python PEPs, Rust RFCs, Kubernetes KEPs as heavyweight
cousins; FastAPI keeps the same knowledge as narrative docs
(alternatives.md, history-design-future.md) - we use ADRs while the
project is design-heavy and may distill narrative docs from them later.

Decisions 0001-0013 were made during the 0.2.0 rework (2026-07-10/11);
0014 onward cover 0.2.1 polish (2026-07-11/12).
