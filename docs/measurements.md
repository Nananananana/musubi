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
| Trace map size | 10.7× → **4.9× the corpus** | half fixed ([#76](https://github.com/Nananananana/musubi/issues/76)) |
| Composition | **quadratic** → linear, 33× faster | fixed |
| Re-read ratio | **0.32**, from 1.01 | falsified, then fixed (ADR-0036) |
| Archive reads per unit | **O(1)** archives opened | fixed in [#78](https://github.com/Nananananana/musubi/issues/78) |
| Screener precision, synthetic | **0.00%** false stops after ADR-0026 | holds |
| Cleansing precision | not measured | owed |
| Screener recall | not measured | owed |

---

## Trace map size — 10.7× the documents

```text
uv run python tools/scaling.py --only map
20 generated HTML pages and 20 Markdown notes, one real sync

  documents/    105,720
  traces/     1,132,820    10.7x the documents
  manifest       18,606
  everything  1,257,146    11.9x

  one .html document   2,592  map  36,241 (14.0x)  216 segments,  16,093 minified
  one .md   document   2,694  map  20,400 ( 7.6x)  124 segments,   8,720 minified
```

§10 says: *if a map routinely exceeds its document, the guarantee costs more
storage than the corpus*. It did, by an order of magnitude, and the proposal's
predicted remedy — *the fix is converter-side* — was **wrong about roughly half
of it**. Minifying the sidecar took it from 10.7× to **4.9×**; the numbers below
are the measurement that showed where to look:

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

The first of those is also half of the map-size problem above: minified, one
HTML map goes from 36,241 bytes to 16,588, and `traces/` from 10.7× the
documents to **4.9×**. The reason for indenting was that a reviewer opens these;
a reviewer can pipe one through `jq`, and nobody gets the disk back.

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
     100    273,200      405,205        1.5x
     200    546,400      733,355        1.3x
     400  1,092,800    1,384,353        1.3x
```

**Linear, and the ratio does not fall.** A run holds roughly the whole corpus at
once, so the folder has to fit in memory. That is fine for a vault and not for
the "everything you have ever written" case [ADR-0007] describes. It is a
ceiling rather than a defect, and it is filed as
[#80](https://github.com/Nananananana/musubi/issues/80) so that it is a known
one.

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

## Still owed

- **Cleansing precision** — firings that removed something a corpus labels as
  noise. Needs the labelled evaluation corpus, which v0.4 owes.
- **Screener recall** — labelled credentials found, against a public set.
  [ADR-0008] claims about 70% and **no number here supports that**; it is a
  figure taken from the literature, not a measurement of this screener.
- **Coverage on collected rather than generated documents.** Everything above
  generates its corpus, so it answers order of growth and relative quality. The
  absolute question needs files somebody actually has.
