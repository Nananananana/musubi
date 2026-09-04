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
from pathlib import Path

import pytest

from musubi import __version__
from musubi.application.export import SHAPES, as_line, documents
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

    identifier, content = SHAPES[shape]
    assert set(body) == {identifier, content, "metadata"}
    assert body[identifier] == record.id
    assert body[content] == record.text
    assert body["metadata"] == dict(record.metadata)


def test_an_unknown_shape_is_refused_and_the_known_ones_are_named(corpus: Path) -> None:
    reader = Corpus(corpus)
    record = next(iter(documents(reader, str(corpus))))
    with pytest.raises(ContractError, match="jsonl"):
        as_line(record, "haystack")


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
