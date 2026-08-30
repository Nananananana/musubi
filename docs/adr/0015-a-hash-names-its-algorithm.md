# 15. A hash names its own algorithm, and the algorithm is SHA-256

**Status:** accepted

## Context

musubi hashes constantly. Every record is content-addressed
([ADR-0006](0006-the-unit-of-sync-is-the-record.md)), every artefact carries a
hash in the manifest, every removal is recorded by the hash of what it took
([ADR-0005](0005-say-what-was-removed-and-by-which-rule.md)), and a `run_id` is
a hash over exactly the inputs that determine the output
([ADR-0003](0003-a-sync-is-reproducible.md)).

By 2026 SHA-256 is not the fast option. BLAKE3 reports roughly an order of
magnitude more throughput on commodity hardware and parallelises across cores,
which is exactly the shape of musubi's workload — a large folder, hashed in
full, on every run. BLAKE2b is the middle ground and, unlike BLAKE3, **is in
`hashlib`**, so it is available under [ADR-0001](0001-the-domain-depends-on-nothing.md)
at no cost at all.

Two things argue the other way.

**The family's published contracts already say `sha256`.** `kiseki`'s PhotoRecord
schema constrains its `id` to `^sha256:[0-9a-f]{64}$`; `tsumugi` and `akashi`
both use `sha256:` prefixed content hashes throughout. musubi writes into that
world ([ADR-0010](0010-write-the-contracts-import-neither-consumer.md)), and a
second algorithm at the boundary means a conversion, or a schema change
negotiated across three projects, to buy speed nobody has yet shown is needed.

**And nobody has shown it is needed.** The intuition is that musubi's cost is
dominated by reading and converting rather than hashing. That is an intuition,
and this project does not write unmeasured numbers into documents, so it stays
an open question rather than becoming a justification.

## Decision

**Every hash musubi produces is a string that names its own algorithm:
`sha256:` followed by 64 lowercase hex characters.** The algorithm is SHA-256.

The prefix is the whole point of the decision. It costs seven bytes and it means
a future change of algorithm is a *data* change that old readers can detect and
refuse, rather than a silent reinterpretation of a field that looks the same and
means something else. It is the same reasoning as the `contract` field on a
document ([ADR-0002](0002-the-sync-manifest-is-a-document.md)), applied to a
value instead of a file.

Structured values are hashed over a canonical form, so that a `run_id` does not
change when a field's order does. musubi canonicalizes by the rules of **RFC 8785
(JSON Canonicalization Scheme)**: lexicographic key ordering by UTF-16 code unit,
minimal separators, no insignificant whitespace. Following a published
specification rather than inventing one means the canonical form can be produced
by anyone re-deriving a `run_id` in another language, which is what
`musubi verify` is for.

**Floating-point values are refused by the canonicalizer.** JCS's hardest clause
is its number serialization, and musubi does not need it: everything that
determines a run is a string, an integer or a boolean. Refusing floats is a
restriction that removes the only part of the specification that is difficult to
get exactly right, and a test asserts the refusal rather than the intent.

## Consequences

Hashes are comparable across the four sibling projects without translation, and
a musubi content hash can be dropped into a `kiseki` record as it stands.

Nothing in the code says `sha256` outside `domain/hashing.py`, so the day a
measurement argues for BLAKE2b, the change is one module plus a contract version
plus a compatibility window — not a search for hard-coded 64s.

## What it costs

**Speed, in an amount nobody has measured.** That is the honest statement of the
cost: SHA-256 is several times slower than the alternatives, musubi hashes
whole corpora, and whether that matters is a v0.4 measurement — the cold-sync
and re-read numbers ADR-0006 already owes. If hashing turns out to be a
meaningful share of a sync, this ADR gets superseded by one that cites the
measurement.

**Seven bytes per hash**, everywhere, forever. Worth it.

**The canonicalizer is a subset**, and calling it "RFC 8785" without qualification
would be a claim musubi does not meet. It implements the clauses its input domain
reaches and refuses input that would reach the rest, which is a different and
smaller promise, stated here so that nobody later assumes the general one.
