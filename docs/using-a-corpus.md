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
