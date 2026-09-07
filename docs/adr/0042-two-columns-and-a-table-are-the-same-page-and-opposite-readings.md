# 0042. Two columns and a table are the same page and opposite readings

**Status:** accepted
**Date:** 2026-09-09
**Context:** [#97](https://github.com/Nananananana/musubi/issues/97), [ADR-0033], [ADR-0039]

## The problem

`pdf_text@1` and `pdfium@1` both read a two-column page in the order the file
holds it, which is not the order a person reads it. #97 measured it against
fixtures whose correct reading is written down, and neither reader got any of
the three right.

The failure is the comfortable kind, and that is what makes it worth an ADR
rather than a patch. Every word of the page is present. Every offset resolves to
the page it came from. `traceable_coverage` is unchanged, `answer_width` is
unchanged, the conformance suite passes, and the corpus contains sentences that
are not in the document. Nothing anywhere says so.

## What geometry can decide, and what it cannot

Reading order is a question about where runs sit, so the first half is
arithmetic: cluster the runs by their left edge to find columns, cluster by
baseline to find lines, and order them. That is `domain/reading_order.py`, and
it depends on nothing but the standard library because it is arithmetic over
coordinates.

The second half is not arithmetic. **Two columns of prose must be read down. A
table must be read across. The two can be the same geometry.** The two-column
page and the table in `tests/pdf_fixtures.py` are both two clusters of x with
shared baselines, and their correct readings are opposite:

```text
  two columns   Tents and poles / weigh two point four / … / Stoves and fuel / …
  a table       Item Mass / Tent 2.4kg / Stove 1.1kg
```

What separates them is what the words mean. That is not in the file, and no
threshold recovers it. A cell-width ratio would separate *these two fixtures*,
which is the definition of a number fitted to one corpus that [ADR-0033] exists
to refuse.

## Decision

**The reading order is a setting, `pdf-reading-order`, and its default is the
file's own order.**

- `stream` — the order the file holds them in. The default, and exactly what
  every corpus written before this has.
- `columns` — down each column, columns left to right.
- `rows` — across each line, lines down the page.

[ADR-0028]'s bargain again: offered, never claimed. A guess that silently
reorders somebody's corpus is worse than the disorder it was fixing, because the
disorder at least came from the file and can be traced to it.

**The converter name carries the strategy.** `pdf_text@1` becomes
`pdf_text@1+columns`. This is not cosmetic: an incremental sync reuses a
document when the source hash and the converter name still match ([ADR-0036]),
so without it, changing the setting would reconvert nothing. The corpus would
keep an order its settings no longer ask for, with the manifest naming a
converter that did not produce it.

**Left to right, and not otherwise.** Columns that run right to left, as
vertical Japanese does, are a different reading order, and nothing in a run's
geometry distinguishes the two. That is recorded here rather than guessed at,
and the reason it cannot simply be added is the next section.

## What it costs

**A shelf with both kinds in it cannot be right under one setting.** One
`pdf-reading-order` applies to the whole run, so a folder holding two-column
papers and tables reads one of them wrongly whichever value is chosen. The
owner splits the folders or accepts stream order for one kind. Deciding per
document would mean deciding from the page, which is the thing this ADR says
cannot be done.

**The setting can be set and be wrong, silently.** `columns` on a page of
tables produces a confident, well-formed, wrong reading, exactly as the default
does today — and now with the owner believing it was fixed. What is bought is a
lever, not a guarantee, and only the floors say the lever still works.

**A third name for the same converter.** `pdf_text@1+columns` in the manifest
and the trace map means a reader comparing corpora has three names where it had
one, and `pdf-word-gap` will multiply them again if it ever joins the name. The
alternative was worse: reuse keyed on a name that no longer describes the
output.

**Two more thresholds**, `COLUMN_GAP` and `BASELINE_TOLERANCE`, on a path that
had none. Both are registered and the first is swept; the second is bounded by
typography rather than by a sweep, which is weaker evidence and is written down
as such.

**The measurement got longer.** Reading order is now measured per strategy
rather than as one mean, so the floors register carries five PDF entries where
it carried two. That is the honest shape and it is more to keep true.

## What this cost, and the two defects it found

### A fixture that stated an answer it did not contain

`#97`'s measurement rested on three fixtures with written-down answers, and
**two of the three answers were not reachable from the fixtures**.

The table wrote its second column `len(TABLE)` rows up rather than
`len(TABLE) - 1`, so `Mass` sat one row **above** `Item` rather than beside it,
and `2.4kg` shared a baseline with `Item`. Read by baseline, that grid gives
`Mass / Item 2.4kg / Tent 1.1kg / Stove`. `TABLE_READ` described a table the
file did not contain.

The third was worse, because it was careful. It was three ASCII runs side by
side and its answer was the rightmost first, as 縦書き reads. The text was ASCII
**on purpose**: real vertical Japanese needs a composite font, whose bytes are
glyph indices, which is what [ADR-0039] made `pdf_text@1` refuse. Its own
docstring records the first draft's mistake — writing UTF-8 into a Helvetica
string, and so stating an answer no correct reader could produce. The second
draft removed the script and kept the answer, and removing the script removed
the only evidence that the columns ran right to left. Three runs side by side
are three runs side by side whichever way the script goes.

Both fixtures asserted targets nothing could reach. **A test asserting that
musubi gets a layout wrong passes just as happily when the layout is
impossible.** It can never go green, so it never tells anybody anything: a red
that is red about nothing, which is the same family as this repository's
recurring green that is green about nothing and had not been named before.

The guard is `test_every_stated_answer_is_reachable_by_some_strategy`. If no
strategy reaches a stated answer, either musubi is missing one or the fixture is
wrong, and a person should find out which. It was verified against the
reintroduced defect before being trusted.

The table's grid is fixed. The vertical fixture is replaced by one whose answer
its geometry supports, and the real 縦書き case is filed rather than faked —
it needs composite-font support first, so it is not a reading-order question
yet.

### `Tm` was not a line break

Found on the way, and larger than the thing being looked for. `_BREAK` listed
`T*`, `TD`, `Td` and `TL` but not `Tm`, which sets the text matrix absolutely
and is how a great many producers place **every single line**. Two separately
placed runs were therefore concatenated with nothing between them: three runs
came out as `middlerightleft`, one unbroken word, at full coverage, with every
offset still resolving to the right page.

A page positioned entirely by `Tm` was being read as a single word and nothing
in the corpus said so. It is fixed, and the fixtures that found it are the ones
that were built for a different question.

## Consequences

**A shelf with papers and tables in it cannot be right under one setting.** The
owner splits the folders or accepts stream order for one kind. This is stated in
`docs/configuration.md` rather than being left for somebody to discover.

**`pdfium@1` has no reading-order setting.** It has its own extraction and its
own geometry, and wiring it to the same strategies is separate work. Its
reading-order number is measured and floored as it stands, which says the extra
is not covered rather than implying it is.

**The default changed nothing**, which is the point, and it is also the risk:
the corpus that has this problem today still has it until somebody reads the
setting. The floors register carries all three geometric bounds so the strategy
cannot quietly stop working, and the stream-order number stays measured so the
default cannot quietly get worse.

**A threshold arrived.** `COLUMN_GAP` is swept in `tools/sensitivity.py --only
columns`, which shows both edges of its plateau: 20 to 259 on the two cases that
bound it. 24 is two 12pt line heights, which is a reason rather than a fit, and
the sweep is what says it lands somewhere safe.

[ADR-0028]: 0028-a-dependency-outside-the-domain-buys-quality-and-still-owes-a-map.md
[ADR-0033]: 0033-a-threshold-that-nobody-swept-is-a-number-fitted-to-one-corpus.md
[ADR-0036]: 0036-a-unit-whose-bytes-did-not-change-is-not-converted-again.md
[ADR-0039]: 0039-a-fixture-whose-answer-is-known-and-the-two-things-it-found.md
