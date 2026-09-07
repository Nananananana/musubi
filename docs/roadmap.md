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
| 5 | [#114](https://github.com/Nananananana/musubi/issues/114) | The skip vocabulary is prose, not a document | **open** — nobody has asked |
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

## Where every number stands, measured today

Re-derived rather than remembered. Each row names the command.

| | when it was filed | now | |
|---|---|---|---|
| Trace map, against the documents | 10.7x | **1.5x** | `scaling.py --only map` |
| What a run holds, against what it read | 1.9x | **0.8x** | `scaling.py --only memory` |
| A re-sync that changed nothing | 1.01 | **0.30** | `scaling.py --only resync` |
| A cold sync, 300 documents | 1.49s | **1.19s** | interleaved A/B |
| Syscalls in that sync | 9,350 | **3,350** | exact, `cProfile` counts |
| Archive reads per unit | O(n) | **O(1)** | `scaling.py --only archive` |

And the two nobody had measured before this week:

```text
  verify, 400 artefacts     0.367s     half of it materialising trace maps
  export, 400 documents     0.131s     a third of it resolving paths
```

**Neither is a problem and both are worth having written down.** `verify`
re-reads every document and every map and rebuilds each map as objects; that is
the work, not overhead. `export` is fast enough that the 40% it spends on
`resolve()` is 0.05 seconds, which is not worth weakening a security check that
carries a written argument for asking the filesystem.

### The survey that found four non-problems and one message

Worth recording as carefully as the fixes, because *measured and discarded* is
a result and because each of these looked like a defect first.

| probed | verdict |
|---|---|
| The journal grows one entry per run, forever | **fine.** 675 bytes a run after the first; sync time flat over 60 runs; reading 60 entries 1.6ms |
| A citation, which is the core promise | **fine.** 1.6ms, and `Corpus` deliberately caches nothing across calls |
| `musubi export` holds the corpus | **no.** It streams. Its peak is 99–100% the *manifest*, parsed |
| Every text document is decoded twice | **true and irrelevant.** 0.003ms a note, 0.08% of a run |
| Two runs into one destination | **a message, not a defect** — see below |

The double decode is the sharpest of these. `Decoding` decodes the bytes to
find out whether it can, throws the text away, and the inner converter decodes
the same bytes again — which reads like an obvious waste and costs one part in
twelve hundred. Fixing it would have meant a change to the converter port.

**What the export probe did establish** is a number worth having: a manifest
parses to **3.1× its size on disk**, and that is the memory floor of every
command that opens a corpus — `sync` reading the previous one, `verify`, and
`export`. It is the same ceiling [#80] records, stated more precisely, and the
manifest has no cheap win in it: hashes are 21% of the artefacts array,
`path` and `trace_map` are 8% and derivable from `unit_key` but are contract
fields a consumer reads, and indentation is 22% and deliberate.

### What performance work here has to look like

Two corrections came out of doing it, and both are about the instrument.

**A stale number reads as a solved problem.** `Path.resolve()` was recorded as
fixed at 7% and was back at 12%, because a later refactor put the syscall on
every write. Nothing measured it again until somebody did.

**The profiler and the stopwatch disagree in a predictable direction.**
`cProfile` charges per call, so tens of thousands of tiny Python calls read as
24% of a run when a stopwatch says 5%. Acting on that profile would have meant
rewriting the composition algorithm for a twentieth of the run.

So the rule this arrived at, and the reason the table above quotes counts:
**count something exact, and use the clock only to corroborate.** Syscall
counts do not move between runs, between machines, or with what else the laptop
is doing — this one is noisy to ±15%, which is larger than most wins worth
having.

### What is left, and why none of it is scheduled

- **Memory is still linear.** 0.8x of input, and the remaining half is the
  manifest document built whole before it is streamed out. Streaming that too
  means writing JSON by hand around a generator of artefacts, and the manifest
  is the one document here whose exact bytes are a contract. [#80] holds it.
- **Trace maps are materialised to be checked.** Half of `verify`. A map that
  could be checked without building every `Segment` would halve it, and would
  mean a second reader of the format beside `unpacked` — which is the thing
  `trace_format` exists to prevent.
- **Nothing else measured is above noise.** The sync path's remaining cost is
  `open` and `replace`, which are the writes themselves: one read and two
  writes per document, which is the floor for staging plus atomic promotion.
- **A manifest parses to 3.1x its size**, and that is the memory floor of
  `sync`, `verify` and `export` alike. Lowering it means not parsing it whole,
  which means a streaming JSON reader, which means a dependency [ADR-0001]
  refuses. [#80] holds this too.

### The degenerate-input pass, and the one number it left open

Sixteen shapes through a real sync — empty files, a lone byte-order mark,
whitespace only, an unclosed fence, a 200 kB single line, NUL, BEL, VT, form
feed, CRLF, lone CR, empty HTML and PDF. Everything was handled sensibly except
two, and one of them was the worst defect found this month
([ADR-0054](adr/0054-utf-16-without-a-mark-is-valid-utf-8.md)).

The other is **open, deliberately**: a title is as long as the heading it came
from. A 200,000-character heading gives a 200,000-character title in the
manifest, which is then paid for at about 3.1× on every command that opens the
corpus.

Every fix has a real objection. Truncating contradicts what the field *is* —
[ADR-0040]'s *the title is the document's claim, repeated* — and any length is
a threshold with nothing swept behind it, which [ADR-0033] refuses. So it is
written down in `docs/contracts.md` where a consumer reads, with the advice to
clamp, and left for a decision rather than taken by one.

### And one constraint that turned out to need a sentence rather than a fix

**Two runs into one destination.** There is no lock, so a second run clears the
first one's staging area. Probed deliberately, with the second `begin()`
landing after four of six documents had been promoted: the corpus ends up
**ahead of its own account**, `verify` names all eight faults, and the next
ordinary sync repairs every one. [ADR-0008]'s promotion order was doing its job
before anybody checked.

What was wrong was that it arrived as `Unreadable: the file system refused` — a
sentence about a machine that was fine. It is `InterruptedRunError` now, and
one of the two kinds musubi marks retryable, because running the sync again
*is* the repair ([ADR-0053](adr/0053-a-run-that-was-interrupted-says-so.md)).

That is the third constraint this month that was reasonable, designed for, and
written down nowhere — after one source per destination, and the skip
vocabulary. In all three the **code handled the case correctly and the person
was not told**, which is a different failure from a bug and needs looking for
differently: by asking what happens, rather than by reading what should.

[ADR-0001]: adr/0001-the-domain-depends-on-nothing.md
[ADR-0008]: adr/0008-a-credential-stops-the-run.md

[#80]: https://github.com/Nananananana/musubi/issues/80

## What the four had in common

Worth writing down, because it was not the plan. **Everything below has since
happened three more times**, in a schema description, in a contract's own
prose, and in a test whose docstring argued for a distinction its assertions
destroyed ([ADR-0047] through [ADR-0051]).

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

**And the shape kept going.** Since then: a contract shipped with no schema and
no line in the document that publishes it; a reused manifest record republishing
values musubi had invented for it; a second source silently deleting the first
one's corpus; a published vocabulary of twenty-two skip reasons that named
eight; and a distinction the contract told consumers to branch on that musubi
had never once produced. Each was found the same way — by asking what the
population was, or by checking a claim against the thing it described — and the
last one was found because a **consumer wrote their reading of the contract
down where musubi could read it back**.

The generalisation is not *people forget*. It is that **a list beside a thing
has no reason to change when the thing does**, and a promise in prose has no
reason to be true.
