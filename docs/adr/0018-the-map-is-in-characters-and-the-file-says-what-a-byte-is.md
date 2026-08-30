# 18. The map is in characters, and the file says what a byte is

**Status:** accepted. Settles a unit
[ADR-0004](0004-a-conversion-carries-a-map-back-to-its-source.md) deliberately
left open.

## Context

[ADR-0004](0004-a-conversion-carries-a-map-back-to-its-source.md) says a segment
points at "a range in the source unit" and does not say what a unit is.
`domain/span.py` repeats the evasion on purpose: *what a position indexes is the
holder's business, and the trace map is where that is recorded.* Writing the
first converter is where it had to be decided.

The obvious answer is **bytes**. `docs/concept.md` already promises
`~/docs/gear.pdf page 3 [1086:1113]`; a byte offset is the one thing every tool
takes — `dd`, `head -c`, `grep -b`, a hex editor; and a format with no characters
in it at all still has bytes, which matters the moment a PDF converter exists.

It was implemented that way, and a test caught what is wrong with it.

`source_span_of` answers an interior query by clipping inside a verbatim run:
the source offset is the query offset plus a constant. That constant is a
*character* delta. On a map whose source side is bytes, the arithmetic silently
produces an offset wrong by however many multi-byte characters came before it —
which, in a Japanese corpus, is all of them. The query landed mid-character and
the test failed on a decode error; in a corpus with no accidental invalid
boundary it would simply have pointed at the wrong place.

The fix is not local. **A byte-measured map cannot answer an interior query on
its own**, because the relation between a character index and a byte offset is a
property of the text, and the map does not hold the text. The alternatives are
all worse: refusing to clip means a whole file is one verbatim segment and every
query returns the whole file; refusing to merge verbatim runs means the map costs
more than the document, which is the cost ADR-0004 already promised to control.

## Decision

**A trace map's source side is measured in characters of the decoded text.**

A `TraceMap` carries `source_unit`, and for every converter that exists it is
`characters`. The field is kept rather than dropped for the same reason a hash
carries `sha256:` ([ADR-0015](0015-a-hash-names-its-algorithm.md)): when a PDF
converter arrives with a locator that is a page and an offset within it, an old
reader must be able to *see* that it is not looking at a character map, rather
than reading one field as another.

**The decoding is recorded beside the map** — the encoding, and the bytes a
byte-order mark consumed. That is everything needed to turn a character range
into a byte range, and it is a fixed, tiny amount of information rather than a
per-character index.

**The byte answer is computed by whoever holds the file.** `musubi trace` opens
the source to show the text anyway; converting an offset once it has done so is
one `encode` of a prefix. The map stays sound, composition stays sound, and the
promise in `docs/concept.md` is still delivered — by the command that has the
file, which is the only thing that ever could.

Composition therefore happens entirely in characters, and there is no
"re-measure" step to get the order of wrong.

## Consequences

The verbatim equal-length invariant survives, and it moved from `Segment` to
`TraceMap` on the way — which is where it belonged, because it is a statement
about both sides counting the same thing and only the map knows whether they do.

A consumer that has the trace map and *not* the source file gets character
offsets. That is enough to know what came from where and how much; it is not
enough to seek in the original. Naming the limitation is better than a byte
offset that is wrong in the common case.

## What it costs

**`musubi trace` has to open the source file.** It was going to, and a caller
who wants a byte range without one is not served. If that turns out to be a real
use, the answer is a small byte-offset table at segment boundaries written into
the sidecar — an addition to the contract, priced then, not guessed at now.

**The name `source_unit` currently has one value.** Speculative generality, at
the cost of one string field, bought deliberately: the alternative is a v0.3
locator that looks exactly like a v0.1 one to anything reading the contract.
