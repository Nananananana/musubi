# 10. Write the consumers' contracts, import neither consumer

**Status:** accepted

## Context

musubi exists to feed `tsumugi` and `kiseki`. The temptation is to import them:
construct a `tsumugi.Document`, call `kiseki`'s reader, get type checking across
the seam for free.

Everything about that is wrong in this family. `tsumugi`'s `kiseki` adapter
already demonstrates the alternative and states the reason: coupling to a
published contract rather than to a schema is the whole difference between an
adapter and a reach-in. It imports nothing, because `kiseki`'s export is JSON
with a documented shape, and a file is enough.

There is a version argument too. musubi, `tsumugi` and `kiseki` release
separately. An import makes every musubi run depend on which version of two other
libraries happens to be installed, and makes musubi unusable for anyone who wants
one of them and not the other.

## Decision

**musubi writes what its consumers publish, and imports neither of them.**
Enforced by `import-linter` and by an AST test: no module under `src/musubi/` may
name `tsumugi` or `kiseki`, not even in an adapter.

Two output shapes, both already specified elsewhere:

**For `tsumugi`** — a folder of Markdown with YAML front matter carrying the
metadata its ingest reads: `title`, `producer`, `observed_at`, `layer`. Plus a
`.trace.json` beside each file (ADR-0004), which `tsumugi` ignores and
`musubi trace` reads.

**For `kiseki`** — its record contracts as JSON: PhotoRecord v1, ActivityRecord
v1, NoteRecord v1. Each has a published schema and a documented gate of ten
questions a new source must answer, and musubi answers them per source in its own
documentation before emitting anything.

Conformance is tested against the schemas, which are vendored into
`tests/contracts/` with the commit they were taken from, exactly as `akashi`
vendors the ContextPackage schema.

### Which layer musubi may declare

`kiseki`'s vocabulary — `fact`, `measure`, `interpretation` — survives into
`tsumugi`'s packages, and a document declares its own layer in metadata.

**musubi emits `fact` and `measure`, and never `interpretation`.** A note the
owner wrote is a fact about what they wrote; a message in a channel is a fact
about what was said. A count musubi derives is a measure. An interpretation
requires a reading, a reading requires a model, and musubi has no model
(ADR-0003) — so an `interpretation` from musubi would be an opinion with no
author, which is precisely the laundering `kiseki`'s layering exists to prevent.

## Consequences

musubi is usable by anything that reads Markdown with front matter, and by
anything that reads those JSON contracts. Neither sibling is required to install
it, run it, or test it.

Anything musubi needs from a consumer that the contract does not carry is
negotiated as a contract change, across the seam, and never as an import.

## What it costs

No type checking across the seam. A field renamed in `tsumugi`'s metadata
vocabulary is caught by a conformance test that has to be kept current, rather
than by `mypy`.

The vendored schemas can drift from upstream. The mitigation is the same one
`akashi` uses: the schema file records the commit it came from, and refreshing it
is a visible, reviewable change rather than a silent one.
