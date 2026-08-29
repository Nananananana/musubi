# 4. A conversion carries a map back to its source

**Status:** accepted

This is the decision the rest of musubi is arranged around.

## Context

Every document-to-Markdown tool in 2026 has the same signature. Bytes in, text
out. `markitdown`, `docling`, `unstructured`, `trafilatura`, every commercial
parsing API: they differ enormously in quality and not at all in shape. What
comes back is a string, and the correspondence between that string and the file
it came from is discarded inside the library.

For a chatbot demo that is fine. For this family of projects it is fatal, and it
is worth being precise about why.

`tsumugi`'s guarantee is that every piece of context names the document, the
offset and the hash it came from — "text that cannot is not context, it is a
guess". `akashi` reports a contradicted figure with an anchor pointing at where
the source says otherwise. Both guarantees are about *a document*. If the
document is `synced/gear.md`, a file musubi wrote by converting `gear.pdf`, then
the anchor resolves to a place in a derived artefact. The owner opens the PDF to
check and there is nothing to check against: the offsets are for a file that did
not exist until the sync ran, and the conversion that produced it is the one step
in the whole chain with no record of what it did.

That is not a theoretical gap. Conversion is exactly where silent corruption
enters. A two-column PDF reflowed in the wrong order interleaves two arguments
into sentences that never existed. A table flattened to lines pairs the wrong
value with the wrong label. An HTML page stripped of boilerplate takes a
paragraph of the article with it. In every one of those cases the output is
fluent and plausible, nothing downstream can detect the problem, and the evidence
chain is already broken by the time `tsumugi` sees a file.

So the useful question is not "which converter scores highest on WCXB". It is:

> Can a conversion be made to carry a map back to its source, at a cost worth
> paying — and if it can, does the map cover enough of real documents to be worth
> having?

## Decision

**Every converter returns text *and* a trace map, or it does not ship.**

A trace map is an ordered sequence of segments that **tile the output exactly**:
every character of every emitted artefact belongs to exactly one segment. Each
segment names a half-open range of the output, and one of three kinds:

| Kind | Meaning | Points at |
|---|---|---|
| `verbatim` | the source's own characters, decoded and otherwise untouched | a range in the source unit |
| `transformed` | the same content in different bytes — normalized, whitespace collapsed, an entity resolved | a range in the source unit |
| `synthetic` | musubi wrote it: front matter, a heading it inserted, a separator | nothing |

Segments are ordered by *output* offset. Their source ranges need not be
monotonic, which is what lets a reflow be expressed honestly rather than hidden:
a two-column page that musubi reads in reading order produces a map whose source
ranges jump, and the jumps are visible.

Two things follow immediately.

**`musubi trace` is a command.** Give it an artefact and an offset range and it
answers with the source file, the byte range and the kind — or says *synthetic,
musubi wrote this*. A citation produced by `tsumugi` or `akashi` against a synced
corpus can be resolved all the way back to the owner's original file, through the
conversion, by a program that knows nothing about either.

**Traceable coverage is the metric this project lives by.** The share of an
artefact's characters lying in a `verbatim` or `transformed` segment. It is
reported per artefact in the manifest, per converter in `docs/measurements.md`,
and it is the number that decides whether this design was right.

## Consequences

A conversion musubi cannot map is a conversion musubi does not do. That forbids,
by construction: summarising, "cleaning up" prose, a model in the path (ADR-0003
again, arrived at from the other end), and any library that returns a bare
string. It also forbids the shortcut where a converter emits mostly-right text
and marks the whole thing `synthetic` — that is legal but it scores zero, and the
score is published.

Removals become expressible. When a cleansing rule deletes a tracking parameter
(ADR-0005), the map records a discontinuity at that point rather than an
undetectable shift, so every offset after it stays honest.

Adjacent segments with the same kind and the same output-to-source delta merge.
A verbatim Markdown passthrough is therefore one segment for a whole file, which
is what keeps the common case nearly free.

## What it costs

**Size.** A pathological conversion — heavily marked-up HTML, character by
character — produces a map larger than the document. Segment merging bounds the
common case and not the worst one. The mitigation is measurement, in v0.4: map
bytes per output byte, per converter, on real corpora, published with the corpus
named. If a format's map routinely exceeds its document, that format's converter
is the thing to fix, and the number is what says so.

**Sensitivity.** A trace map is a per-character index into the owner's private
files, including their paths. It is at least as sensitive as the corpus and is
treated that way — `docs/threat-model.md` will own this, and until then the
ignore rules and pre-commit hooks do.

**Effort.** This is the reason musubi cannot adopt any existing converter later,
even if ADR-0001 were relaxed. The constraint is permanent, and it is chosen with
that understood.

## What would change this

If traceable coverage on real HTML and PDF corpora lands low enough that the
map's guarantees cover only a minority of a real user's corpus, the honest
response is not to loosen the definition of traceable. It is to narrow the
formats musubi claims to handle and say so. The measurement is scheduled before
the formats are promised, for exactly that reason.
