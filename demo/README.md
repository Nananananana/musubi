# A demo you can run in five minutes

Every command below was run to write this page, and every block of output is
what it printed.

## Setup

```bash
git clone https://github.com/Nananananana/musubi
cd musubi
uv sync --all-extras
uv run python demo/make_sample.py
```

That builds `demo/sample-vault`: six files, each one a thing a real folder
contains and a thing that goes wrong.

| | |
|---|---|
| `design/ギア設計.md` | UTF-8 Japanese, with a tracked URL in it |
| `design/古いメモ.md` | **Shift-JIS** — a note from before everything was UTF-8 |
| `posts/index.html` | a blog index: forty tracked links, nav, cookie banner |
| `reports/report.pdf` | **PDF 1.5** — the page is inside a compressed object stream |
| `setup/deploy.md` | holds something shaped exactly like an AWS key |
| `photo.png` | a format musubi does not read |

---

## 1. Ask what would happen. Nothing is written.

```bash
cd demo
uv run --project .. musubi plan sample-vault --as filesystem
```

```text
musubi plan — 2 emitted, 4 skipped, 2 removals, 86.7% traceable
  nothing was written. run id sha256:adf0ebf59e3b49fdd8f2418bcc37bb42386c1072b04ab…

Would refuse, and stop the whole run
  an AWS access key id in setup/deploy.md at [79:99] (aws.access-key)

Would not be read
  design/古いメモ.md  undecodable (… It looks like cp932 (100% coherent); set
    `encoding = "detect"` in musubi.toml to read it, and the detected encoding
    will be recorded with every offset)
  photo.png  unknown_format (.png)
  reports/report.pdf  no_pages (no page objects were found in the file)
  setup/deploy.md  credential (aws.access-key)

Would be removed
  tracking.utm-family  2x

Installed and not used
  pdfium@1 reads application/pdf, and may read what was refused above.
    musubi.toml:  [converters]  "application/pdf" = "pdfium@1"
  trafilatura@1 reads text/html, application/xhtml+xml, and may read what was refused above.
    musubi.toml:  [converters]  "text/html" = "trafilatura@1"
```

**Two of every three files were refused, and each refusal says what to do about
it.** The report leads with what would *not* happen, which is the reverse of
what an ingestion tool usually prints.

## 2. Tell it what this folder is

```bash
cat > musubi.toml <<'TOML'
source   = "filesystem"
into     = "corpus"
encoding = "detect"

[converters]
"application/pdf" = "pdfium@1"
"text/html"       = "trafilatura@1"
TOML

uv run --project .. musubi config
```

`musubi config` prints every setting **with the thing that decided it** — the
file, the environment variable or the flag — and the alternatives beside each.

```bash
uv run --project .. musubi plan sample-vault
```

```text
musubi plan — 4 emitted, 2 skipped, 2 removals, 92.7% traceable
```

**Two emitted became four.** The Shift-JIS note and the PDF 1.5 both read.

## 3. It still refuses to build

```bash
uv run --project .. musubi sync sample-vault
```

```text
musubi: an AWS access key id in setup/deploy.md at [79:99] (aws.access-key).
Nothing was written. Look, then pass --allow aws.access-key:setup/deploy.md if
it is not what it looks like.
```

Nothing at all was written — not the four files that converted cleanly either.
A credential stops the whole run, and musubi does not redact it: refusing needs
only that a secret exists, and redacting needs to be right about where it ends.

Look at the file. It is an example key from AWS's own documentation, so:

```bash
uv run --project .. musubi sync sample-vault --allow aws.access-key:setup/deploy.md
```

```text
musubi sync — 5 emitted, 1 skipped, 2 removals, 90.2% traceable
  …/demo/corpus. run id sha256:83a733cd9fe225c71d2489464c4b7a25d3dbb97133f2081…
```

## 4. The part nothing else does

Find where a phrase in the corpus came from. `3.8kg` appears in the note that
was **Shift-JIS**:

```bash
uv run --project .. python -c "
from pathlib import Path
print(Path('corpus/documents/design/古いメモ.md').read_text(encoding='utf-8').index('3.8kg'))"
# 69

uv run --project .. musubi trace "corpus/documents/design/古いメモ.md:69-74"
```

```text
design/古いメモ.md [69:74]  verbatim
  '3.8kg'

  filesystem:design/古いメモ.md
    characters [25:30]
    bytes      [41:46]  (cp932)
    …/demo/sample-vault/design/古いメモ.md

  '3.8kg'
```

**Byte 41 to 46 of the original Shift-JIS file.** The last line is the excerpt
read back out of that file, so the answer is checked rather than asserted — and
the byte offset is right because the encoding musubi had to detect was recorded
in the map beside every offset.

Try it on the PDF too:

```bash
uv run --project .. musubi trace "corpus/documents/reports/report.pdf:0-34"
```

That one answers **page 1**, not a character offset, because a PDF has no
decoded text to point at and *page one* is a claim you can check by opening it.

## 5. Hand it to something else

```bash
uv run --project .. musubi export corpus > corpus.jsonl
head -c 400 corpus.jsonl
```

One JSON object per document, which LangChain, LlamaIndex, Hugging Face
`datasets` and every vector store read as they are. Two things travel with it
that no other loader gives you:

- an **id that survives a re-sync** (`filesystem:design/古いメモ.md`), so an
  upsert updates rather than duplicates;
- `trace_map` and `corpus`, so a citation coming back out of an index can be
  handed to `musubi trace` and turned into a byte range in your own file.

## 6. Or one file, in three lines

```bash
uv run --project .. python -c "
import musubi
doc = musubi.convert('sample-vault/reports/report.pdf')
print(doc.text[:70])
print(doc.converter, f'{doc.coverage:.1%}')
print(doc.where(0, 34))
"
```

```text
Trip report: the Kita-Alps, October
The tent weighed 2.4kg and it mattere
pdfium@1 100.0%
page 1 (opaque locator)
```

No corpus, no manifest, nothing written — and the map is a value you can hold.

## 7. Check a corpus somebody else handed you

```bash
uv run --project .. musubi verify corpus
```

Checks every document against the hash the manifest recorded, and the invariants
the published schemas cannot express. It also prints what it **cannot** tell
you: it compares a corpus against its own manifest, so a corruption that
happened before the hash was taken is recorded in the hash and reads as *all
hold*.

## Cleaning up

```bash
rm -rf sample-vault corpus corpus.jsonl musubi.toml
```
