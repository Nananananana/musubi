"""A corpus as one file the popular readers already know how to open.

## The friction this removes

musubi's output is a folder of Markdown, a manifest and a tree of trace maps.
That is the right thing to *write* ([ADR-0013]: one output family, and the
consumer adapts) and it is four things to *read*. Somebody wiring a corpus into
a retrieval pipeline has to walk the folder, notice `traces/` is not documents,
join the manifest for the converter and the coverage, and invent an id. Most
people write that badly once and never look at it again.

So `musubi export` reads a corpus musubi already wrote and emits **JSON Lines,
one document per line**, which every one of those readers takes:

```python
# LangChain
from langchain_core.documents import Document
docs = [Document(**json.loads(line)) for line in open("corpus.jsonl")]
```

## Why this is not a consumer-specific emitter

[ADR-0013] says musubi ships no emitter per consumer, and the reason it gives is
specific: an emitter for `kiseki`'s NoteRecord would hold **`kiseki`'s domain
semantics** -- its category vocabulary, its trust boundary, its opaque reference
-- inside a library that has no business knowing them.

There is none of that here. `page_content` and `metadata` is an envelope with no
meaning of its own, the metadata inside it is **musubi's own fields and only
those**, and the three shapes differ from each other by *the name of one key*.
Renaming a key is not adopting a contract. Nothing in this module would have to
change if a framework changed what it means by a document; it would have to
change if a framework renamed a field, which is the whole of the coupling.

And it reads a corpus rather than writing one. `sync` is untouched, the folder
is untouched, and a corpus exported twice is the same corpus.

## The id, which is the part worth having

Every loader in every framework gives a document an id derived from its **path**
or a fresh UUID. Both are wrong for the thing people actually do with them: a
vector store upsert, on a corpus that gets re-synced.

musubi has a real one. [ADR-0006] makes identity `(source_id, unit_key)` and
makes `unit_key` survive a re-export -- that is the property [ADR-0013] found
was load-bearing for a consumer two steps away. So the id here is
`source_id:unit_key`, it is stable across re-syncs, and re-embedding a corpus
updates rows rather than duplicating them.

## What travels in the metadata

Enough to *go back*. `trace_map` and `corpus` are in there so that a citation
coming out of a retrieval pipeline can be handed to `musubi trace` and turned
into a place in the owner's own file, which is the entire point of the project
and is otherwise lost the moment the text enters somebody else's index.

`body_offset` is where the prose starts, after the front matter. The text is
emitted **whole**, so that every offset in the trace map still means what it
says; slicing at `body_offset` is the caller's decision and a visible one.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from ..domain.frontmatter import block_of
from ..errors import ContractError
from ..ports.corpus import CorpusReader

__all__ = ["SHAPES", "Exported", "as_line", "documents"]

#: The field names each reader constructs a document from. Values only; the
#: metadata is identical in all three, because it is musubi's and not theirs.
#:
#: ``llamaindex`` also reads the LangChain shape through
#: ``Document.from_langchain_format``, so the third entry is a convenience
#: rather than a necessity -- and saying so is cheaper than pretending the list
#: is a compatibility matrix.
SHAPES: Mapping[str, tuple[str, str]] = {
    "jsonl": ("id", "text"),
    "langchain": ("id", "page_content"),
    "llamaindex": ("id_", "text"),
}


@dataclass(frozen=True, slots=True)
class Exported:
    """One document, ready to be given a name a framework recognises."""

    id: str
    text: str
    metadata: Mapping[str, Any]


def documents(corpus: CorpusReader, root: str = "") -> Iterator[Exported]:
    """Every artefact the manifest records, in the order the manifest has them.

    Read from the manifest rather than by walking the folder. A walk would find
    `traces/` and the manifest itself -- which is exactly the mistake
    `emitters/documents.py` measured a real consumer making, five files ingested
    where two were meant -- and it would have no converter, no coverage and no
    layer to attach.
    """
    body = corpus.manifest_document()
    artefacts = body.get("artefacts")
    if not isinstance(artefacts, list):
        raise ContractError("the manifest lists no artefacts; there is nothing to export")

    for entry in artefacts:
        key = corpus.key_of(str(entry.get("path", "")), str(entry.get("trace_map", "")))
        text = corpus.artefact(key)
        block = block_of(text)
        characters = int(entry.get("characters") or 0)
        traceable = int(entry.get("traceable_characters") or 0)
        # `source` is a nested object in the manifest, not two flat fields. Read
        # wrong it yields `""` twice and every id in the file is `":"` -- which
        # is what happened, and is the shape of failure this whole project is
        # about: the run succeeds, the file looks right, and every row collides
        # in whatever index it is loaded into.
        origin = entry.get("source") if isinstance(entry.get("source"), dict) else {}
        source_id = str(origin.get("source_id", ""))
        unit_key = str(origin.get("unit_key", ""))
        if not source_id or not unit_key:
            raise ContractError(
                f"the manifest entry for {entry.get('path', '?')!r} states no "
                f"(source_id, unit_key); there is no stable id to export it under"
            )
        yield Exported(
            id=f"{source_id}:{unit_key}",
            text=text,
            metadata={
                "source": source_id,
                "unit_key": unit_key,
                "content_hash": entry.get("content_hash", ""),
                "converter": entry.get("converter", ""),
                "layer": entry.get("layer", ""),
                "characters": characters,
                # Published beside the ratio rather than instead of it, so a
                # caller aggregating over a corpus uses the right denominator.
                "traceable_characters": traceable,
                "traceable_coverage": (traceable / characters) if characters else 1.0,
                # The two fields that make the text reversible. Without them a
                # citation that leaves here can never come back.
                "trace_map": entry.get("trace_map", ""),
                "corpus": root,
                "body_offset": block.end + 1 if block else 0,
            },
        )


def as_line(record: Exported, shape: str = "jsonl") -> str:
    """One JSON object and a newline, with the keys `shape` expects."""
    if shape not in SHAPES:
        raise ContractError(f"no export shape called {shape!r}; musubi has {', '.join(SHAPES)}")
    identifier, content = SHAPES[shape]
    body = {identifier: record.id, content: record.text, "metadata": dict(record.metadata)}
    # `ensure_ascii=False` and UTF-8 at the writing end: RFC 8259 §8.1 requires
    # UTF-8 for JSON leaving a closed ecosystem, and a corpus of Japanese notes
    # escaped into `\uXXXX` is four times the size and unreadable in a diff.
    return json.dumps(body, ensure_ascii=False, sort_keys=True) + "\n"
