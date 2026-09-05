# ADR-0036 — A unit whose bytes did not change is not converted again

**Status:** accepted
**Date:** 2026-09-05
**The comparison ADR-0006 promised and nothing made, and what it is keyed on.**

## Context

[ADR-0006](0006-the-unit-of-sync-is-the-record.md) says the unit of sync is
the record, identity is `(source_id, unit_key)`, change is `content_hash`, and
*a re-export that changed nothing produces an empty diff*. Measured
(`tools/scaling.py --only resync`, 400 unchanged notes), a no-change re-sync
cost **1.01** of a cold one. Every run was a cold one, and `docs/README.md` had
said so since the beginning. Filed as #77, with the design of the fix in the
issue: the cache key is not the bytes alone.

Almost everything needed was already here. The source bytes were hashed on
every run; the previous manifest was already read back as a ledger for
withdrawal; keys were stable by construction. What was missing was one field
and one comparison.

## Decision

**The manifest records the hash of each artefact's source bytes** —
`source.content_hash`, the same value the trace map already carried — so that a
run can ask *did the bytes change* without opening ten thousand sidecars. It is
not part of `run_id`: the id is over the outputs, and an input hash added to it
would change the id of every existing corpus on upgrade, and with it every
journal's parent chain.

**A unit is carried forward unconverted on three conditions**, checked in the
order they are cheap:

1. **The previous run was decided by the same things this one is.** `musubi`,
   `rulesets`, `screener`, `emitter` and `allowed`, as the manifest recorded
   them, equal to this run's. Any difference is a cold run: a new rule has to
   meet the old corpus, a new signature list has to look at bytes it has never
   seen, a lost allowance has to stop what it was allowing. And **a musubi
   upgrade converts everything again, on purpose** — a converter that changed
   without changing its name is the one case nothing else here would catch,
   and an upgrade is the moment it happens.
2. **The bytes hash to what that run recorded**, and the converter this run
   would use for the unit's media type has the name the record says. Compared
   per unit rather than by the set of names the previous run used, because a
   setting that switched one media type to another extractor can leave the set
   looking the same.
3. **The artefact and its map are still on the disk exactly as recorded** — the
   sidecar present, the document hashing to the manifest's `content_hash`.
   Hashing it means reading it, and the incremental path pays that on purpose.
   The alternative is trusting that nothing touched the corpus since the
   manifest was written, and `musubi verify` exists because that is not a
   thing to trust. A document somebody edited by hand is converted again and
   corrected.

**A carried artefact brings its removals and its findings with it.** The
manifest is an account of the corpus and not of the run's effort: a re-sync
that converted nothing still lists every rule that fired on every document it
holds, or the corpus is one nobody can appeal
([ADR-0005](0005-say-what-was-removed-and-by-which-rule.md)). The test that
pins this compares a warm manifest to a cold one and finds them equal.

**What was kept is reported and not recorded.** `Outcome.kept` names the units
the run did not convert, and the report prints the count, because a run that
converted three documents and said four hundred would be claiming somebody
else's work as its own. It is not in the manifest, for the same reason the
removals *are*: whether a document was converted this morning or last month is
a fact about the run, not about the corpus.

**A plan makes the same decision from the same evidence**, so the dry run
predicts the real one, kept set included.

**The source's timestamp still reaches a kept document**
([ADR-0022](0022-the-document-keeps-the-day-it-was-written.md)) — a note whose
bytes did not change and whose mtime did is a note somebody touched. It is
applied **at promotion**, because a run that later refuses must have touched
nothing in the destination, and a timestamp is a touch.

**And the manifest is promoted last.** Found while writing this: sorted,
`documents/` < `manifest.json` < `traces/`, so a crash between the second and
the third left a manifest describing maps that were not there yet. Promoted
last, a crash at any point leaves the old manifest describing the old corpus,
and the next run's disk check finds the half-promoted documents not matching it
and converts them again.

## Consequences

- Measured, the same 400 notes: **1.69 s cold, 0.54 s unchanged, ratio 0.32.**
  What remains is reading and hashing every source, reading and hashing every
  artefact, and parsing the manifest. The design implied near zero and this is
  not near zero; it is the honest floor for a check that reads the disk rather
  than trusting it.
- A no-change re-sync promotes exactly one file, the manifest, and appends one
  empty journal entry.
- `docs/README.md` no longer lists the incremental path under *not built*, and
  #77 closes.
- `source.content_hash` is optional in `musubi.sync-manifest/1-draft`. A
  manifest written before it omits it, and a run reading one converts
  everything rather than inferring anything from the absence.

## What it costs

**Two reads per unchanged unit where the design implied none.** The source is
read to be hashed and the artefact is read to be checked. A source that could
hand over a hash without the bytes — an archive with a stored CRC, a filesystem
with a content-addressed index — would halve this, and no source does. The
`mtime`-and-size shortcut every build tool uses was considered and declined:
[ADR-0022](0022-the-document-keeps-the-day-it-was-written.md) already found
modification times saying things that were not so, and a shortcut that skips
a changed file is a corpus quietly out of date.

**A musubi upgrade is a cold sync**, always, even when nothing that decides an
output changed. That is a real cost on a large corpus and it is the price of
condition 1 being an equality rather than a judgement. A converter version that
did not move could in principle be trusted across an upgrade; this ADR does not
trust it, because the case it protects against — an output change with no name
change — is exactly the one that leaves no trace.

**The reverse of `render()` now exists.** `DocumentEmitter.previous()` reads
artefact, removal and finding records back out of the manifest, which is the
producer reading its own object — the thing `verify` deliberately does not do,
because a reader that reconstructs the producer's object can only see what the
object can represent. It lives beside the writer of the same layout rather than
in the domain, and a field it cannot read makes the artefact unretainable rather
than the run fail. But it is a second place that has to agree with the first,
and it will be the place a new manifest field is forgotten.
