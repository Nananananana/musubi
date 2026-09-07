# What is open, in what order, and why that order

`proposals/0001-the-design.md` is the plan **as it was written before the code**,
and [AGENTS.md](../AGENTS.md) keeps it that way: it is not edited to match what
happened, because a plan edited to match the present cannot be wrong about
anything and is therefore worth nothing.

This file is the other half. It is the **order the open work is being taken in
now**, with the measurement behind each position, and it *is* kept current. It
does not restate §9. Where this order differs from §9, the difference is a
finding and it is written down here rather than smoothed away there.

Every number below is measured, with the command that re-derives it.
`docs/measurements.md` holds the tables; this holds the ordering.

## The order

| | Issue | What it is | Cost of leaving it |
|---|---|---|---|
| 1 | [#97](https://github.com/Nananananana/musubi/issues/97) | Reading order is not the document's | **Wrong text, silently.** Half done: see below |
| 2 | [#76](https://github.com/Nananananana/musubi/issues/76) | The trace map is 4.9x the corpus | A falsification condition of the design |
| 3 | [#82](https://github.com/Nananananana/musubi/issues/82) | `CONFIDENT` cannot tell right from wrong | A guess with nothing drawing attention to it |
| 4 | [#80](https://github.com/Nananananana/musubi/issues/80) | A run holds the whole corpus | A written ceiling, not yet reached |
| — | [#57](https://github.com/Nananananana/musubi/issues/57) | The first real export | **Rises with delay.** Owner, not musubi |

### Why #97 was first, and what is left of it

It was the only open issue where musubi **gave a wrong answer** rather than an
expensive one. The other three are costs and ceilings, and each is written down.
This one was not visible from anywhere inside a corpus: every word of the page
present, every offset resolving, coverage unchanged, `answer_width` unchanged,
and the sentences not the ones the document contains.

**What landed.** `pdf-reading-order` reads a PDF down its columns or across its
rows, and each reads the layout it is for exactly:

```text
  fixture                  default   +columns   +rows
  two columns                0.70      1.00      0.70
  a table                    0.67      0.67      1.00
  one line, out of order     0.67      1.00      1.00
```

**Off by default**, because no setting reads both and nothing in a file says
which it is: two columns of prose and a table can be the same geometry with
opposite correct readings ([ADR-0042](adr/0042-two-columns-and-a-table-are-the-same-page-and-opposite-readings.md)).

**What is left**, and why the issue stays open:

- `pdfium@1` has no reading-order setting. It has its own extraction and its own
  geometry, and wiring it to the same strategies is separate work.
- Columns that run right to left, as 縦書き does, are a different reading order
  and nothing in the geometry distinguishes them. That case needs composite-font
  support before it is a reading-order question at all.
- The default is still the file's own order, so a corpus with this problem today
  still has it until somebody reads the setting.

**Two defects were found on the way**, and both were in the measurement rather
than the code. Two of the three fixtures stated answers their own geometry could
not produce, so the tests recording musubi's wrongness could never have gone
green. And `Tm` — how a great many producers place every line — was missing from
the operators that end a line, so a page positioned entirely by `Tm` was read as
one unbroken word at full coverage. `docs/measurements.md` has both.

Re-derive: `uv run python tools/reading_order.py`.

### Why #76 is second and no longer what it says

Filed at 10.7x. Measured today at **4.9x**, because minifying the sidecar is
done. What is left is not whitespace:

```text
  traces/  517,140   4.9x the documents
  one .html document   2,592  map  16,614   216 segments,  16,093 minified
```

The map is now within 3% of its own minified size, so **the remaining cost is
the segments**, at roughly 74 bytes each. That moves the issue from the emitter
to the two places the original issue named as harder: a segment per line ending,
and genuinely many short segments. Both have a precision cost attached
(merging changes what `source_span_of` answers inside a run), so both need an
ADR and a measurement rather than a patch.

Second rather than first because it is a cost the design predicted and named in
§10, and costs that are known are not the ones that hurt.

Re-derive: `uv run python tools/scaling.py --only map`.

### Why #82 is third and smaller than it looks

The threshold cannot separate a right reading from a wrong one; it excludes only
a detector that recognised nothing. The issue's own third option — say louder
how many documents were read by detection — is cheap, honest, and does not
pretend to fix the detection. The other two options need measuring first.

Third because it is bounded, opt-in (`musubi[encoding]`, off by default), and
the risk is already registered as a threshold rather than dressed as a gate.

### Why #80 is fourth

A ceiling, at 1.3x to 1.5x of input, linear and written down. The fix argues
with [ADR-0008](adr/0008-a-credential-stops-the-run.md), which is fail-closed on
purpose, and §9 already flags that the argument has to be careful. Nothing
reaches the ceiling today.

### Why #57 is outside the order

musubi cannot do it. It needs a real export from a real account, and a second
one taken the same way weeks later. **It is the only item whose cost rises with
delay** — every week that passes is a week added to when the pair can be
compared. The order above is about what musubi does next; this one is about what
is being lost while that happens.
