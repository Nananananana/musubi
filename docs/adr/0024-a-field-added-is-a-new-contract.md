# 24. A field added is a new contract, not a wider old one

**Status:** accepted

## Context

`docs/contracts.md` said:

> Once frozen: a field may be added; none will be removed or change meaning. A
> field addition is a schema revision, and an old validator will refuse a newer
> document because every object is `additionalProperties: false`. That is
> deliberate and fail-closed.

The second half is honest, and it is more than `tsumugi` had — `tsumugi` promised
*a field may be added* over the same `additionalProperties: false` structure with
nothing said about the consequence, and found on measuring that the promise had
been unfulfillable since the day it froze. musubi at least wrote the consequence
down.

Writing it down did not make it coherent. Measured here, against the real schema
and a manifest a real sync wrote:

```text
today's manifest against today's schema : accepted
a manifest with one added field         : REJECTED
a manifest that is actually malformed   : REJECTED
both arrive as ValidationError
```

**A consumer holding the older schema cannot tell *I am out of date* from *this
document is malformed*.** Those need opposite responses — refresh the schema, or
refuse the document and tell somebody — and as one `ValidationError` they are
one situation.

This is the shape ADR's neighbour in this repository already names. The trace
map's fourth resolution rule exists because folding *musubi wrote this* and *this
did not resolve* into one return value turns an abstention into a pass. Here two
failures collapse instead of a failure and an abstention, but the defect is the
same: **one value carrying two situations that want different handling.**

`akashi` has already lived it. Its `audit-report/1` gained an optional field, and
its own documentation records that *a consumer validating against a cached copy
of the schema will reject a v0.4 report until it refreshes* — a real consumer,
rejecting a valid document, with no way to know that is what happened.

## Decision

**A field added produces a new contract identifier.** `musubi.sync-manifest/2`,
not a quietly wider `/1`. Removal and changes of meaning stay forbidden, as
before.

`additionalProperties: false` stays, and this is what makes the rule enforceable
rather than merely written: **the schema itself will not let a wider document
pass as `/1`**, so there is no version of *add it quietly* that works. The
constraint and the versioning rule now agree instead of pulling against each
other.

The signal moves to where a consumer already looks. Step 1 of *Writing a
consumer* is **check `contract`, refuse a value you do not recognise**, and it
runs before any validator. An unrecognised `/2` says *you are out of date* in the
one place that cannot be mistaken for a malformed document. **The rule that was
already published does the work, once additions stop hiding from it.**

## Consequences

Every additive change now costs an identifier and a refresh for every consumer,
including ones that do not want the new field. Under the previous rule those
consumers broke anyway — they just found out by validation failure instead of by
name — so the cost is not new. What is new is that they can tell why.

Neither contract is frozen, so this is free today. After a freeze it would not
be: `tsumugi` measured that loosening the schema afterwards does not help,
because consumers are told to ship the schema with their code, and a vendored
strict copy goes on refusing. **The moment to get this right is while it is still
a draft**, which is the only reason this is being decided now rather than when
somebody first wants a field.

## What it costs

**Identifier churn is real and will look silly.** A single optional field —
`corpus_bytes`, say — makes `musubi.sync-manifest/2`, and a project that adds
four fields over a year publishes `/5`. Version numbers that climb for reasons
nobody outside can see are a thing consumers learn to ignore, and a consumer who
learns to ignore them stops doing step 1 properly, which is the exact check this
decision leans on.

**It converts a soft failure into a hard one on a schedule musubi chooses.**
Under `additionalProperties: true` an old consumer could read a newer document
and quietly ignore what it did not know. musubi has decided that is worse — a
consumer that cannot see the whole of what it was handed should say so — but that
is a judgement about consumers musubi does not have yet, made on their behalf.
Somebody building a dashboard that only wants `run_id` and `coverage` is now
broken by a field they would never have read.

**It does not help a consumer that skipped step 1.** The whole mechanism is a
string check the consumer performs before validating, and nothing musubi ships
can make them do it. The schema refuses the document either way, so they are no
worse off than before — but they get no benefit from this decision at all, and
they are probably the majority.
