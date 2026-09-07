# 0048. A record that does not say is not a record that says no

**Status:** accepted
**Date:** 2026-09-10
**Context:** [ADR-0036], [ADR-0040], [ADR-0044], [#82](https://github.com/Nananananana/musubi/issues/82)

## The defect

[ADR-0036] reuses a document whose source bytes have not changed: rather than
converting it again, the run copies its record out of the previous manifest and
into the new one. It is the reason a re-sync costs 0.30 of a cold one.

That is sound only while the record is **complete**. `_artefact_from` fills a
default for a field an older manifest does not have — and then the run
republishes it, which turns an absence into a claim.

Measured on a Shift-JIS vault read entirely by detection, with the manifest
rewritten as a musubi from before [ADR-0044] wrote it:

```text
  first sync      encoding='cp932'   detected=True
  re-sync (kept)  encoding='cp932'   detected=True
  after upgrade   encoding='utf-8'   detected=False     <- every document
```

Nothing failed. The manifest said the corpus was UTF-8 and declared, `musubi
verify` passed, and the run report — added days earlier so an owner could ask
*how much of this corpus rests on a guess* — answered **none of it**.

And it is sticky. The wrong value is now in the manifest, so the next re-sync
carries it forward as though the corpus had always said it.

## It was never only `encoding`

`encoding` is how this was found. Every field added since a corpus was first
written has the same shape, and two are worse:

| field | default on the way in | what republishing it claims |
|---|---|---|
| `encoding` | `"utf-8"` | a guess, as a declaration |
| `encoding_detected` | `False` | that musubi did not guess |
| `source_unit` | `"characters"` | that a PDF's page range is a character count |
| `title` | `None` | that a document says nothing about itself |
| `answered_source_units` | `0` | an answer width the corpus never measured |

`source_unit` is the one that would have hurt most. [ADR-0025] exists to keep
page ranges and character counts apart, and a default of `characters` makes two
coverage numbers look addable that are not.

## Decision

**A record missing a field the manifest publishes is not reused.**

The gate goes where `source_hash` already gates exactly this — an artefact
whose record has no source hash is already excluded from reuse for the same
reason — and not in the parser:

```python
complete = published_artefact_fields() <= set(entry)
if artefact is not None and artefact.source_hash and complete:
```

**Reading is not republishing**, and the distinction is the whole of the fix.
Two existing tests say *absent is not wrong* — a reader holding an older
manifest should carry on, `answer_width` should return `None` rather than
`0.0`, a missing `title` should read as `None`. They are right, they still
pass, and they are about the parser. Republishing is a different act: it is
musubi asserting something about a corpus.

**The population comes from the renderer.**

```python
@cache
def published_artefact_fields() -> frozenset[str]:
    """Every key `render` writes for an artefact, taken from the renderer."""
```

Not a list beside it. `encoding` was added to `render` and this gate was not
told, which is precisely the failure; a list would have gone stale the same way
the next time. Rendering one sample artefact and taking its keys means a field
added to the manifest is a field a reused record must already carry, with
nobody remembering anything.

## What it costs

**One full sync after a field is added.** Every record is incomplete on that
run, so nothing is reused and everything is converted. The run after it reuses
again, and a test asserts that the corpus settles rather than reconverting
forever.

That is a real cost on a large corpus and it is the right one: the alternative
is a corpus that quietly says something untrue about every document in it until
somebody edits the file.

**A `cache` on a domain function that renders a manifest to answer.** Cheap,
called once per run, and it keeps the answer honest by construction rather than
fast by duplication.

**The gate is in one of three readers of the same document.** `previous()`
reads the manifest for withdrawal, for the journal, and for reuse, and only the
third is gated. The other two are unaffected: withdrawal counts paths and the
journal wants hashes, and neither invents anything.

## Consequences

The test is parametrised over **every** published field rather than the one
that was noticed, and verified potent by removing the gate: it goes red on
`title` and `answered_source_units` as well as on `encoding`. A regression test
for the specific field would have left the other four.

This is the fourth time in this repository that a value was **defaulted on the
way in and asserted on the way out**. [ADR-0040] is `title`, `null` and never
`""`. [ADR-0033] is `answer_width`, `None` and never `0.0`. The catalogue in
[ADR-0044] refuses to let a detected encoding read as a declared one. Each of
those fixed the field in front of it. This one fixes the act — republishing —
and is the first of them that a field added tomorrow cannot get past.

[ADR-0025]: 0025-a-map-with-no-verbatim-run-composes-whatever-it-measures.md
[ADR-0033]: 0033-a-threshold-that-nobody-swept-is-a-number-fitted-to-one-corpus.md
[ADR-0036]: 0036-a-unit-whose-bytes-did-not-change-is-not-converted-again.md
[ADR-0040]: 0040-a-corpus-says-what-it-holds-and-what-it-is-called.md
[ADR-0044]: 0044-a-second-opinion-from-the-same-detector-is-not-a-second-opinion.md
