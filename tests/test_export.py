"""A corpus as one file, and the trip back out of somebody else's index.

The export exists to remove friction, so most of these are about the failures
that are *comfortable*: a file that loads fine and is quietly wrong. An id that
collides, a coverage number nobody can check, a citation that cannot be taken
back to the owner's file.

The last test is the one the whole feature is for. It goes corpus -> exported
line -> an offset chosen inside the exported text -> `musubi trace` -> a place
in the source file, because a pipeline that cannot do that has lost the only
thing musubi was built to keep.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from musubi import __version__
from musubi.application.export import ARROW_EXTRA, SHAPES, as_line, documents, write_parquet
from musubi.application.pipeline import Settings
from musubi.application.sync import sync
from musubi.application.trace import resolve
from musubi.domain.span import Span
from musubi.errors import ContractError
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.corpus import Corpus
from musubi.infrastructure.emitters import MANIFEST, DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import ObsidianSource
from musubi.interfaces.cli import main

NOTE = "# ギア設計\n\nテントは 2.4kg。ブーツのほうが効く。\n"
OTHER = "# Stove\n\nA remote canister freezes; a liquid-fuel stove does not.\n"


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """A real sync of a real vault. Never a folder a test assembled."""
    vault = tmp_path / "vault"
    (vault / "design").mkdir(parents=True)
    (vault / "design" / "gear.md").write_text(NOTE, encoding="utf-8")
    (vault / "stove.md").write_text(OTHER, encoding="utf-8")

    into = tmp_path / "corpus"
    # `sync`, not `run(write=True)`: staging is not promotion, and a corpus that
    # was staged and never moved into place has no manifest to export.
    sync(ObsidianSource(vault), _settings(), DocumentEmitter(into))
    return into


def _settings() -> Settings:
    return Settings(
        ruleset=CORE,
        screener=default_screener(),
        converter_for=converter_for,
        musubi_version=__version__,
    )


def exported(destination: Path) -> list[dict[str, object]]:
    reader = Corpus(destination)
    return [
        json.loads(as_line(record, "jsonl"))
        for record in documents(reader, str(destination.resolve()))
    ]


# -- the id, which is the part worth having ---------------------------------


def test_the_id_is_the_records_identity_and_not_a_path_or_a_uuid(corpus: Path) -> None:
    """[ADR-0006] makes identity `(source_id, unit_key)` and makes the key
    survive a re-export. Every framework loader instead derives an id from a
    path or invents a UUID, and both duplicate rows on the next sync."""
    rows = exported(corpus)
    assert {str(row["id"]) for row in rows} == {"vault:design/gear.md", "vault:stove.md"}


def test_two_syncs_of_the_same_vault_export_the_same_ids(corpus: Path, tmp_path: Path) -> None:
    """The property a vector store upsert actually needs."""
    before = [row["id"] for row in exported(corpus)]

    sync(ObsidianSource(tmp_path / "vault"), _settings(), DocumentEmitter(corpus))
    assert [row["id"] for row in exported(corpus)] == before


def test_an_entry_with_no_identity_is_refused_rather_than_exported(corpus: Path) -> None:
    """`source` is a nested object in the manifest. Read as two flat fields it
    yields `""` twice, every id becomes `":"`, and every row collides in
    whatever index the file is loaded into -- with the run succeeding and the
    file looking right. That happened; this is the guard."""
    manifest = corpus / MANIFEST
    body = json.loads(manifest.read_text(encoding="utf-8"))
    body["artefacts"][0]["source"] = {}
    manifest.write_text(json.dumps(body), encoding="utf-8")

    with pytest.raises(ContractError, match="no stable id"):
        exported(corpus)


# -- what travels with the text ---------------------------------------------


def test_the_metadata_is_musubis_own_fields_and_nothing_borrowed(corpus: Path) -> None:
    """[ADR-0013] refuses a consumer-specific emitter because one would hold a
    consumer's *semantics*. Keeping the metadata to musubi's own fields is what
    makes this an envelope rather than a contract."""
    (row, _) = sorted(exported(corpus), key=lambda r: str(r["id"]))
    metadata = row["metadata"]
    assert isinstance(metadata, dict)
    assert set(metadata) == {
        "body_offset",
        "characters",
        "content_hash",
        "converter",
        "corpus",
        "layer",
        "source",
        "trace_map",
        "traceable_characters",
        "traceable_coverage",
        "unit_key",
    }


def test_the_coverage_is_published_with_its_denominator(corpus: Path) -> None:
    """A ratio on its own cannot be aggregated over a corpus. Both counts travel
    so that a caller summing them uses the right denominator."""
    for row in exported(corpus):
        metadata = row["metadata"]
        assert isinstance(metadata, dict)
        assert metadata["traceable_coverage"] == pytest.approx(
            metadata["traceable_characters"] / metadata["characters"]
        )


def test_the_text_is_whole_and_the_body_offset_says_where_the_prose_starts(
    corpus: Path,
) -> None:
    """Emitting the body alone would silently invalidate every offset in the
    trace map. Emitting the whole document and saying where the prose begins
    makes the slice the caller's decision and a visible one."""
    for row in exported(corpus):
        text = str(row["text"])
        metadata = row["metadata"]
        assert isinstance(metadata, dict)
        assert text.startswith("---\n"), "front matter was stripped"
        body = text[int(metadata["body_offset"]) :]
        assert body.startswith("# "), body[:40]
        assert "---" not in body.split("\n")[0]


# -- the shapes -------------------------------------------------------------


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_shape_carries_the_same_three_things(corpus: Path, shape: str) -> None:
    """The shapes differ by the name of one key. If one ever differed by more
    than that, it would have stopped being a renaming and started being a
    contract, which is what ADR-0013 forbids."""
    reader = Corpus(corpus)
    record = next(iter(documents(reader, str(corpus))))
    body = json.loads(as_line(record, shape))

    identifier, content, metadata = SHAPES[shape]
    assert set(body) == {identifier, content, metadata}
    assert body[identifier] == record.id
    assert body[content] == record.text
    assert body[metadata] == dict(record.metadata)


def test_an_unknown_shape_is_refused_and_the_known_ones_are_named(corpus: Path) -> None:
    reader = Corpus(corpus)
    record = next(iter(documents(reader, str(corpus))))
    with pytest.raises(ContractError, match="jsonl"):
        as_line(record, "csv")


def test_a_line_is_valid_utf8_json_with_the_characters_unescaped(corpus: Path) -> None:
    """RFC 8259 §8.1 requires UTF-8 for JSON leaving a closed ecosystem, and a
    corpus of Japanese notes escaped into `\\uXXXX` is four times the size and
    unreadable in a diff."""
    reader = Corpus(corpus)
    lines = [as_line(record) for record in documents(reader, str(corpus))]
    assert any("ギア設計" in line for line in lines), "the characters were escaped"
    for line in lines:
        json.loads(line.encode("utf-8").decode("utf-8"))


# -- the trip back ----------------------------------------------------------


def test_a_citation_taken_from_an_exported_line_traces_back_to_the_source(
    corpus: Path,
) -> None:
    """The whole reason for the feature.

    Text that enters somebody else's index normally loses its provenance at the
    door. Here the line carries `corpus` and `trace_map`, so a range chosen in
    the retrieved text goes back through the map to a place in the file the
    owner has.
    """
    row = next(r for r in exported(corpus) if str(r["id"]) == "vault:design/gear.md")
    text = str(row["text"])
    metadata = row["metadata"]
    assert isinstance(metadata, dict)

    at = text.index("2.4kg")
    found = resolve(
        Corpus(Path(str(metadata["corpus"]))), str(metadata["unit_key"]), Span(at, at + 5)
    )

    assert found.excerpt == "2.4kg"
    assert found.source_excerpt == "2.4kg", "the source no longer holds what the map claims"
    assert found.source_path is not None
    assert found.source_path.name == "gear.md"
    assert not found.changed


def test_the_command_writes_a_file_and_reports_to_the_error_stream(
    corpus: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """So that a pipe gets the document and a person still gets the report."""
    out = tmp_path / "exported" / "corpus.jsonl"
    assert main(["export", str(corpus), "--out", str(out)]) == 0

    captured = capsys.readouterr()
    assert captured.out == "", "the report went to standard output and would corrupt a pipe"
    assert "2 documents" in captured.err
    assert len(out.read_text(encoding="utf-8").splitlines()) == 2


def test_the_command_writes_the_document_to_a_pipe(
    corpus: Path, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    assert main(["export", str(corpus)]) == 0
    captured = capsysbinary.readouterr()
    body = captured.out.decode("utf-8")
    assert [json.loads(line)["id"] for line in body.splitlines()] == [
        "vault:design/gear.md",
        "vault:stove.md",
    ]


# -- the shapes that were missing, and the table ---------------------------


def test_the_haystack_shape_is_what_its_document_takes(corpus: Path) -> None:
    """`haystack.Document(id=..., content=..., meta=...)`. The third shape to
    differ in the metadata key, which is why SHAPES grew a third slot."""
    reader = Corpus(corpus)
    record = next(iter(documents(reader, str(corpus))))
    body = json.loads(as_line(record, "haystack"))
    assert set(body) == {"id", "content", "meta"}
    assert body["meta"]["unit_key"] == "design/gear.md"


def test_a_parquet_export_holds_the_same_rows_with_the_same_names(
    corpus: Path, tmp_path: Path
) -> None:
    """The columns are the JSON Lines keys, so a reader moving between the two
    finds the same names -- and the citation still comes home from a table."""
    pyarrow = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")

    out = tmp_path / "corpus.parquet"
    count = write_parquet(documents(Corpus(corpus), str(corpus)), out)
    table = pq.read_table(out)

    assert count == 2 == table.num_rows
    rows = exported(corpus)
    assert table.column("id").to_pylist() == [row["id"] for row in rows]
    assert table.column("text").to_pylist() == [row["text"] for row in rows]
    metadatas = [row["metadata"] for row in rows]
    assert all(isinstance(metadata, dict) for metadata in metadatas)
    for name in ("unit_key", "trace_map", "corpus", "body_offset", "traceable_coverage"):
        assert table.column(name).to_pylist() == [
            metadata[name] for metadata in metadatas if isinstance(metadata, dict)
        ], name
    assert isinstance(table.schema.field("characters").type, type(pyarrow.int64()))


def test_the_parquet_command_needs_a_file(corpus: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pytest.importorskip("pyarrow")
    assert main(["export", str(corpus), "--format", "parquet"]) == 1
    assert "--out" in capsys.readouterr().err


def test_the_parquet_command_writes_a_table(corpus: Path, tmp_path: Path) -> None:
    pq = pytest.importorskip("pyarrow.parquet")
    out = tmp_path / "t" / "corpus.parquet"
    assert main(["export", str(corpus), "--format", "parquet", "--out", str(out)]) == 0
    assert pq.read_table(out).num_rows == 2


def test_without_pyarrow_the_message_names_the_extra(
    corpus: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Offered, never claimed ([ADR-0028]): nothing imports pyarrow until the
    format is asked for, and the caller who lacks it is told what to install
    rather than shown an ImportError from inside a writer."""
    import builtins

    real_import = builtins.__import__

    def refusing(name: str, *args: object, **kwargs: object) -> object:
        if name.startswith("pyarrow"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", refusing)
    monkeypatch.delitem(sys.modules, "pyarrow", raising=False)
    monkeypatch.delitem(sys.modules, "pyarrow.parquet", raising=False)
    with pytest.raises(ContractError, match=ARROW_EXTRA.replace("[", "\\[")):
        write_parquet(documents(Corpus(corpus), str(corpus)), tmp_path / "x.parquet")


def test_the_package_hands_out_the_rows_one_at_a_time(corpus: Path) -> None:
    """`musubi.documents()` for the caller who wants Python rather than a
    file, and a generator so that a corpus of any size costs one document."""
    import musubi

    rows = musubi.documents(corpus)
    assert hasattr(rows, "__next__"), "a list would hold the whole corpus"
    first = next(rows)
    assert first.id == "vault:design/gear.md"
    assert first.metadata["corpus"] == str(corpus.resolve())


def test_the_command_does_not_hold_the_corpus(
    corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The writer sees the first line before the reader has produced the last.

    Asserted by interleaving rather than by measuring memory: a generator that
    is consumed as it yields cannot have been collected into a list first, and
    that is the whole of the property.
    """
    from musubi.application import export

    order: list[str] = []
    real = export.documents

    def noting(reader: object, root: str = "") -> object:
        for record in real(reader, root):  # type: ignore[arg-type]
            order.append(f"read {record.id}")
            yield record

    class Sink:
        def write(self, chunk: bytes) -> int:
            order.append("write")
            return len(chunk)

    monkeypatch.setattr(export, "documents", noting)
    export.write(noting(Corpus(corpus), str(corpus)), Sink())  # type: ignore[arg-type]
    assert order[:2] == ["read vault:design/gear.md", "write"], order
