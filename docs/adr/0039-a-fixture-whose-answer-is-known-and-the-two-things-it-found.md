# ADR-0039 — A fixture whose answer is known, and the two things it found

**Status:** accepted
**Date:** 2026-09-07
**Measuring *converted correctly* rather than *converted*, and refusing a font whose text nobody here can read.**

## Context

musubi measures three things and none of them is correctness:

| | what it says | what it does not say |
|---|---|---|
| `traceable_coverage` | an offset resolves to a place in the source | that the text is right |
| `answer_width` | how tightly it resolves ([ADR-0038](0038-the-number-that-goes-up-when-the-guarantee-stops-holding.md)) | that the text is right |
| the conformance suite | the map is structurally honest | that the text is right |

The `Limits` block has always admitted it in words — *a traceable character
means an offset resolves; it does not mean the conversion read the document in
the right order* — and **saying it is not measuring it** (#85, and the review's
§2.1: 「変換できた」と「正しく変換された」を分離評価する).

Every PDF fixture in the repository was one this converter reads correctly. A
suite whose samples are all easy is a suite that cannot tell a good converter
from a bad one.

## Decision

**Fixtures whose correct reading is written down**, built byte by byte in
`tests/pdf_fixtures.py` rather than collected — a file whose right answer
nobody can state measures nothing.

```text
two_columns()   laid out by baseline, read by column      COLUMNS_READ
a_table()       written down columns, read across rows    TABLE_READ
vertical()      columns that run right to left            VERTICAL_READ
composite()     glyph indices; there is no right text     (refusal)
scanned()       no text layer; a refusal must stay one    (refusal)
```

`tools/reading_order.py` reports each converter against each answer, and
`tests/test_reading_order.py` holds the results as assertions.

### What it found first: neither converter reads any layout correctly

```text
  fixture                  pdf_text@1   pdfium@1
  two columns                  0.70       0.70     every word, wrong order
  a table                      0.67       0.67
  right-to-left columns        0.67       0.67
```

Every word of the document is present and the order is not the document's.
Coverage is unchanged, every offset resolves, and the prose is not in the file.
That is the difference #85 was filed to make visible, and it is now a number.

**This is recorded and not fixed.** Reading order needs geometry — clustering
runs into columns, ordering the clusters — and that is a converter, not a
patch. The tests assert the *wrongness*, with the answer beside it, so the day
somebody fixes it they go red and the reader is told. A measured limitation
nobody has written down is indistinguishable from one nobody has found.

### What it found second, which is a defect: a composite font was read as numbers

Under a `Type0` / `Identity-H` font — **how every PDF holding Japanese encodes
its text, and how most current producers encode a subsetted Latin font** — the
bytes a `Tj` shows are *glyph indices*. The map from those to characters is in
the font's `ToUnicode` CMap, which `pdf_text@1` does not read.

It read them as characters anyway:

```text
<0024002500260027> Tj   ->   "\x00$\x00%\x00&\x00'"
```

The font's internal numbering, **including NUL bytes**, written into a corpus
document at full traceable coverage, with nothing anywhere saying so. Not an
edge case and not documented.

**`pdf_text@1` now refuses a document declaring a composite font**, with reason
`composite_font` and a detail naming `musubi[pdf]` — which reads the CMap. The
detection is a scan for `/Subtype /Type0` and has no threshold in it.

Refusing beats emitting because the output was not the document's text in the
wrong encoding; it was a different document's numbering. A refusal that names
the extra is an answer. Mojibake at 100% coverage is not.

## Consequences

- The refusal fires exactly where the output was previously garbage, so no
  readable text is lost by it: a file using a composite font produced glyph
  numbers before and produces a named refusal now.
- `pdfium@1` reads the composite fixture without refusing, which is the
  measured case for the extra — and on this fixture it gets a stub CMap, so
  what it produces there is not evidence about a real file either way.
- The vertical fixture is **ASCII on purpose**. Its first draft wrote UTF-8 into
  a Helvetica string and stated an answer no correct reader could produce from
  those bytes: it would have recorded its own mistake as musubi's. What is left
  is the geometry, which is what reading order is about; the script belongs to
  `composite()`.
- Closes #85. Reading order is filed separately, because it is work rather than
  a fix.

## What it costs

**A document that used a composite font for one glyph is now refused whole.**
A producer that sets the body in Helvetica and one symbol in a Type0 font
loses the body too. The alternative is a document that is part text and part
glyph numbers with no way to tell which, which is worse — but the cost is
real, and the fix for a reader who meets it is an extra rather than a setting.

**The scan can be wrong.** `/Subtype /Type0` inside a content stream, by
coincidence, refuses a document that would have read correctly. The converter
already accepts that class of risk (it scans for `N 0 obj` rather than reading
the cross-reference table, on purpose), and a false refusal names a way
forward where a false read does not.

**And three tests now assert that musubi is wrong.** They have to be rewritten
when reading order is fixed, and a test that has to be rewritten to make a fix
land is friction on exactly the change most worth making. Naming the answer in
the assertion message — *that is good news and this test is the wrong shape for
it* — is the whole mitigation.
