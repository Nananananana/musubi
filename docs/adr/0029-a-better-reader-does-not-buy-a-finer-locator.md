# ADR-0029 — A better reader does not buy a finer locator

**Status:** accepted
**Date:** 2026-09-04
**Applies [ADR-0028] to a source that is not text, and records the boundary that
turned up when it was.** Upholds [ADR-0025] and `pdf_text@1`'s original
reasoning.

## Context

[ADR-0028] took a dependency for HTML and paid for it by recovering the map:
the extractor's text is *found in* the source, so the offsets come back. The
consequences section called alignment a general bridge — "any extractor that
returns text can be adapted without a fifth argument about ADR-0004".

That is not true, and PDF is where it stops being true.

**Alignment needs a source that is text.** A PDF's words live inside
Flate-compressed content streams; there is no byte range in the file containing
the sentence you are reading, so there is nothing for a run of output to be
*found in*. `domain/alignment.py` would match nothing and report every character
as transformed against the whole file — a map that is technically legal and
carries no information.

Meanwhile the reason to adopt an extractor here is different in kind, and
blunter. On HTML the question was precision: `html@1` keeps a cookie banner
`trafilatura` clears. On PDF it is **reach**:

```text
                                        pdf_text@1               pdfium@1
PDF 1.4, objects at the top level    reads 2/2 lines        reads 2/2 lines
PDF 1.5, page in an object stream  refused: no_pages        reads 2/2 lines
PDF 1.4, page with no text layer  refuses: no_text     refuses: no_text
```

*`tools/pdf_coverage.py`, fixtures from `tests/pdf_fixtures.py`.*

`pdf_text@1` finds objects by scanning for `N 0 obj`. In a PDF 1.5 the
catalogue, page tree and pages are packed into a **compressed object stream**
and reached through a cross-reference stream, so none of them is written that
way and the scan finds nothing. It reports `no_pages`, which is correct and
useless — and PDF 1.5 is what almost every current producer writes.

And there is a third fact, which is the one this ADR is really about.
**`pdfium` can report a bounding box for every character on a page.** musubi
could emit `page 3, character 47`, or a coordinate. It could not before.

## Decision

**The adapter is taken, and the locator does not change.** A `PagedConverter`
emits exactly the map `pdf_text@1` emits: one `transformed` segment per page,
`src` a half-open range of page indices, `source_unit` `opaque` ([ADR-0025]).

**Character positions within a page are declined**, though the reader now
offers them, for the reason `pdf_text@1` gave before it had the option:

> *Musubi could report a character offset within its own extraction of a page,
> and it would be reproducible only by musubi — a reader holding the PDF cannot
> count to character 47 of a page, because what "character 47" means depends on
> the order this file chose to walk the text operators. Page three is a claim a
> person can check by opening the PDF.*

That argument does not weaken when the counting gets better. It is not about
accuracy; it is about **who can check the answer**. A coordinate would be worse
still: reproducible only by a reader with the same rasteriser.

So `pdf_text@1` and `pdfium@1` produce **the same `src` spans for the same
file**, asserted by a test. A corpus rebuilt with the better reader has better
text and every citation still says *page three*.

**And the alignment's precondition is written down**: it needs a source that is
text. Where there isn't one, the honest map is the coarse one.

## Consequences

- `external.py` has two adapter shapes rather than one, and which one an
  extractor gets is a property of its source, not of the library. A future
  `.docx` reader is a question about whether its source is text, and that
  question now has a place to be asked.
- `pdf_text@1` stays, is still the default, and is still the only PDF converter
  in a zero-dependency install. It is not deprecated: it reads PDF 1.4
  correctly, and the extra is a choice rather than a migration.
- A corpus can be rebuilt with a different reader without invalidating a single
  recorded citation, because the locator did not move.

## What it costs

**musubi now knowingly discards information it is being handed.** `pdfium`
returns character boxes; the adapter drops them on the floor. That is a real
cost and it will look like a mistake to somebody who wants to highlight a phrase
in a viewer, which is a reasonable thing to want.

The answer is that the *map* is not the place for it. A trace map is a claim
about correspondence that a person can check against the file they have, and
`page 3` is checkable in a way that `page 3, character 47` is not. If highlight
coordinates are wanted later, they are a second artefact with a second contract,
produced by something that names its rasteriser — not a quietly finer number in
a field whose meaning would then depend on which converter wrote it.

**The second cost is a wheel.** `pypdfium2` bundles PDFium, which is Chrome's
PDF engine: a few megabytes of compiled C++ with no Python dependencies and a
release cadence musubi does not control. It is BSD-3-Clause and Apache-2.0, it
is the same engine already parsing PDFs on the machine of anyone who has a
browser, and it is opt-in. It is still a large amount of somebody else's code
with read access to the owner's documents, and `musubi[pdf]` is the line where
that decision is made.
