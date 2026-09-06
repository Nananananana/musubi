# ADR-0037 — A fetch record beside the page is a fact musubi may state

**Status:** accepted
**Date:** 2026-09-06
**Where a page's URL and fetch time travel, and why not the two other places.**

## Context

The `sora` orchestrator builds a news lane — *feed → musubi → tsumugi* — and
puts musubi in it for one reason: so that a screen's *open the original* can
go from a downstream anchor back to **the bytes it fetched**. It lays pages out
as `<feed>/<date>/<id>.html`, and it knows two things about each page that the
page does not say about itself: the URL it came from and when it was fetched.
It asked musubi to decide where those facts travel
(`musubi-work/01_sora_requirements.md`, R1), and offered two options:

- **(a)** front matter musubi writes, with `source_url` and `fetched_at` added
  to its vocabulary;
- **(b)** an index the orchestrator keeps in a separate tree, with musubi
  handling the page alone.

And it stated a constraint the right answer has to respect: *Sora が勝手に
front matter を書き足すことはしない* — it will not write into the pages,
because that would corrupt the record of where the bytes came from.

Two places were available and both were wrong. A sidecar in the corpus is
indexed as a document by the consumer downstream (measured, in
`emitters/documents.py`), and the artefact path has to be exactly `documents/`
+ `unit_key` (#62). Front matter written by the producer into the page changes
the bytes a trace leads to, which is the thing musubi exists to keep.

## Decision

**(a), with the facts in a record beside the page in the source tree, read by
a dedicated source and stated by musubi.** `<id>.html` and `<id>.fetch.json`:

```json
{"url": "https://example.test/a/1", "fetched_at": "2026-09-05T03:12:00Z",
 "canonical_url": "https://example.test/a/1"}
```

`FetchedSource` (`--as fetched`, `source = "fetched"`) reads the record beside
each page and hands the pipeline the page's bytes **and** the facts. The
emitter writes the facts into the document's front matter as flat `key: value`
lines — `source_url`, `fetched_at`, `canonical_url` — beside `layer` and
`producer`. The page's bytes are never touched.

**This is inside what musubi is entitled to say.** `domain/frontmatter.py`
lists the two things musubi may state about a document: its layer and its
producer. A fact the source states about a unit is the third kind, and it is
the same kind as the first two — something known about the document from
outside it, stated under `layer: fact`, and never an interpretation
([ADR-0010](0010-write-the-contracts-import-neither-consumer.md)).
The record is the orchestrator saying *here is what I know about this fetch*;
musubi repeats it and attributes nothing.

**Front matter is written to any document that carries facts**, not only to
Markdown. The rule was that a `.txt` gets none because its layer and producer
live in the manifest, where a reader who cannot parse front matter would look.
A page's URL that stays in the manifest never reaches the consumer that
indexes the documents, and reaching it is the whole request.

**The facts are recorded in the manifest beside the artefact**, and they
decide reuse. The page's `content_hash` is the hash of the page and nothing
else — `musubi trace` checks the page on disk against it — so the facts cannot
enter it. They enter the artefact record instead, and [ADR-0036]'s comparison
now covers them: a record that changed under an unchanged page converts the
unit again. Without that, editing `fetched_at` would leave a stale document
with the manifest describing it as current.

**One article, once.** Two pages whose records share a `canonical_url` — or a
`url`, when no canonical one is given — are one article, and a corpus holding
both answers the same question twice (U2). The first in walk order is read;
the rest are skipped with reason `duplicate` and the origin of the page that
stood for them. Pages with no record are never taken for one another: silence
is not evidence that two pages are the same. The choice is made here and not
by keying on a URL hash, because a key nobody can read in a citation trades
[ADR-0006](0006-the-unit-of-sync-is-the-record.md)'s legible weakness for an
illegible one.

**A missing record is not an error; a record that cannot be read is a skip.**
A page with no record is read and states nothing. A record that is present and
is not a JSON object, or gives a fact that is not a bare single-line string, is
`bad_fetch_record` with the reason — a record that lies is worse than none, and
a value with a line break would put the rest of itself into the document body
for the one-line-per-key reader downstream.

**A fact may not be stated under `layer` or `producer`**, and a key may not
contain a colon. The first is a source overwriting what musubi states; the
second is two keys to the reader.

## Consequences

- The orchestrator's question is answered: **(a)**, and the record format
  above is the contract between it and musubi. It writes the record, never the
  page, and never the corpus.
- `musubi.sync-manifest/1-draft` gains an optional `facts` object per
  artefact. Draft, so a field is added rather than a `/2` made
  ([ADR-0024](0024-a-field-added-is-a-new-contract.md) governs a frozen one).
- `Found`, `Document` and `Artefact` each carry `facts`; the front matter's
  validation covers them the way it covers `layer` and `producer`.
- The export carries the facts in the text before `body_offset`, so a consumer
  reading rows rather than documents still learns where a page came from.

## What it costs

**The artefact keeps the page's name.** `feed/2026-09-05/a.html` in the corpus
is extracted text with front matter, named `.html`. That was already true of
every HTML sync and is not new here, but this ADR makes it the normal case for
a whole lane. A consumer whose parser registry claims `.html` may parse the
extracted text as markup, and whether `tsumugi` reads front matter off a file
so named is a question for that seam, asked in the response to the orchestrator
rather than answered by guessing here.

**Deduplication is by the record, and the record can be wrong.** A feed that
puts the same `canonical_url` on two different articles loses one of them,
silently except for the `duplicate` line in the manifest. The manifest saying
which page stood for which is the whole of the defence, and it is the same
defence [ADR-0005](0005-say-what-was-removed-and-by-which-rule.md) offers for
everything else musubi drops.

**Three keys, fixed.** `url`, `fetched_at`, `canonical_url` and nothing else
travels. A record may say more and it stays in the record. Widening this is a
vocabulary decision the front matter's reader has to be party to, and it is
deliberately not made in advance.
