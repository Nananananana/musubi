# Configuring musubi

**This is a current-state document.** It describes what the code does today. The
reasoning is in [ADR-0027](adr/0027-the-nearest-file-wins-whole-and-every-value-says-where-it-came-from.md).

## The short version

```bash
musubi config          # what this folder would run with, and why
```

Everything below is optional. musubi with no configuration at all reads a folder
as an Obsidian vault, writes to `./synced`, screens for credential signatures
and cleanses with the core rule pack.

## Where settings come from

In this order, later winning:

| | Example |
|---|---|
| built-in defaults | `into = "synced"` |
| the nearest configuration file | `musubi.toml` |
| the environment | `MUSUBI_INTO=corpus` |
| a flag | `--into corpus` |

A file is looked for in the working directory and then upward, and **the first
one found is used whole**:

```text
musubi.toml                    a folder of notes is not a Python project
.musubi.toml                   the same file, hidden
pyproject.toml [tool.musubi]   when it is
```

Settings are **not** merged across files. `musubi config` prints the file it
read and, underneath, any it found further up and did not — which is the
question somebody standing in a subdirectory actually has.

A `pyproject.toml` with no `[tool.musubi]` table is not a musubi configuration
file and does not stop the search. Otherwise the first Python project above a
notes folder would win it while setting nothing.

## An example

```toml
# musubi.toml
source    = "notion"
into      = "corpus"
screener  = "signatures+entropy"
allow     = ["stripe.secret-key:archive/2019-invoice.md"]

[converters]
"text/html" = "html@1"
```

## Every setting

| Key | Values | Default | What it decides |
|---|---|---|---|
| `source` | `filesystem`, `notion`, `obsidian` | `obsidian` | how the root folder is read |
| `into` | a path | `synced` | where the corpus goes |
| `screener` | `signatures`, `signatures+entropy` | `signatures` | which credential tiers run ([ADR-0017](adr/0017-entropy-is-a-tier-not-a-default.md)) |
| `rules` | `core`, `none` | `core` | which cleansing pack runs ([ADR-0016](adr/0016-a-rule-is-a-matcher-not-a-regular-expression.md)) |
| `converters` | a table of media type → converter | *(empty)* | overrides the built-in claim for a format |
| `allow` | a list of `rule:unit_key` | *(empty)* | credential hits already looked at and decided against |
| `pdf-word-gap` | a number | `-180.0` | how negative a PDF kerning value must be to read as a space ([ADR-0033](adr/0033-a-threshold-that-nobody-swept-is-a-number-fitted-to-one-corpus.md)) |
| `encoding` | `strict`, `detect` | `strict` | whether a file that is not UTF-8 is refused or read by detection ([ADR-0031](adr/0031-a-guess-with-its-uncertainty-attached-is-not-the-guess-that-was-forbidden.md)) |

Environment variables are the key uppercased with `MUSUBI_` in front:
`MUSUBI_SOURCE`, `MUSUBI_SCREENER`. A list is comma-separated. **A table is
not settable from the environment** — `converters` refuses out loud rather than
being ignored, because a table flattened into one string is a syntax nobody can
read back.

## Choosing an algorithm

`screener`, `rules` and `converters` each name an implementation. The names
resolve against a table that ships in the wheel, and `musubi config` prints the
alternatives beside whichever is in effect:

```text
  rules        core                         default
                                            or: none
```

**A setting names an algorithm, never an import path.** musubi is pointed at the
folder that holds everything its owner has written ([ADR-0001](adr/0001-the-domain-depends-on-nothing.md)),
and a settings file that can name an arbitrary module is a settings file that
can run anything. A converter written elsewhere is registered by a program that
imported musubi deliberately:

```python
from musubi.infrastructure.converters import register_converter

register_converter(MyPdfConverter(), replace=True)
```

After that it has a name, `musubi config` lists it, and `[converters]` can
select it — because the table is read when the question is asked rather than at
import.

The wiring — which class implements `notion`, which pack `core` names — lives in
`musubi/config.py`, the composition root the architecture map reserves for it.
An interface prints a configuration or runs one; neither needs to know.

## When words run together in a PDF

`pdf_text@1` reads a `TJ` array's kerning values and inserts a space when one is
negative enough. **That number is a cliff, not a convention.** Measured with
`uv run python tools/sensitivity.py --only kerning`:

```text
   kerning  reads as          
      -179  'thetent'          one word
      -180  'the tent'         two words
```

Real fonts put a word space anywhere from under 200 thousandths of an em to
about 330, so documents land on both sides of any single value. If a PDF comes
out with words joined, lower it:

```toml
# musubi.toml
pdf-word-gap = -120
```

Or stop choosing: **`pdfium@1` reads the font metrics and needs no threshold at
all.**

```bash
pip install "musubi[pdf] @ git+https://github.com/Nananananana/musubi"
```

```toml
[converters]
"application/pdf" = "pdfium@1"
```

## Reading notes that are not UTF-8

musubi reads UTF-8 and UTF-16-with-a-mark. Everything else is refused, because a
wrongly guessed encoding writes plausible nonsense into a corpus and looks
exactly like a successful read.

That is right and it is unusable on its own: **a vault holding anything written
on a Japanese Windows machine before about 2015 is Shift-JIS**, and musubi
reports every one of those files as `undecodable`.

```bash
pip install "musubi[encoding] @ git+https://github.com/Nananananana/musubi"
```

```toml
# musubi.toml
encoding = "detect"
```

With the extra installed and `strict` still set, the refusal tells you what the
file is:

```text
skipped  design/古いメモ.md  undecodable
  not decodable as UTF-8 or as UTF-16 with a byte-order mark (byte 2 is 0x90).
  It looks like cp932 (98% coherent); set `encoding = "detect"` in musubi.toml
  to read it, and the detected encoding will be recorded with every offset
```

With `detect`, it is read, and **the detected encoding is written into the trace
map** — so an offset still converts to a byte offset in your original file, and
the corpus says what musubi had to assume.

**Measured** with `uv run python tools/encoding_detection.py`, six languages
against seven encodings, comparing the recovered *text* rather than the label:

| sample | recovered exactly |
|---|---|
| a paragraph | **17 of 19** |
| one line | **16 of 19** |

Both constant failures are French in Latin-1 or cp1252 read as cp1250. Every
multi-byte encoding was right at paragraph length. **Detection gets worse as the
file gets shorter**, and the extra failure there is Russian in KOI8-R read as
Japanese — and every one of these misses reports 100% coherence, so the
confidence number will not warn you.

That is why `strict` is the default rather than `detect`.

## Optional converters

Some formats have a better extractor than musubi's own, and taking it costs a
dependency. Those are **extras**, and installing one adds a name without
changing anything:

```bash
pip install "musubi[html] @ git+https://github.com/Nananananana/musubi"      # better main-content extraction
pip install "musubi[pdf] @ git+https://github.com/Nananananana/musubi"       # reads the PDFs a scan of `N 0 obj` cannot
```

```toml
# musubi.toml -- until this line exists, nothing has changed
[converters]
"text/html" = "trafilatura@1"
```

`musubi config` lists what is installed and what is not:

```text
Optional converters (ADR-0028). Installed ones are offered, never claimed:
  pdfium@1         available    application/pdf  [BSD-3-Clause]
  trafilatura@1    available    text/html, application/xhtml+xml  [Apache-2.0]
```

An external extractor returns text and no offsets, which is the shape
[ADR-0004](adr/0004-a-conversion-carries-a-map-back-to-its-source.md) cannot
use. musubi **recovers** the map by aligning the extractor's output against the
source, so traceable coverage stays a measurement in the manifest rather than a
claim. On one generated page: 99.7% through `trafilatura@1`, against 93.5% for
the built-in `html@1` — and 6/6 planted boilerplate strings rejected against
3/6. Re-derive both with `uv run python tools/html_coverage.py`.

**PDF is different, and the difference is worth knowing.** There is no decoded
text in a PDF to align against, so `pdfium@1` produces exactly the map
`pdf_text@1` produces — one segment per page, and a citation that says *page
three*. What the dependency buys there is **reach**: `pdf_text@1` finds objects
by scanning for `N 0 obj`, and reports `no_pages` on a PDF 1.5, where the page
lives inside a compressed object stream. That is what almost every current
producer writes. Re-derive it with `uv run python tools/pdf_coverage.py`.

Only permissively licensed extractors are offered. PyMuPDF is the fastest PDF
reader in Python and is AGPL-3.0; an extra is still a dependency you ship.

## What cannot be configured

- **The screener cannot be turned off.** A run stops on a credential
  ([ADR-0008](adr/0008-a-credential-stops-the-run.md)) and a corpus that was
  never screened looks exactly like one that was. Every tier includes the
  signature tier.
- **The hash algorithm.** `sha256:` is written into every hash value precisely
  so that changing it later is a *data* change an old reader can detect
  ([ADR-0015](adr/0015-a-hash-names-its-algorithm.md)). Making it a setting
  would put two incompatible corpora behind one contract version, which
  [ADR-0024](adr/0024-a-field-added-is-a-new-contract.md) is about. It stays a
  decision, not a switch.
- **Whether a conversion carries a map.** That is the product.

## `--allow` replaces, it does not add

A flag beats a file completely, including this one. Passing `--allow` on the
command line means the file's list is not used. That is the fail-closed
direction: losing an allowance stops a run that would otherwise have proceeded,
and the opposite rule would let a forgotten line in a file two directories up
keep a credential moving.
