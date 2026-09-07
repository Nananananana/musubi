# 0050. The better reader was not offered the setting

**Status:** accepted
**Date:** 2026-09-10
**Context:** [ADR-0042], [#97](https://github.com/Nananananana/musubi/issues/97), [ADR-0028]

## The problem

[ADR-0042] made reading order a setting, and wired it to `pdf_text@1`. It named
what was left:

> **`pdfium@1` has no reading-order setting.** It has its own extraction and its
> own geometry, and wiring it to the same strategies is separate work.

Written down, which is the point of writing things down, and still wrong in a
particular way: `pdf-reading-order = "columns"` was **accepted and silently
ignored** by `pdfium@1`. Not refused, not warned about — the converter simply
kept the file's own order, and the manifest recorded the plain name
`pdfium@1`, so nothing in the corpus said the setting had not been honoured.

`pdfium@1` is the reader an owner installs **because** their PDFs need a better
one ([ADR-0028]). It is the more likely of the two to be pointed at a
two-column paper, and it was the one that ignored the fix.

## Decision

**A `PageExtractor` may also say where its text sits, and one that can is
offered the reading order.**

```python
place: Callable[[], Callable[[bytes], list[list[Run]]] | None] | None = None
```

`_pdfium_runs` fills it, and the runs come from **pdfium's own text rects**:

```text
  (72.3, 717.6, 156.9, 728.6)  'Tents and poles '
  (332.5, 719.9, 413.9, 728.7)  'Stoves and fuel'
```

That matters more than it looks. Grouping characters into runs myself would
need a gap threshold — how far apart two characters are before they are two
runs — and that is a number with nothing behind it, on a path that already
carries `COLUMN_GAP`. Asking the library that laid the page out is asking
something that already knows, and it means **no new number to sweep**.

`top` rather than `bottom` for the baseline. Measured on the fixtures, tops
agree to a tenth of a point across a line where bottoms differ by two, because
a descender moves the bottom and nothing moves the top as much.
`BASELINE_TOLERANCE` covers either; this one needs less of it.

```text
  fixture                 default      +columns        +rows
                        text  pdfium   text  pdfium   text  pdfium
  two columns           0.70    0.70   1.00    1.00   0.70    0.70
  a table               0.67    0.67   0.67    0.67   1.00    1.00
  one line, out of...   0.67    1.00   1.00    1.00   1.00    1.00
```

**An extractor that cannot place its text keeps the file's order and says so by
keeping its plain name.** `pdfium@1+columns` is a different converter from
`pdfium@1` and the manifest records which ran, so a corpus states the order it
was read in — the same reason [ADR-0042] put the strategy in the name.

## What it costs

**A field on `PageExtractor` that most extractors will not fill.** The
alternative was a second protocol, which is more machinery for the same
question. `None` means *no positions*, and the converter branches on it once.

**Three more bounds in the floors register**, and they are bounds rather than
floors for [ADR-0042]'s reason: a setting asked for and half delivered is worse
than one never offered, because the owner believes the corpus is in reading
order.

**The domain algorithm is now load-bearing for two readers with different
geometry.** `pdf_text@1` derives positions from the text matrix it walks;
`pdfium@1` takes them from a C library's rectangles. That they agree on all
three fixtures is worth something, and it is also two callers to keep working
whenever `columns` or `rows` changes.

## What is still left of #97

Vertical Japanese. Columns that run right to left are a different reading order
and nothing in the geometry distinguishes them, which [ADR-0042] recorded; and
a real 縦書き fixture needs a composite font, which `pdf_text@1` refuses
([ADR-0039]) and which is therefore not a reading-order question yet. `pdfium@1`
*can* read one, so the case is now reachable for one of the two readers, and
that is a different issue from this one.

## The shape of it

[ADR-0042] wrote down what it had not done, and that is not the same as
noticing that the undone half **silently accepts the setting anyway**. A gap
recorded in prose is still a gap a user falls into; what closed it here is the
same thing that has closed the last four — the test population is read out of
what can do the thing (`extractor.place is not None`) rather than named, so the
next extractor to gain positions is covered without anybody editing a list.

[ADR-0028]: 0028-a-dependency-outside-the-domain-buys-quality-and-still-owes-a-map.md
[ADR-0039]: 0039-a-fixture-whose-answer-is-known-and-the-two-things-it-found.md
[ADR-0042]: 0042-two-columns-and-a-table-are-the-same-page-and-opposite-readings.md
