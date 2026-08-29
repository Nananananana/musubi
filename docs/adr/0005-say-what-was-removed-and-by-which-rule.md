# 5. Say what was removed, and by which rule

**Status:** accepted

This is the decision that makes ADR-0004 honest.

## Context

Cleansing is subtraction. musubi's reason to exist is that it strips the
tracking parameters, the internal identifiers, the export scaffolding and the
platform noise out of somebody's data before it becomes a corpus — and every one
of those strippings is a deletion of bytes the owner actually had.

A wrong rule is invisible. If the tracking-parameter rule eats an `?id=` that was
load-bearing in a documentation link, the output looks *cleaner*. If a Notion
block-UUID rule matches a hexadecimal string in a code sample, the code sample is
quietly wrong and reads fine. Nobody diffs an ingestion output against its input,
because the whole point of the ingestion output is that it differs.

The sibling projects already decided the shape of the answer. `tsumugi`: nothing
is removed on a guess, and every cap that bounds coverage appears in
`omissions[]`, because a silent truncation reads as completeness. `akashi`: the
account of what could not be checked travels with the artefact, because the
artefact travels and the documentation does not. Both are the same rule, and it
applies with more force here, since musubi's subtraction is destructive in a way
neither of theirs is.

## Decision

**Every removal is recorded, with the rule that made it, and the record travels
in the manifest.**

A `RemovalRecord` carries:

- the rule id, exactly as it appears in the ruleset (ADR-0009);
- the kind (`tracking_parameter`, `internal_identifier`, `export_scaffold`,
  `platform_noise`, …);
- the span in the **source** unit, so it can be found again;
- the number of characters removed;
- `sha256` of the removed text — **never the text**.

The trace map (ADR-0004) records the corresponding discontinuity, so offsets
after a removal remain resolvable rather than silently shifted.

### Why the hash and not the value

Because the removed thing is, in the common case, exactly the sensitive thing. A
tracking parameter is an identifier for the owner. A Slack internal user id names
a colleague. A manifest that quoted them would re-publish, into a file people
commit, precisely what the run was for.

The hash still does the work that matters: two runs can be shown to have removed
the same thing, a rule can be shown to have fired on the same value forty times,
and a suspected false positive can be confirmed by hashing the candidate.

For the one case where a person genuinely has to look — deciding whether a new
rule is safe — `musubi plan --show-removals` prints values to the terminal and
never to a file (ADR-0012).

## Consequences

`musubi rules --explain <id>` can report what a rule did on the last run: how
many times it fired, in which sources, over what total length. A rule that fires
ten thousand times in a corpus of two hundred documents is a rule to look at, and
that is visible without reading anything private.

The manifest gains a section that is large and boring. That is accepted: an
account nobody reads is still an account somebody *can* read, and the alternative
is an artefact that cannot be appealed.

## What it costs

A removal cannot be audited by reading the manifest alone; the source is needed
to see what was taken. That is the deliberate trade — auditability against
re-publication — and it is stated here so that nobody re-litigates it as an
oversight.

It also means musubi is more verbose than every tool it competes with. A run that
strips ninety tracking parameters says so ninety times. The summary line exists
for humans, and the ninety records exist for the day somebody asks.
