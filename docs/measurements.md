# Measurements

**This is a current-state document.** Every number here names the script that
produced it, the corpus it ran on, and what it does not cover. A number without
those three is not written down.

`docs/proposals/0001-the-design.md` §9 lists six metrics that v0.4 owes and §10
lists what would falsify the design. **Four of the six are measured. Two are
not, and they are named at the bottom rather than estimated.**

Two of the four are bad, and one is bad in a way the proposal predicted the
wrong fix for. That is the falsification section working.

| Metric | Value | Verdict |
|---|---|---|
| Traceable coverage, HTML | 93.5% built-in, **99.7%** via `trafilatura@1` | holds |
| Trace map size | 10.7× → **1.5× the corpus** | fixed, and not where the roadmap predicted ([#76](https://github.com/Nananananana/musubi/issues/76)) |
| Composition | **quadratic** → linear, 33× faster | fixed |
| Re-read ratio | **0.32**, from 1.01 | falsified, then fixed (ADR-0036) |
| Archive reads per unit | **O(1)** archives opened | fixed in [#78](https://github.com/Nananananana/musubi/issues/78) |
| Screener precision, synthetic | **0.00%** false stops after ADR-0026 | holds |
| What a run holds | 1.9× → **0.8× of what it read** | cause found, still linear ([#80](https://github.com/Nananananana/musubi/issues/80)) |
| Encoding detection | 17 of 19 recovered; **the confidence cannot tell which two** | recorded, not fixed ([#82](https://github.com/Nananananana/musubi/issues/82)) |
| Cleansing precision | not measured | owed |
| Screener recall | not measured | owed |

---

## Trace map size — 10.7× the documents, now 1.5×

```text
uv run python tools/scaling.py --only map
20 generated HTML pages and 20 Markdown notes, one real sync

                     filed      minified       now
  traces/            10.7x         4.9x        1.5x
  everything         11.9x         6.1x        2.7x
  one .html map      14.0x         6.4x        1.8x
  one .md map         7.6x         3.4x        1.1x

  a segment            ---       71 bytes   18.9 bytes
```

§10 says: *if a map routinely exceeds its document, the guarantee costs more
storage than the corpus*. It did, by an order of magnitude, and the proposal's
predicted remedy — *the fix is converter-side* — was **wrong twice over**.

Minifying took it to 4.9×, and after that a map was **within 3% of its own
minified size**: what remained was not whitespace and not the converter, it was
the segments, at 71 bytes each, nearly all of it five key names and a rule
string repeated once per segment. Writing a segment as a row of numbers with
those hoisted into tables took it to **1.5×**
([ADR-0043](adr/0043-a-segment-is-a-row-of-numbers-and-the-tiling-supplies-the-rest.md)).

At 1.5× a map still exceeds its document, and it is now the same order of
magnitude as the corpus rather than an order above it. That is what the
falsification condition was about, and it is a different sentence about the
project.

**One thing was measured and discarded.** Merging adjacent removals is free —
a removal has no output, so no query can land inside one — but on the worst
real case, 68 of 81 segments were zero-length removals and **not one adjacent
pair shared a rule**: they alternate `markup.tag.a`, `boilerplate.nav`,
`markup.tag.a`. Merging across rules would drop the attribution ADR-0005 exists
for. It bought nothing, which is a thing worth knowing before building it.

The numbers below are the measurement that showed where to look:

- **`indent=2`.** The sidecar is written indented on the stated grounds that it
  is *the file a reviewer opens*. The indentation is about as many bytes as the
  data: 36,241 down to 16,093 for one HTML map. Emitter-side, not converter-side.
- **One segment per line ending.** A file written on Windows produces a
  `transformed` segment per CRLF, so 82 of a Markdown note's 124 segments are
  `line_ending`. The same note authored on Linux produces none of them. This is
  not a violation of [ADR-0003] — the input bytes genuinely differ — but it does
  mean **map size depends on the author's platform**, which nothing anywhere
  said.
- **The rest is genuinely converter-side**, and `html@1` is the worst of them at
  216 segments for 2.6 kB.

Filed as [#76](https://github.com/Nananananana/musubi/issues/76).

## Composition was quadratic, and 112 kB took five seconds

```text
links     bytes      sync   growth        after
  100    13,840     0.09s                 0.04s
  200    27,840     0.18s     2.1x        0.05s
  400    55,840     0.62s     3.5x        0.09s
  800   111,840     5.29s     8.5x        0.16s   **33x**
 1600   225,040         -                 0.35s
 3200   452,240         -                 0.86s
```

The page is a blog index or a newsletter archive — links with tracking
parameters on them, so the converter's map and the cleanser's map are **both
dense**. `TraceMap.followed_by` scanned every segment of the earlier map for
every segment of the later one, and the growth factor was still rising at
800 links.

The segments tile the output in order, so `out.end` is non-decreasing and the
window is a bisection. `tests/test_composition_is_linear.py` keeps the old
algorithm and compares the two on generated maps, because an optimisation to
the core of [ADR-0004] that quietly changed an answer would make every citation
in every corpus built afterwards wrong with nothing to say so.

## A 300-document sync, by where the time went

```text
before   4.83s
after    1.52s     **3.2x**
```

| | share of the profile | what it was |
|---|---|---|
| encoding the sidecars | 27% | `indent=2`, most of it whitespace |
| composition | 18% | the quadratic above |
| `Path.resolve()` in `_inside` | 7% | a syscall per check, twice per artefact |

### The third one came back, and the profile was lying about the second

Re-measured after the trace-map and manifest work, `Path.resolve()` was **12%
again** — a refactor had routed both writers through one checked helper, which
was right, and put the syscall back on every write. And the profile said
composition was 24%, which it is not: `cProfile` charges per call, and
composition is a few tens of thousands of very small Python calls. Timed
directly it is about 5%.

**So the counts are the measurement and the clock is the corroboration.**
Syscalls for the same 300 documents, which are exact and do not move with the
machine:

```text
                        before    after
  _getfinalpathname      3,627      620
  nt.mkdir               1,206       10
  nt.stat                3,013    1,216
  nt.replace               601      601     the real work, untouched
  _io.open                 903      903
```

Six thousand syscalls removed, twenty per document. Wall clock, interleaved
A/B on a laptop noisy to ±15%, three rounds each: **1.49s → 1.19s**, with every
"after" below every "before".

Both come from the same observation: musubi was asking the filesystem about
paths **it had just built itself** ([ADR-0052]). The staging area is made fresh
by `begin()`, so the only thing a resolve defends against there is a key that
walks out with `..`, which is arithmetic on a string. The two checks that
*delete* still ask the disk.

The first of those is also part of the map-size problem above: minified, one
HTML map goes from 36,241 bytes to 16,588, and `traces/` from 10.7× the
documents to **4.9×**. The reason for indenting was that a reviewer opens these;
a reviewer can pipe one through `jq`, and nobody gets the disk back. The rest of
that cost was the segments themselves, and rows took `traces/` to 1.5×.

## Re-read ratio — 0.32, from 1.01

```text
uv run python tools/scaling.py --only resync
400 unchanged Markdown notes

                          before ADR-0036     after
  cold sync                     2.11s         1.69s
  no-change re-sync             2.13s         0.54s
  re-read ratio                  1.01          0.32
```

[ADR-0006]'s claim is that *a re-export that changed nothing produces an empty
diff*. Before [ADR-0036](adr/0036-a-unit-whose-bytes-did-not-change-is-not-converted-again.md)
a no-change re-sync cost the whole of a cold one and rewrote every artefact:
`Change` existed and nothing called it. Now a unit whose bytes hash to what the
previous manifest recorded, under the same ruleset, screener, allowances and
musubi, with its artefact still on the disk as recorded, is carried forward
unconverted, and the re-sync promotes one file.

**0.32 is not near zero, and the remainder is the honest floor.** Every source
is still read and hashed, and every artefact is read back and checked against
the manifest rather than trusted. The `mtime`-and-size shortcut that would take
the ratio lower was declined — [ADR-0022] already found modification times
saying things that were not so.

Two runs on a laptop, generated notes; the ratio is the number and the seconds
are not. Filed and closed as [#77](https://github.com/Nananananana/musubi/issues/77).

## Traceable coverage — the number ADR-0004 lives on

```text
uv run python tools/html_coverage.py        one generated page

converter            text  boilerplate   content  traceable
html@1                431       3/6       3/3        93.5%
trafilatura@1         352       6/6       3/3        99.7%
```

```text
uv run python tools/pdf_coverage.py

                                        pdf_text@1               pdfium@1
PDF 1.4, objects at the top level    reads 2/2 lines        reads 2/2 lines
PDF 1.5, page in an object stream  refused: no_pages        reads 2/2 lines
PDF 1.4, page with no text layer     no_text_layer          no_text_layer
```

**What these do not cover.** Both fixtures are generated. A generated page has
the shape of a real one and none of the mess, so these answer the *relative*
question — is one converter better than another on the same input — and not
*what coverage a real shelf of documents would get*. That number needs a
collected corpus, which v0.4 also owes.

## Encoding detection — right often, and it cannot tell you when

```text
uv run python tools/encoding_detection.py

  a paragraph of prose   17 of 19 recovered exactly
  one line of prose      16 of 19
```

**Every one of the misses reported 100% coherence.** French in Latin-1 read as
cp1250, Russian in KOI8-R read as `shift_jis_2004`, all confidently. So
`CONFIDENT = 0.3` cannot separate a right reading from a wrong one; it excludes
only the case where the detector found nothing at all, which is a much smaller
job than it looks like.

### The runner-up does not separate them either

#82 proposed taking the second-best candidate into account and was explicit
that it needed measuring. Measured, on the same corpus, where *a rival reading*
means another candidate that decodes the same bytes to different text:

```text
  a rival reading exists    right    WRONG
  no                           11        0
  yes                           6        2
```

It fires on eight readings to find two wrong ones. As a gate that is about the
entropy tier's published precision of 21.1%, which
[ADR-0017](adr/0017-entropy-is-a-tier-not-a-default.md) made opt-in and off by
default for exactly this reason.

The score gap says the same. Two of the three misses had the correct encoding
at **rank two with a chaos gap of exactly 0.0000** — and so did a case the
detector got right.

### So the corpus says which readings are guesses

The manifest carries `encoding` and `encoding_detected` per artefact, and the
run report says how many:

```text
  1 of 2 read by detecting the encoding, which is a guess and not a
  reading of a declaration
    cp932  1x
```

That does not fix detection and does not claim to
([ADR-0044](adr/0044-a-second-opinion-from-the-same-detector-is-not-a-second-opinion.md)).
It stops the corpus being quiet about the fact that detection happened. `#82`
assumed the manifest already recorded the encoding per artefact; it did not,
only the trace map did, so the question *how much of this corpus rests on a
guess* meant opening every sidecar.

**`CONFIDENT` does not move.** Raising it would exclude nothing that is wrong
and would start refusing files that read correctly.

## Screener precision — 0.00% false stops, on synthetic blobs

```text
uv run python tools/screener_false_stops.py
300 blobs of 100,000 characters per population, seed 20260904, 21 signatures

population    before ADR-0026    after
base64                  1.00%    0.00%
base64url               3.33%    0.00%
hex (lower)             0.00%    0.00%
hex (upper)             0.00%    0.00%
```

Under [ADR-0008] a hit stops the whole run, so this is the difference between a
gate and an obstacle course. 100,000 characters is one 75 kB image pasted into a
note.

**What this does not cover.** It is precision on *noise*, not on documents. A
real corpus contains strings that look like credentials for reasons a random
generator cannot produce — an example key in a tutorial, a redacted token in a
bug report. And it says nothing at all about recall.

## What a run holds in memory

```text
uv run python tools/scaling.py --only memory

   notes      input         peak  peak/input
     100    273,200      256,086        0.9x
     200    546,400      429,301        0.8x
     400  1,092,800      820,399        0.8x
```

**Still linear, and the constant is 2.4x smaller than it was.** A run held 1.9x
of what it read; it now holds 0.8x, which is less than the corpus rather than
more.

### The cause was in none of the three places it was filed under

[#80](https://github.com/Nananananana/musubi/issues/80) named the accumulated
artefact lists, the staging that ADR-0008 requires, and `Source.read()` handing
back whole units. Measured phase by phase through a 400-note run:

```text
  after previous + begin    peak    2,053   0.00x
  after run (all staged)    peak  595,598   0.56x
  after render(manifest)    peak 2,008,425  1.89x     <- here
  after promote             peak 2,008,425  1.89x
```

The accumulation is real and it is 0.56x. The peak is **rendering the
manifest** — 1.33x of the whole input, transiently, to produce a 269 kB file,
because `json.dumps` builds every piece and then joins them. Streaming it out
instead fixed it, and ADR-0008 was never touched
([ADR-0045](adr/0045-the-peak-was-the-manifest-and-nobody-had-looked.md)).

### And the number had drifted, with nothing watching

This section said 1.5x, 1.3x, 1.3x. By the time anybody looked again it was
1.8x, 1.7x, 1.7x, and no test and no report could have said so — `tools/` prints
and nothing compares, which is #84's finding in a second place.
`tests/test_memory_ceiling.py` is now the gate, sized above the measurement with
the headroom written down, and checked against the old behaviour before being
trusted.

**What is still true**: the growth is linear, so the "everything you have ever
written" case [ADR-0007] describes still has a ceiling. #80 stays open for it.

## What an export holds, and where its time goes

```text
2,000 generated notes, 6.5 MB as JSON Lines, one laptop

                         before        after
  export --format jsonl   2.61s         1.73s
  peak memory            19.7 MB        2.8 MB
  export --format parquet   --          0.88s   peak 7.4 MB
```

**The command held the whole export twice.** Every line was built into a list
and joined before a byte was written: 19.7 MB peak for a 6.5 MB file, and a
corpus larger than memory would have failed on exactly the corpus the export
was for. `documents()` was already a generator; the command now consumes it a
line at a time, and the peak is one document.

**And 44% of the time was resolving the same directory 2,000 times.** The
check that a manifest path stays under `documents/` asks the filesystem rather
than the string, on purpose (`C:/Windows/win.ini` leaves a corpus without a
`..` in sight) -- but it resolved the *root* once per key as well as the key.
Resolved once per corpus now. What remains is one `open()` per document, which
is the floor.

The Parquet peak is the row group: a thousand rows held, written, dropped. The
generated notes compress to almost nothing, so the file size says nothing about
a real corpus and is not listed.

## What a source re-reads to hand over one unit

```text
uv run python tools/scaling.py --only archive

 pages    archive   read all   per page          touched
    50     12,358     0.027s     0.54ms          617,900
   100     24,581     0.061s     0.61ms        2,458,100   2x pages -> 2.2x time
   200     49,333     0.189s     0.94ms        9,866,600   2x pages -> 3.1x time
   400     98,866     0.660s     1.65ms       39,546,400   2x pages -> 3.5x time
```

**It was quadratic.** `Source` is two stages — `discover()` opens nothing,
`read()` opens one thing — which is exactly right for a folder and is the shape
of a quadratic for an archive, because there is no way to open one entry without
the container. So the container was opened once per entry:

```text
 pages   read all   per page
    50     0.027s     0.54ms
   400     0.660s     1.65ms   2x pages -> 3.5x time
```

Fixed in [#78](https://github.com/Nananananana/musubi/issues/78), and the fix
took three changes rather than the one that looked sufficient:

| | |
|---|---|
| the outer archive is opened **on its path** | costs a central directory, not its size |
| nested parts are held **open** under a byte budget | not their bytes — see below |
| origins are **indexed once** | a scan of `infolist()` per read is itself quadratic |

The middle one is the instructive one. Caching the inflated *bytes* and building
a `ZipFile` from them per read left the curve exactly where it was, because
constructing a `ZipFile` reads a central directory and that is linear in the
entries. **Both intermediate states passed every functional test in the suite**,
which is why `tests/test_archive_reads_stay_linear.py` counts archive opens
rather than asserting behaviour.

```text
 pages   read all   per page
    50     0.002s     0.03ms
   400     0.008s     0.02ms   2x pages -> 1.8x time
```

**Linear**, and the per-page cost is flat. At 400 pages that is 82× faster, and
the gap grows with the export.

## How sensitive each threshold is

```text
uv run python tools/sensitivity.py

alignment MINIMUM_RUN   identical output from 1 to 80        **a plateau**
alignment WINDOW        bites below about 1 kB               a bound
pdf_text@1 kerning      -179 'thetent' / -180 'the tent'     **a cliff**
```

A number on a plateau was not load-bearing and will survive other people's
files. One on a cliff was fitted, whether or not anybody meant to fit it. The
cliff became a setting (`pdf-word-gap`), and `pdfium@1` removes the question by
reading the font.

`tests/test_thresholds.py` registers all ten behaviour-gating constants as a
bound, a measurement or a threshold, and **fails the build when a new one
appears unclassified**. [ADR-0033](adr/0033-a-threshold-that-nobody-swept-is-a-number-fitted-to-one-corpus.md).

## The metric that can move the wrong way

```text
uv run python tools/sensitivity.py --only window

window     coverage   matched   answer_width
    64      100.0%          0          166.0     nothing aligned
 65536       98.1%          1            1.0     aligned correctly
```

When alignment matches nothing the whole output becomes one `transformed`
segment against the whole source, every offset resolves — to the entire
document — and **traceable coverage reads 100%**. The failure reports the
higher number.

`TraceMap.answer_width` is the companion: *ask about one character, how much
source comes back*. It is not in the manifest yet
([#81](https://github.com/Nananananana/musubi/issues/81)), which is where people
read numbers.

---

## Reading order — every word, wrong order, until it is asked otherwise

```text
uv run python tools/reading_order.py
fixtures whose correct reading is written down

  fixture                 default      +columns        +rows
                        text  pdfium   text  pdfium   text  pdfium
  two columns           0.70    0.70   1.00    1.00   0.70    0.70
  a table               0.67    0.67   0.67    0.67   1.00    1.00
  one line, out of...   0.67    1.00   1.00    1.00   1.00    1.00
```

The ratio is how much of the known answer the reading is, by word. The first
two columns are the **default**, which is the file's own order, and it gets none
of the three right. The failure is the comfortable kind: every word of the
document present, in an order that is not the document's, with every offset
resolving and coverage unchanged.

A producer laying out by baseline writes the left cell of a line and then the
right cell of the same line; reading order is column by column. A table emitted
cell by cell down each column pairs `Item` with `Tent` rather than with `Mass`.

The last four columns are `pdf-reading-order`, and each reads the layout it is
for exactly — **in both readers**. `pdfium@1` was left out when the setting
arrived and ignored it for three days, which is the reader an owner installs
*because* their PDFs need a better one
([ADR-0050](adr/0050-the-better-reader-was-not-offered-the-setting.md)).

**No setting reads both layouts**, and that is the finding rather than a gap: two columns of prose and a table can be the same geometry with opposite
correct readings, so what separates them is what the words mean and that is not
in the file
([ADR-0042](adr/0042-two-columns-and-a-table-are-the-same-page-and-opposite-readings.md)).
musubi offers the lever and does not guess.

### Two of the three answers were unreachable

These are the first fixtures here whose **correct answer is written down**
([ADR-0039](adr/0039-a-fixture-whose-answer-is-known-and-the-two-things-it-found.md)),
and nothing checked that the answer was *in the fixture*. Two were not.

The table wrote its second column one row too high, so `Mass` sat above `Item`
rather than beside it: `TABLE_READ` described a grid the file did not contain.
The third fixture was three ASCII runs side by side whose answer was the
rightmost first, as 縦書き reads — and the script that would have said so had
been removed on purpose, because vertical Japanese needs a composite font that
`pdf_text@1` refuses. Removing it removed the only evidence for the answer.

**A test asserting that musubi gets a layout wrong passes just as happily when
the layout is impossible.** It can never go green, so it never tells anybody
anything: a red that is red about nothing. The guard is now
`test_every_stated_answer_is_reachable_by_some_strategy`, verified against the
reintroduced defect before being trusted.

### And `Tm` was not a line break

Found by those fixtures, and bigger than what they were built for. `Tm` sets the
text matrix absolutely and is how a great many producers place **every line**.
It was missing from the operators that end a line, so separately placed runs
were concatenated with nothing between them:

```text
  three runs at x=300, x=400, x=200   ->   "middlerightleft"
```

One unbroken word, at full coverage, every offset still resolving to the right
page. Fixed; it is what lifts the default from 0.456 to 0.678.

## A composite font was read as glyph numbers

```text
<0024002500260027> Tj   ->   "\x00$\x00%\x00&\x00'"
```

Under a `Type0` / `Identity-H` font the bytes a `Tj` shows are **glyph
indices**, and the map to characters lives in the font's `ToUnicode` CMap.
`pdf_text@1` does not read one, and read the indices as characters: the font's
internal numbering, NUL bytes included, into a corpus document at 100%
traceable coverage with nothing saying so.

This is how every PDF holding Japanese encodes its text, and how most current
producers encode a subsetted Latin font. It was found by the fixtures above and
is now a refusal — `composite_font`, naming `musubi[pdf]`, which reads the CMap.

## The floors, and what happens when one is crossed

```text
uv run python tools/floors.py

  converter        measure                        now   floor    room
  html@1           boilerplate rejected         0.500   0.333  +0.167
  html@1           traceable coverage           0.935   0.850  +0.085
  pdf_text@1       a table across               1.000   1.000  +0.000
  pdf_text@1       one line, out of order       1.000   1.000  +0.000
  pdf_text@1       reading order agreement      0.678   0.550  +0.128
  pdf_text@1       two columns down             1.000   1.000  +0.000
  pdfium@1         reading order agreement      0.789   0.550  +0.239
  pdfium@1         reads a PDF 1.5              1.000   1.000  +0.000
  trafilatura@1    boilerplate rejected         1.000   0.667  +0.333
  trafilatura@1    traceable coverage           0.997   0.900  +0.097
```

Every number above was measured and printed before this, and **nothing failed
when one fell**: a change dropping `trafilatura@1` from 99.7% traceable to 70%
passed every test in the repository. The floors are the gate, and the report
prints either way — a number that went **up** is worth seeing, and a floor with
less headroom than somebody thinks is a floor about to become a target.

**Floors, not targets**, which `docs/proposals/0001-the-design.md` §9 decided
and the register repeats: each one sits below what it measured, carries what it
measured at and when, and says why the headroom is the size it is. Moving one
up is a commit with a reason in it.

**Three measures have no headroom on purpose.** `content kept`, `refuses a
scan` and `reads a PDF 1.4` are bounds: losing a planted paragraph is not a
score getting worse but a corpus answering questions without something the page
said, and a scan becoming an empty document is [ADR-0033]'s shape — 100%
traceable over no characters, reading as success.

**Seen red.** A `trafilatura@1` blunted to keep a third of the page with a map
that resolves everywhere and locates nothing takes traceable coverage to
**0.000** and trips its floor; `content kept` falls to 0.333 and trips its
bound. That is the regression #84 describes, and it used to pass.

## Still owed

- **Cleansing precision** — firings that removed something a corpus labels as
  noise. Needs the labelled evaluation corpus, which v0.4 owes.
- **Screener recall** — labelled credentials found, against a public set.
  [ADR-0008] claims about 70% and **no number here supports that**; it is a
  figure taken from the literature, not a measurement of this screener.
- **Coverage on collected rather than generated documents.** Everything above
  generates its corpus, so it answers order of growth and relative quality. The
  absolute question needs files somebody actually has.
