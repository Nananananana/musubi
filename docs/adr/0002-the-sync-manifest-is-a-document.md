# 2. The sync manifest is a document, not a type

**Status:** accepted

Borrowed from `tsumugi` (ADR-0002) and `akashi` (ADR-0002).

## Context

A sync run produces two kinds of output. The *artefacts* — the cleaned documents,
the record files — are the point. But the artefacts alone cannot answer the
questions somebody asks three months later:

- Where did this paragraph come from?
- What did the run remove, and under which rule?
- Was anything skipped, and why?
- Did this folder come from the export I think it did?
- If I run it again on the same input, do I get the same thing?

A library that answers those through Python objects answers them for Python
programs running today. The questions get asked by a reviewer holding a JSON
file, by a shell script six months from now, and by the next program in the
chain — which is `tsumugi`, and which does not import musubi.

## Decision

**A run emits `musubi.sync-manifest/1`: a JSON document that stands on its own.**

It names the sources it read, the artefacts it wrote and their hashes, every
removal with the rule that made it (ADR-0005), everything skipped with its
reason, the rulesets and converter versions in force, and a `run_id` derived from
exactly the inputs that determine the output.

A second contract, `musubi.trace-map/1`, travels beside each artefact and holds
the correspondence back to the source (ADR-0004). Two documents rather than one,
because the manifest is small and read often and a trace map is large and read
only when somebody follows a citation.

Both are versioned by name. A consumer reading a `contract` value it does not
recognise refuses rather than parsing hopefully.

## Consequences

The Python API is a convenience over the document, never the other way round.
Anything a caller can learn from a `SyncReport` object is in the manifest, and a
test asserts the two do not drift.

The schemas ship inside the wheel. A consumer validating a manifest should not
have to fetch a schema from the internet, and a tool that promises to work
offline cannot have an online contract.

## What it costs

Writing a document is more work than returning an object, and versioning it is
more work again: a field added is a field that has to keep meaning what it meant.
The freeze rule is `tsumugi`'s — a contract freezes once a second program has
produced and consumed one, not on a date.

A manifest is also an artefact that leaks. It names private file paths, and a
trace map names them per character. `.gitignore` and the pre-commit hooks treat
both as if they were the corpus, because they very nearly are.
