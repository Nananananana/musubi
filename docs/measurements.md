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
| Trace map size | **10.7× the corpus** | **falsified** |
| Re-read ratio | **0.91** | **falsified** |
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
storage than the corpus*. It does, by an order of magnitude, and the proposal's
predicted remedy — *the fix is converter-side* — is **wrong about roughly half
of it**:

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

## Re-read ratio — 0.91

```text
uv run python tools/scaling.py --only resync
400 unchanged Markdown notes

  cold sync              2.08s  400 artefacts
  no-change re-sync      1.89s  400 artefacts
  re-read ratio           0.91
```

[ADR-0006]'s claim is that *a re-export that changed nothing produces an empty
diff*. A no-change re-sync costs **91% of a cold one** and rewrites every
artefact. `docs/README.md` has always said `Change` exists and nothing calls it;
this is what that costs rather than what it sounds like it costs.

The identity machinery is real and correct — `content_hash` is computed, keys
are stable, the previous manifest is read as a ledger for withdrawal. What is
missing is the one comparison that would use it.

Filed as [#77](https://github.com/Nananananana/musubi/issues/77).

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
