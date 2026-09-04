# ADR-0030 — An envelope is not a contract

**Status:** accepted
**Date:** 2026-09-04
**Reads against [ADR-0013], and does not narrow it.**

## Context

[ADR-0013] says musubi ships **no consumer-specific emitter**, and the reason it
gives is precise. An emitter for `kiseki`'s NoteRecord would hold *`kiseki`'s
domain semantics* — its category vocabulary, which categories are recorded but
never labelled, its trust boundary, its opaque reference — inside a library that
has no business knowing them, and would couple every musubi release to a
contract musubi does not own.

That argument is right and it settles a different question from this one.

musubi's output is a folder of Markdown, a manifest and a tree of trace maps.
That is the right thing to *write*. It is four things to *read*. Somebody wiring
a corpus into a retrieval pipeline has to walk the folder, know that `traces/`
is not documents (a real consumer got that wrong: five files ingested where two
were meant, recorded in `emitters/documents.py`), join the manifest for the
converter and the coverage, and **invent an id**.

The id is where the friction turns into a defect. Every loader in every
framework derives one from a path or generates a UUID, and both are wrong for
the thing people actually do: upsert into a vector store, on a corpus that gets
re-synced. A path-derived id changes when a Notion export regenerates its UUIDs;
a generated one changes every run. Either way the second sync duplicates the
corpus instead of updating it.

**musubi has a real id and nobody outside can see it.** [ADR-0006] makes
identity `(source_id, unit_key)` and makes the key survive a re-export — the
property [ADR-0013] itself found was load-bearing for a consumer two steps away.
It is in the manifest, under a nested `source` object, and reaching it means
writing the join that people write badly once and never look at again.

## Decision

**`musubi export` reads a corpus and writes JSON Lines: one document per line,
`id`, text, and metadata.** It writes nothing into the corpus and changes
nothing about `sync`.

Three shapes — `jsonl`, `langchain`, `llamaindex` — which differ from each other
by **the name of one key**: `text` or `page_content`, `id` or `id_`. The
metadata is identical in all three, because it is musubi's own and not theirs.

**This is not what ADR-0013 forbids, and the test is the semantics.** A
`page_content` / `metadata` pair is an envelope with no meaning of its own.
Nothing in `application/export.py` would have to change if a framework changed
what it *means* by a document; it would have to change if a framework renamed a
field. That is the whole of the coupling, and renaming a key is not adopting a
contract. The moment a shape needs to know something a framework believes — a
chunking convention, a required metadata key, a namespace — it has stopped being
an envelope and this ADR does not cover it.

**The id is `source_id:unit_key`**, and it is the reason for the feature rather
than a detail of it.

**The metadata carries `trace_map` and `corpus`.** Text that enters somebody
else's index normally loses its provenance at the door. With those two fields a
range chosen in retrieved text goes back through the map to a place in the
owner's own file, and a test walks exactly that path: corpus → exported line →
an offset inside the exported text → `musubi trace` → `gear.md`.

**The text is emitted whole**, front matter included, with `body_offset` saying
where the prose starts. Emitting the body alone would silently invalidate every
offset in the trace map; making the slice the caller's decision keeps it
visible.

## Consequences

- The command is the sixth, and it writes a document, so [ADR-0020] applies in
  its harder form: the report goes to standard error and the document to the
  buffer beneath standard output, so a pipe gets the document and a person still
  gets the count. `test_every_command_the_parser_knows_is_exercised_here` caught
  this before a person did, for the second time.
- `kiseki` is unaffected. `kiseki-notes` reads the folder, as [ADR-0013] settled;
  nothing here is aimed at it and nothing here is a record type.
- A fourth shape is a line in a table. A fourth *consumer contract* is still a
  different decision, still refused, and still belongs with the consumer.

## What it costs

**A field name in a table that musubi does not own.** `page_content` is
LangChain's word. If it becomes `content` in a future major version, this table
is wrong and a user's loader breaks — and musubi will find out through somebody
reporting it, not through a type error. That is a small, permanent maintenance
cost, and it is the honest price of removing the friction rather than describing
it in a README.

**And the export invites a mistake this project spent ADR-0004 preventing.** A
line of JSON is easy to treat as the document, and it is not: it is a copy, with
no relationship to the corpus once either changes. The `content_hash` in the
metadata is what a careful consumer checks and what a hurried one ignores.
Nothing here stops somebody embedding a year-old export and citing it as
current — the corpus can say what it is, and it cannot say that about a file
somebody took away.
