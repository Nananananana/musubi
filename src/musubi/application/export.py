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
those**, and the four shapes differ from each other by *the names of keys*.
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

## One document in memory at a time

`documents()` is a generator and `write()` consumes it a line at a time. The
first version of the command built every line into a list and joined it,
which held the whole export twice: measured on 2,000 generated notes, 19.7 MB
peak for a 6.5 MB file. A corpus is read by people whose corpus is larger than
their patience, and an export that needs three times its own size in memory
is an export that fails on exactly the corpus it was for.

## Parquet, for the readers that want a table

`pandas`, `polars`, DuckDB and Hugging Face `datasets` all read Parquet
directly, and a hundred thousand documents as JSON Lines is a file those
readers parse slowly and hold whole. `--format parquet` writes the same rows
as a columnar table, in row groups of a thousand so that the writer never
holds the corpus either. It needs `pyarrow`, which is Apache-2.0 and is
offered as `musubi[arrow]` -- offered, never claimed ([ADR-0028]): nothing
here imports it until a caller asks for the format, and a caller without it is
told which extra to install rather than shown an ImportError.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import IO, Any

from ..domain.frontmatter import block_of
from ..errors import ContractError
from ..ports.corpus import CorpusReader

__all__ = ["ARROW_EXTRA", "SHAPES", "Exported", "as_line", "documents", "write", "write_parquet"]

#: The field names each reader constructs a document from: the id, the text,
#: and the metadata mapping. Values only; what is *in* the metadata is
#: identical in every shape, because it is musubi's and not theirs.
#:
#: ``llamaindex`` also reads the LangChain shape through
#: ``Document.from_langchain_format``, so that entry is a convenience rather
#: than a necessity -- and saying so is cheaper than pretending the list is a
#: compatibility matrix. ``haystack`` is the shape ``haystack.Document`` takes
#: as keyword arguments.
SHAPES: Mapping[str, tuple[str, str, str]] = {
    "jsonl": ("id", "text", "metadata"),
    "langchain": ("id", "page_content", "metadata"),
    "llamaindex": ("id_", "text", "metadata"),
    "haystack": ("id", "content", "meta"),
}

#: The extra that brings `pyarrow`. Named here so that the message a caller
#: sees and the entry in `pyproject.toml` cannot drift apart unnoticed.
ARROW_EXTRA = "musubi[arrow]"

#: Documents per Parquet row group. A thousand rows of prose is a few
#: megabytes, which is the amount a writer holds at once.
ROW_GROUP = 1000

#: The metadata fields, in the order a table's columns take them. Listed once,
#: because a column set that is derived from whichever record comes first is a
#: schema that changes with the corpus.
COLUMNS: tuple[str, ...] = (
    "source",
    "unit_key",
    "content_hash",
    "converter",
    "layer",
    "characters",
    "traceable_characters",
    "traceable_coverage",
    "trace_map",
    "corpus",
    "body_offset",
)


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
    identifier, content, metadata = _shape(shape)
    body = {identifier: record.id, content: record.text, metadata: dict(record.metadata)}
    # `ensure_ascii=False` and UTF-8 at the writing end: RFC 8259 §8.1 requires
    # UTF-8 for JSON leaving a closed ecosystem, and a corpus of Japanese notes
    # escaped into `\\uXXXX` is four times the size and unreadable in a diff.
    return json.dumps(body, ensure_ascii=False, sort_keys=True) + "\n"


def write(records: Iterable[Exported], sink: IO[bytes], shape: str = "jsonl") -> int:
    """Every record as a line, into a byte stream, one at a time. Returns the count.

    Bytes rather than text, for [ADR-0020]'s reason: a document is UTF-8
    whatever the console is, and JSON that went through a `cp932` terminal was
    a file that was not valid UTF-8 with exit 0 and no error.
    """
    _shape(shape)  # refused before the first line, not after the last
    count = 0
    for record in records:
        sink.write(as_line(record, shape).encode("utf-8"))
        count += 1
    return count


def write_parquet(records: Iterable[Exported], path: Path) -> int:
    """Every record as a row of one table, in row groups. Returns the count.

    The metadata is flattened into columns named exactly as the JSON Lines keys
    are, so a reader moving between the two formats finds the same names. The
    id and the text are the first two columns.
    """
    try:
        # `import_module`, like every optional dependency here: nothing is
        # imported at import time, and a module with no stubs is a module mypy
        # is not asked about.
        pa: Any = import_module("pyarrow")
        pq: Any = import_module("pyarrow.parquet")
    except ImportError as error:
        raise ContractError(
            f"the parquet format needs pyarrow, which is not installed. It is offered "
            f"as an extra: pip install '{ARROW_EXTRA}'. Nothing else changes when it is."
        ) from error

    schema = pa.schema(
        [
            ("id", pa.string()),
            ("text", pa.string()),
            ("source", pa.string()),
            ("unit_key", pa.string()),
            ("content_hash", pa.string()),
            ("converter", pa.string()),
            ("layer", pa.string()),
            ("characters", pa.int64()),
            ("traceable_characters", pa.int64()),
            ("traceable_coverage", pa.float64()),
            ("trace_map", pa.string()),
            ("corpus", pa.string()),
            ("body_offset", pa.int64()),
        ]
    )
    count = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with pq.ParquetWriter(str(path), schema) as writer:
        batch: list[dict[str, Any]] = []
        for record in records:
            batch.append({"id": record.id, "text": record.text, **dict(record.metadata)})
            count += 1
            if len(batch) >= ROW_GROUP:
                writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                batch = []
        if batch or count == 0:
            # A corpus of nothing is still a table with these columns: a reader
            # that opens it learns the shape, which an absent file cannot say.
            writer.write_table(pa.Table.from_pylist(batch, schema=schema))
    return count


def _shape(shape: str) -> tuple[str, str, str]:
    if shape not in SHAPES:
        raise ContractError(
            f"no export shape called {shape!r}; musubi has {', '.join(SHAPES)}, and "
            f"parquet as a format of its own"
        )
    return SHAPES[shape]
