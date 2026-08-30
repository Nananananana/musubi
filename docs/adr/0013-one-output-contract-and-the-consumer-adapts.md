# 13. One output contract, and the consumer adapts

**Status:** accepted. Narrows the scope of
[ADR-0010](0010-write-the-contracts-import-neither-consumer.md).

## Context

[ADR-0010](0010-write-the-contracts-import-neither-consumer.md) settled two
things at once, and only one of them was right.

The part that was right: musubi imports neither `tsumugi` nor `kiseki`, and
writes what they publish. That stands, unchanged, and the import linter still
enforces it.

The part that was wrong: that musubi would ship an emitter *per consumer
contract* — a `tsumugi` folder emitter and a `kiseki` records emitter producing
PhotoRecord, ActivityRecord and NoteRecord.

`kiseki` already contains the argument against it.

It ships **`kiseki-notes`**, described in its own metadata as a *reference
implementation that turns a folder of notes into NoteRecord documents*. Zero
dependencies. It has the plan-then-apply two-step that `kiseki`'s NoteRecord
contract requires, it owns the category vocabulary and which categories are
recorded but never labelled, it owns the trust boundary around where the
classifying model runs, and it derives the opaque `reference` by hashing a path.
It ships **`kiseki-ingest`** on the same pattern for PhotoRecord.

A musubi emitter for those contracts would be a second implementation of both,
holding `kiseki`'s domain semantics inside a library that has no business
knowing them, and coupling every musubi release to a contract musubi does not
own.

And there is a detail in `kiseki-notes` that settles it. It reads `.md`, `.txt`
and `.markdown` and nothing else, on stated grounds: *a format that needs parsing
needs a library, and every library is a dependency that reads the owner's notes*.

**musubi is that library, running out of process.** `kiseki` chose an input shape
specifically so that the parsing could happen somewhere else, and musubi's output
is exactly that shape. The seam was already designed for this before musubi
existed.

## Decision

**musubi publishes one output family, and ships no consumer-specific emitter.**

What musubi produces:

- **Documents.** A folder of Markdown with YAML front matter. This is not an
  adaptation of anything; it is what a cleaned document *is*.
- **`musubi.sync-manifest/1`.** What the run did.
- **`musubi.trace-map/1`.** Where every character came from.

Adaptation to a consumer's records lives with the consumer, in the consumer's own
producer package, where the semantics already live:

```bash
musubi sync ~/notion-export --into ./synced      # a Notion zip becomes documents
kiseki-notes plan ./synced                       # kiseki's own producer, unchanged
kiseki-notes read ./synced --apply --out note-records.json
```

`tsumugi` needs no adapter at all: it ingests folders of Markdown already. The
only musubi-specific artefact in the folder is `.trace.json`, which it ignores.
If `tsumugi` later wants to follow a citation one hop further, into the owner's
original PDF, that is a `tsumugi`-side adapter reading `musubi.trace-map/1` — and
it is `tsumugi`'s decision, made on `tsumugi`'s schedule.

The `Emitter` port stays and ships one implementation. The port exists so that a
third party can write their own, out of tree, without a musubi release.

## Consequences

**v0.5 changes shape entirely.** It stops being "implement three of `kiseki`'s
contracts" and becomes "make the folder good enough that `kiseki-notes` reads it
correctly", which is a much smaller and much better-defined job, verified by
running the real `kiseki-notes` against musubi output in a seam test.

**A derived requirement falls out, and it is not obvious.** `kiseki-notes`
derives a note's opaque `reference` by hashing its path. If musubi's output
filename changes between syncs — because a Notion export regenerated its UUIDs —
then `kiseki` sees a brand-new note that has never been seen before, and the
trail of returnings that NoteRecord exists to capture is destroyed.

So: **musubi's output filename must be a function of the `unit_key`
(ADR-0006), never of the source filename.** Stability that ADR-0006 established
for musubi's own bookkeeping turns out to be load-bearing for a consumer two
steps away, which is exactly the kind of thing a seam only reveals when something
real is on both sides of it.

**Release coupling reverses, correctly.** Under ADR-0010 a change to `kiseki`'s
NoteRecord forced a musubi release. Now it forces a `kiseki` release — which is
where the change originated.

**musubi's promise becomes one sentence** and stays one sentence as consumers are
added. A fourth consumer needs no musubi change at all.

## What it costs

**Two commands where the owner might have wanted one.** `musubi sync` then
`kiseki-notes read`. Softened by the fact that `kiseki`'s contract already
mandates a two-step for notes, and ADR-0012 mandates one for musubi, so the
honest count was never one.

**An intermediate folder holding the text.** `kiseki`'s NoteRecord deliberately
carries no text; under ADR-0010 musubi would have gone from source to record
without the text ever landing in a musubi output. Now it lands in `./synced`
first. In practice this costs nothing — writing that folder is musubi's whole
purpose, and it exists whether or not `kiseki` reads it — but it is worth stating
that the two-step has a byte on disk in the middle.

**No end-to-end conformance guarantee.** musubi can guarantee its own output and
nothing else. If `kiseki` changes what it expects of an input folder, musubi
finds out through a seam test that has to be kept current, not through a type
error. That is the price of every contract seam in this family, and it is the
same price ADR-0010 already accepted.
