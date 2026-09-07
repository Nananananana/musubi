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

## The order, and where each one ended up

All four code items have been worked, in this order. **Three of the four are
still open**, and each says below exactly what is left of it. An issue closed
because something was done to it, rather than because the thing it describes
stopped being true, is a corpus of green checkmarks over a project that still
has the problem.

| | Issue | What it is now | Where it stands |
|---|---|---|---|
| 1 | [#97](https://github.com/Nananananana/musubi/issues/97) | Reading order is a setting, honoured by both readers | **open** — 縦書き remains |
| 2 | [#76](https://github.com/Nananananana/musubi/issues/76) | The trace map is 1.5x the corpus, from 10.7x | **closed** |
| 3 | [#82](https://github.com/Nananananana/musubi/issues/82) | The corpus now says which readings are guesses | **open** — detection is no better |
| 4 | [#80](https://github.com/Nananananana/musubi/issues/80) | A run holds 0.8x of what it read, from 1.9x | **open** — still linear |
| — | [#57](https://github.com/Nananananana/musubi/issues/57) | The first real export | **owner, not musubi.** Cost rises with delay |

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

- ~~`pdfium@1` has no reading-order setting.~~ **Done.** It takes its runs from
  pdfium's own text rects, so no threshold was invented for grouping characters,
  and it reads all three layouts exactly under the right strategy
  ([ADR-0050](adr/0050-the-better-reader-was-not-offered-the-setting.md)). It
  had been **accepting the setting and silently ignoring it** — which the
  previous ADR recorded as not-yet-done and did not notice was worse than that.
- Columns that run right to left, as 縦書き does, are a different reading order
  and nothing in the geometry distinguishes them. That case needs composite-font
  support before it is a reading-order question at all, and `pdfium@1` can read
  one — so it is now reachable for one of the two readers, which makes it a
  different issue rather than this one.
- The default is still the file's own order, so a corpus with this problem today
  still has it until somebody reads the setting.

**Two defects were found on the way**, and both were in the measurement rather
than the code. Two of the three fixtures stated answers their own geometry could
not produce, so the tests recording musubi's wrongness could never have gone
green. And `Tm` — how a great many producers place every line — was missing from
the operators that end a line, so a page positioned entirely by `Tm` was read as
one unbroken word at full coverage. `docs/measurements.md` has both.

Re-derive: `uv run python tools/reading_order.py`.

### Why #76 was second, and where its cost actually was

Filed at 10.7x, and §10 named it as a falsification condition: *if a map
routinely exceeds its document, the guarantee costs more storage than the
corpus*. It did, by an order of magnitude.

```text
                     filed      minified       now
  traces/            10.7x         4.9x        1.5x
  a segment            ---      71 bytes   18.9 bytes
```

The proposal predicted **the fix is converter-side**. It was wrong twice.
Minifying the sidecar took it to 4.9x, after which a map was within 3% of its
own minified size — so the remaining cost was neither whitespace nor the
converter. It was the segments: five key names and a rule string, written out
once per segment. A segment is now a row of numbers with those hoisted into
tables the file carries, and the output start is not stored at all because the
tiling already determines it
([ADR-0043](adr/0043-a-segment-is-a-row-of-numbers-and-the-tiling-supplies-the-rest.md)).

At 1.5x a map still exceeds its document and is now the same order of magnitude
as the corpus rather than an order above it. The map stays mandatory, which is
what the falsification condition was actually asking.

**One idea was measured and discarded before it was built.** Merging adjacent
removals costs no precision, because a removal has no output for a query to land
in. On the worst real case not one adjacent pair shared a rule — they alternate
`markup.tag.a`, `boilerplate.nav`, `markup.tag.a` — and merging across rules
would drop the attribution ADR-0005 exists for.

Re-derive: `uv run python tools/scaling.py --only map`.

### What was done about #82, and why it stays open

The threshold cannot separate a right reading from a wrong one: every miss
reported 100% coherence. The issue offered three ways forward and asked for the
first to be measured rather than assumed.

**Measured, the runner-up does not separate them either.** A rival reading —
another candidate decoding the same bytes to different text — fires on eight
readings to find two wrong ones, which is about the entropy tier's precision
that ADR-0017 made opt-in for the same reason. The score gap says the same: two
of the three misses had the correct encoding at rank two with a gap of exactly
0.0000, and so did a case the detector got right.

So musubi does the third option: it records **which readings are guesses** and
does not rank them. `encoding` and `encoding_detected` are in the manifest, and
the run report says how many
([ADR-0044](adr/0044-a-second-opinion-from-the-same-detector-is-not-a-second-opinion.md)).
The issue's premise that the manifest already carried the encoding was wrong —
only the trace map did — which is why this was more than a print statement.

**`CONFIDENT` does not move.** Raising it would exclude nothing that is wrong
and start refusing files that read correctly.

It stays open because detection is no better than it was. The one remaining
idea with evidence behind it is #82's second: **use the file's neighbours**, on
the grounds that a vault is usually written in one encoding. That is a design
change, because `Source` reads one unit at a time on purpose, and it is a bigger
piece of work than this was.

Re-derive: `uv run python tools/encoding_detection.py`.

### What was done about #80, and why the diagnosis mattered more than the fix

Re-measured before anything was built, a run held **1.9x** what it read, not
the 1.3x this repository had recorded for months. Nothing had noticed, because
`tools/scaling.py` prints and no test compared.

#80 named three causes, all read off the code: the accumulated artefact lists,
the staging ADR-0008 requires, and `Source.read()` handing back whole units. It
concluded a fix meant a careful argument about fail-closed promotion.

**The peak was in none of them.**

```text
  after run (all staged)    peak  595,598   0.56x
  after render(manifest)    peak 2,008,425  1.89x     <- here
```

Rendering the manifest added 1.33x of the whole input, transiently, to build a
269 kB file, because `json.dumps` builds every piece and then joins them.
Streaming it out took the run to **0.8x**, and ADR-0008 was never touched
([ADR-0045](adr/0045-the-peak-was-the-manifest-and-nobody-had-looked.md)).

`tests/test_memory_ceiling.py` is now the gate, so the number cannot drift
silently again. It was checked against the old behaviour first and fails at
2.04x.

It stays open because the growth is still **linear** — the accumulated lists
are real — so the shelf ADR-0007 describes still has a ceiling. The constant
fell by 2.4x and the cause is now known, which is a different position to be in.

Re-derive: `uv run python tools/scaling.py --only memory`.

### Why #57 is outside the order, and the only one still costing

musubi cannot do it. It needs a real export from a real account, and a second
one taken the same way weeks later. **It is the only item whose cost rises with
delay** — every week that passes is a week added to when the pair can be
compared, and no amount of work here shortens it.

Nothing above was blocked on it, and nothing above shortened it either. The
order in this file is about what musubi does next; this one is about what is
being lost while that happens.

## What the four had in common

Worth writing down, because it was not the plan.

**Three of the four were not where they were filed.** #76's remaining cost was
predicted to be converter-side and was in how a segment was written down. #80's
peak was blamed on three things read off the code and was in none of them.
#97's own measurement rested on two fixtures stating answers their geometry
could not produce. In each case the code was read, a cause was reasoned out, and
measuring found somewhere else.

**Two of the four were guarded only by a printout.** `tools/` measured and
nothing compared, so the trace-map ratio and the memory ratio had both drifted
with no test, report or reader able to say so. That is #84's finding, and it
turned up twice more while these were being worked. Both now have gates with
their headroom written down.
