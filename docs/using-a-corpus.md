# Using a musubi corpus with the tools you already have

**This is a current-state document.** It describes what the code does today. The
reasoning is in [ADR-0030](adr/0030-an-envelope-is-not-a-contract.md).

## Three commands

```bash
pip install "musubi @ git+https://github.com/Nananananana/musubi"   # not on PyPI yet
musubi plan   ~/notes                       # writes nothing, tells you everything
musubi sync   ~/notes --into ./corpus       # builds it, or refuses and builds nothing
musubi export ./corpus > corpus.jsonl       # one JSON object per document
```

`corpus.jsonl` is what every retrieval framework reads. Each line is:

```json
{
  "id": "notes:design/gear.md",
  "text": "---\nlayer: fact\nproducer: musubi.sync/1\n---\n# ギア設計\n\n…",
  "metadata": {
    "source": "notes",
    "unit_key": "design/gear.md",
    "content_hash": "sha256:8957…",
    "converter": "markdown@1",
    "layer": "fact",
    "characters": 86,
    "traceable_characters": 42,
    "traceable_coverage": 0.488,
    "trace_map": "traces/design/gear.md.json",
    "corpus": "/home/you/corpus",
    "body_offset": 44
  }
}
```

## Or one file, in three lines

```python
import musubi

doc = musubi.convert("notes/gear.md")
print(doc.text)
print(doc.where(13, 18))  # characters [13:18], in your file
```

No corpus, no manifest, nothing written — and the map is a value you can hold
rather than a sidecar you have to read back off disk. `doc.coverage`,
`doc.removals` and `doc.converter` are all there too.

## Loading it

### LangChain

```python
import json
from langchain_core.documents import Document

docs = [Document(**json.loads(line)) for line in open("corpus.jsonl", encoding="utf-8")]
```

`musubi export --format langchain` names the fields `id` and `page_content`, so
the constructor takes the object as it stands.

### LlamaIndex

```python
import json
from llama_index.core import Document

docs = [Document(**json.loads(line)) for line in open("corpus.jsonl", encoding="utf-8")]
```

`musubi export --format llamaindex` names them `id_` and `text`.

### Haystack

```python
import json
from haystack import Document

docs = [Document(**json.loads(line)) for line in open("corpus.jsonl", encoding="utf-8")]
```

`musubi export --format haystack` names them `id`, `content` and `meta` -- the
one shape whose metadata key is not `metadata`, which is the whole of the
difference.

### Parquet, for pandas, polars, DuckDB and `datasets`

```bash
musubi export ./corpus --format parquet --out corpus.parquet   # needs musubi[arrow]
```

```python
import pandas as pd

table = pd.read_parquet("corpus.parquet")  # id, text, and one column per metadata field
```

The columns are the JSON Lines keys under the same names, so a reader moving
between the two finds nothing renamed. Written in row groups of a thousand,
so neither the writer nor a reader that streams row groups holds the corpus.
`pyarrow` is Apache-2.0 and is an extra -- offered, never claimed: nothing
imports it until this format is asked for, and without it the command names
the extra to install rather than raising an ImportError.

### Or in Python, without a file

```python
import musubi

for row in musubi.documents("./corpus"):  # a generator, one document at a time
    collection.upsert(ids=[row.id], documents=[row.text], metadatas=[dict(row.metadata)])
```

The same rows the command writes, with the same fields, handed over as values.

### Hugging Face `datasets`

```python
from datasets import load_dataset

data = load_dataset("json", data_files="corpus.jsonl", split="train")
```

The default `jsonl` shape is the one to use here: `id`, `text`, `metadata`.

### A vector store, directly

```python
import json

rows = [json.loads(line) for line in open("corpus.jsonl", encoding="utf-8")]
collection.upsert(
    ids=[row["id"] for row in rows],
    documents=[row["text"][row["metadata"]["body_offset"] :] for row in rows],
    metadatas=[row["metadata"] for row in rows],
)
```

## Two things worth knowing

### The id is stable, and that is the point

Every framework loader derives a document id from its **path** or generates a
UUID. Both change when you re-sync — a Notion export regenerates its UUIDs, a
file gets renamed — so the second run duplicates your corpus instead of updating
it.

musubi's id is `source_id:unit_key`, and `unit_key` is designed to survive a
re-export ([ADR-0006](adr/0006-the-unit-of-sync-is-the-record.md)). Re-embedding
after a re-sync **updates rows**.

### A citation can still come home

This is the part no other loader can do. `trace_map` and `corpus` travel with
every line, so a range in retrieved text goes back to a place in your own file:

```bash
musubi trace ./corpus/documents/design/gear.md:57-62
```

```text
design/gear.md [57:62]  verbatim
  '2.4kg'

  notes:design/gear.md
    characters [13:18]
    bytes      [29:34]  (utf-8)
    /home/you/notes/design/gear.md

  '2.4kg'
```

The last line is the excerpt read back **out of your own file**, so the answer
is checked rather than asserted.

That works after the text has been through an embedding model, a vector store
and a chat interface, because the only thing it needs is the offset and the map.

## For a program driving musubi

Three things a person reading the report already had, stated so that a program
has them too.

### Exit codes

| code | meaning | what a caller may conclude |
|---|---|---|
| `0` | done | the corpus is what the report says; `manifest.json` is current |
| `1` | failed | something was wrong with the input or the corpus -- a manifest that will not parse, a path outside the layout, an offset past the end. Fix it and run again |
| `2` | usage | the arguments were wrong. argparse's own value |
| `3` | refused | **musubi declined on purpose and wrote nothing.** A credential, or a source that emptied under an existing corpus (ADR-0021). Retrying changes nothing; a person has to look, and `plan` predicts this code before `sync` returns it |

The one that matters is the last. An orchestrator that retries a `1` must not
retry a `3`: a feed with a leaked key in it stays refused until somebody reads
the message and either fixes the feed or passes `--allow`. The family precedent
is `0 / 2 / 1`; refusal is `3` here because `2` was argparse's before any of
this was written, and a code that means two things means neither.

### Reading a corpus while it is being written

Every file `sync` writes lands by one atomic replace, and **`manifest.json`
lands last**. So at any instant a reader sees:

- a `manifest.json` that is *entirely* the old one or *entirely* the new one,
  never a mixture and never half a file;
- documents that may already be newer than the manifest describing them, for
  the window between the first replace and the last.

What follows from that:

- **Reading `manifest.json` is always safe.** It describes a corpus that
  existed. During a sync it may describe the one being replaced.
- **Reading `documents/` during a sync may see a mixture** of the old corpus
  and the new. A consumer that indexes the folder while a sync runs can index a
  document the manifest does not yet name, or one whose hash the manifest no
  longer states. `musubi verify` would report that state as a fault, correctly.
- **`runs.jsonl` is appended one line per run**, after the manifest has landed.
  A reader that opens it mid-append can see a truncated last line, and
  `musubi log` refuses a truncated line rather than reading around it.

The recommendation is the simple one: **run `sync` and the consumer's ingest
in series**, and read `manifest.json` and `runs.jsonl` after `sync` has exited
with `0`. musubi does not take a lock, because a lock file in the owner's
output folder is a file they did not ask for and a stale one after a crash is
a corpus nobody can sync.

### What `musubi_trace` answers, and how to read it

`musubi mcp <root>` serves `musubi_trace(path, start, end)`. Two cases, told
apart by where `path` sits:

- **A document inside a corpus musubi wrote** -- `<corpus>/documents/<unit_key>`
  -- is answered from its trace map, exactly as `musubi trace` answers. The
  offsets are into the document *as it sits in the corpus*, front matter
  included, which is what an anchor made by a consumer that ingested the
  corpus points at.
- **Any other file** is converted afresh and the offsets are into the text
  `musubi_convert` returned.

The first is the one an orchestrator uses. Its answer is the same document
`musubi trace --json` prints, and it leads with one word:

| `status` | meaning | what to draw |
|---|---|---|
| `resolved` | a place in the source, and the file on disk still holds what the map was built from. `source.bytes` and `source.excerpt` are filled | the original, opened at those bytes |
| `synthetic` | musubi wrote every character in the range -- front matter, a heading it inserted. There is no source to open | *musubi wrote this*, and nothing else |
| `source_changed` | a place in the source, but the file has been edited since the sync. The offsets are about a document that no longer exists | the range, with a warning |
| `source_missing` | a place in the source, and no file to open: moved, deleted, or the manifest's root is not mounted | the range, and *not found* |
| `source_outside_root` | a place in the source, and the server may not read it from where it is rooted (below) | the range, and *not found* |

`synthetic` and the three `source_*` answers are the distinction `docs/contracts.md`
rule 7 draws: *musubi wrote this* is not *this did not resolve*, and a screen
that shows one wording for both is wrong about one of them.

**The root, and what it confines.** The manifest names where each source was
read from as an absolute path, and following it is the point of a trace. But
the server is confined to the folder it was started in (ADR-0007), and a
manifest somebody else wrote must not be able to walk it out: a source outside
the root is *located* and not *opened*, and the answer says `source_outside_root`
with no path, no bytes and no excerpt. So **root the server at a folder that
contains both the corpus and the fetched originals** when the originals are
what the screen should open.

## `body_offset`, and why the front matter is still there

The text is emitted **whole**. Stripping the front matter would shift every
offset by a number nothing records, and the trace map would then point at the
wrong characters — silently, which is the failure this project exists to
prevent.

So the front matter stays and `body_offset` says where the prose starts. Slice
there when you embed; keep the whole text when you trace.

## What a musubi corpus does not promise

- **The export is a copy.** Once you have `corpus.jsonl`, it has no relationship
  to the corpus. `content_hash` is how you check; nothing here stops you
  embedding a year-old export and citing it as current.
- **`traceable_coverage` is per document, and it means an offset resolves** — not
  that the conversion read the document in the right order.
- **What an offset resolves *to* depends on the converter.** A character map
  answers with a character; a PDF's map answers with a page
  ([ADR-0025](adr/0025-a-map-with-no-verbatim-run-composes-whatever-it-measures.md)).
  Each trace map states its own `source_unit`, and one corpus of mixed formats
  has a single coverage number over more than one meaning of *traceable*.
