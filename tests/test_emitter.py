"""Writing the corpus, and not writing it until the run has passed.

ADR-0008 hangs on staging: a credential means nothing is promoted, including the
units that converted cleanly before it. ADR-0013 means there is one emitter and
it writes documents, not somebody else's records.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from musubi.domain.frontmatter import (
    PRODUCER,
    FrontMatter,
    block_of,
    replacements,
    stated_keys,
)
from musubi.domain.hashing import content_hash
from musubi.domain.record import Unit
from musubi.domain.span import Span
from musubi.domain.trace import Kind
from musubi.errors import ConversionError
from musubi.infrastructure.converters import MarkdownConverter, PlainTextConverter
from musubi.infrastructure.emitters import DOCUMENTS, STAGING, TRACES, DocumentEmitter
from musubi.ports.converter import Converted
from musubi.ports.emitter import Artefact, Document, Emitter


def document(key: str, body: str, *, media_type: str = "text/markdown") -> Document:
    raw = body.encode()
    converter = MarkdownConverter() if media_type == "text/markdown" else PlainTextConverter()
    converted = converter.convert(raw, media_type)
    assert isinstance(converted, Converted)
    return Document(
        unit=Unit.of("vault", tuple(key.split("/")), raw, media_type),
        text=converted.text,
        trace=converted.trace,
        converter=converted.converter,
        source_encoding=converted.source_encoding,
        source_bom_bytes=converted.source_bom_bytes,
    )


def emit(destination: Path, *documents: Document) -> tuple[DocumentEmitter, list[Artefact]]:
    emitter = DocumentEmitter(destination)
    emitter.begin()
    return emitter, [emitter.stage(d) for d in documents]


# -- front matter -----------------------------------------------------------


def test_a_document_with_no_front_matter_gets_a_block() -> None:
    inserted = replacements("# 見出し\n", FrontMatter())
    assert len(inserted) == 1
    assert inserted[0].text == "---\nlayer: fact\nproducer: musubi.sync/1\n---\n"
    assert inserted[0].span == Span(0, 0)


def test_musubi_writes_only_what_it_is_entitled_to_say() -> None:
    """No title -- tsumugi takes a better one from the first heading. No
    observed_at -- musubi does not know when a note was written, and an mtime
    here would make a re-sync that changed nothing rewrite the corpus."""
    written = FrontMatter().as_lines()
    assert written == ("layer: fact", f"producer: {PRODUCER}")


def test_the_producer_is_a_contract_name_and_not_a_version() -> None:
    """A version here would change every artefact in the corpus on every
    release, and rewrite a corpus that had not changed."""
    assert PRODUCER == "musubi.sync/1"


def test_a_document_that_already_has_front_matter_keeps_it() -> None:
    source = "---\ntags: [camping]\n---\n\n# 見出し\n"
    inserted = replacements(source, FrontMatter())
    assert inserted[0].span == Span(4, 4), "just after the opening fence"
    assert inserted[0].text == "layer: fact\nproducer: musubi.sync/1\n"


def test_a_key_the_owner_already_stated_is_left_alone() -> None:
    """tsumugi's parser uses setdefault, so the first occurrence wins. Writing
    a second would be musubi arguing with a document about itself."""
    source = "---\nlayer: measure\n---\nbody\n"
    (inserted,) = replacements(source, FrontMatter())
    assert inserted.text == f"producer: {PRODUCER}\n"


def test_a_document_that_states_everything_gets_nothing() -> None:
    source = f"---\nlayer: fact\nproducer: {PRODUCER}\n---\nbody\n"
    assert replacements(source, FrontMatter()) == ()


def test_an_unclosed_fence_is_not_front_matter() -> None:
    """Detected exactly as tsumugi detects it. A block musubi thinks is front
    matter and the reader thinks is prose puts musubi's keys into the body."""
    assert block_of("---\nnever closed\n") is None
    assert block_of("---\nclosed\n---\n") == Span(0, 14)
    assert block_of("not front matter\n---\n") is None


def test_a_closing_ellipsis_fence_is_recognised_too() -> None:
    assert block_of("---\nx: 1\n...\n") is not None


def test_the_keys_a_block_states_are_read_by_line_and_not_parsed() -> None:
    source = "---\ntags: [a, b]\n- item\nlayer: fact\n---\n"
    block = block_of(source)
    assert block is not None
    assert stated_keys(source, block) == frozenset({"tags", "layer"})


def test_an_interpretation_is_refused() -> None:
    """ADR-0010. An interpretation needs a reading, a reading needs a model, and
    musubi has none."""
    with pytest.raises(ValueError, match="never 'interpretation'"):
        FrontMatter("interpretation")


def test_a_value_that_cannot_be_written_bare_is_refused() -> None:
    """tsumugi strips the line and keeps what is left, so a quoted value arrives
    with its quotes and a broken one arrives broken."""
    with pytest.raises(ValueError, match="line break"):
        FrontMatter("fact", "musubi\nsync")
    with pytest.raises(ValueError, match="bare single-line"):
        FrontMatter("fact", " padded ")


# -- what gets written ------------------------------------------------------


def test_staging_writes_the_document_and_its_map(tmp_path: Path) -> None:
    emitter, (artefact,) = emit(tmp_path, document("design/gear.md", "# 見出し\n"))
    assert emitter.staged == ("documents/design/gear.md", "traces/design/gear.md.json")
    assert artefact.path == "documents/design/gear.md"
    assert artefact.trace_path == "traces/design/gear.md.json"


def test_the_map_lives_outside_the_folder_a_consumer_ingests(tmp_path: Path) -> None:
    """A sidecar beside the document would be ingested as a document: tsumugi's
    walk does not skip `.musubi`, and its parser registry claims `.json`."""
    emitter, _ = emit(tmp_path, document("a.md", "x\n"))
    emitter.promote()
    assert not list((tmp_path / DOCUMENTS).rglob("*.json"))
    assert (tmp_path / TRACES / "a.md.json").is_file()


def test_the_written_document_carries_the_front_matter(tmp_path: Path) -> None:
    emitter, _ = emit(tmp_path, document("a.md", "# 見出し\n"))
    emitter.promote()
    written = (tmp_path / DOCUMENTS / "a.md").read_text(encoding="utf-8")
    assert written == f"---\nlayer: fact\nproducer: {PRODUCER}\n---\n# 見出し\n"


def test_a_plain_text_artefact_gets_no_front_matter(tmp_path: Path) -> None:
    """Front matter is a Markdown convention. A `.txt` keeps its layer in the
    manifest and the map, where a consumer that cannot read front matter would
    look anyway."""
    emitter, _ = emit(tmp_path, document("a.txt", "hello\n", media_type="text/plain"))
    emitter.promote()
    assert (tmp_path / DOCUMENTS / "a.txt").read_text(encoding="utf-8") == "hello\n"


def test_the_front_matter_is_synthetic_in_the_map(tmp_path: Path) -> None:
    """musubi wrote it, so it counts against traceable coverage rather than for
    it -- the number would otherwise flatter every short document."""
    emitter, (artefact,) = emit(tmp_path, document("a.md", "body\n"))
    trace = json.loads((emitter.staging / TRACES / "a.md.json").read_text(encoding="utf-8"))
    assert trace["segments"][0]["kind"] == Kind.SYNTHETIC.value
    assert trace["segments"][0]["rule"] == "front_matter"
    assert artefact.traceable_characters == len("body\n")
    assert artefact.characters > artefact.traceable_characters


def test_the_owners_text_still_resolves_after_the_block_was_added(tmp_path: Path) -> None:
    source = "# 見出し\n\nテントは 2.4kg です\n"
    doc = document("a.md", source)
    emitter, _ = emit(tmp_path, doc)
    emitter.promote()

    written = (tmp_path / DOCUMENTS / "a.md").read_text(encoding="utf-8")
    trace = json.loads((tmp_path / TRACES / "a.md.json").read_text(encoding="utf-8"))
    at = written.index("2.4kg")
    segment = next(
        s for s in trace["segments"] if s["out"][0] <= at < s["out"][1] and s["kind"] == "verbatim"
    )
    offset = segment["src"][0] + (at - segment["out"][0])
    assert source[offset : offset + 5] == "2.4kg"


# -- the sidecar ------------------------------------------------------------


def test_the_sidecar_names_its_contract_and_says_it_is_a_draft(tmp_path: Path) -> None:
    emitter, _ = emit(tmp_path, document("a.md", "x\n"))
    trace = json.loads((emitter.staging / TRACES / "a.md.json").read_text(encoding="utf-8"))
    assert trace["contract"] == "musubi.trace-map/1-draft"


def test_the_sidecar_carries_what_a_byte_offset_needs(tmp_path: Path) -> None:
    """ADR-0018: the map is in characters, and this is the rest of what the
    command holding the file needs."""
    doc = document("a.md", "x\n")
    emitter, _ = emit(tmp_path, doc)
    trace = json.loads((emitter.staging / TRACES / "a.md.json").read_text(encoding="utf-8"))
    assert trace["source_unit"] == "characters"
    assert trace["source"]["encoding"] == "utf-8"
    assert trace["source"]["bom_bytes"] == 0
    assert trace["source"]["content_hash"] == doc.unit.content_hash


def test_the_sidecar_hashes_the_artefact_as_written(tmp_path: Path) -> None:
    emitter, (artefact,) = emit(tmp_path, document("a.md", "x\n"))
    written = (emitter.staging / DOCUMENTS / "a.md").read_text(encoding="utf-8")
    trace = json.loads((emitter.staging / TRACES / "a.md.json").read_text(encoding="utf-8"))
    assert trace["artefact"]["content_hash"] == content_hash(written) == artefact.content_hash


# -- staging and promotion --------------------------------------------------


def test_nothing_reaches_the_destination_until_it_is_promoted(tmp_path: Path) -> None:
    emit(tmp_path, document("a.md", "x\n"))
    assert not (tmp_path / DOCUMENTS).exists()
    assert (tmp_path / STAGING / DOCUMENTS / "a.md").is_file()


def test_discarding_leaves_the_destination_untouched(tmp_path: Path) -> None:
    """ADR-0008's mechanism. A credential means this, and not a skipped unit."""
    emitter, _ = emit(tmp_path, document("a.md", "x\n"), document("b.md", "y\n"))
    emitter.discard()
    assert not (tmp_path / DOCUMENTS).exists()
    assert not (tmp_path / STAGING).exists()
    assert emitter.staged == ()


def test_promotion_moves_everything_and_clears_the_staging_area(tmp_path: Path) -> None:
    emitter, _ = emit(tmp_path, document("a.md", "x\n"), document("deep/b.md", "y\n"))
    moved = emitter.promote()
    assert moved == (
        "documents/a.md",
        "documents/deep/b.md",
        "traces/a.md.json",
        "traces/deep/b.md.json",
    )
    assert not (tmp_path / STAGING).exists()
    assert (tmp_path / DOCUMENTS / "deep" / "b.md").is_file()


def test_promotion_replaces_what_a_previous_run_wrote(tmp_path: Path) -> None:
    emitter, _ = emit(tmp_path, document("a.md", "first\n"))
    emitter.promote()
    emitter, _ = emit(tmp_path, document("a.md", "second\n"))
    emitter.promote()
    assert "second" in (tmp_path / DOCUMENTS / "a.md").read_text(encoding="utf-8")


def test_beginning_again_throws_away_what_a_crashed_run_left(tmp_path: Path) -> None:
    """A staging area from a crashed run holds half a corpus. Reusing it would
    promote a mixture of two runs, which ADR-0003 says cannot happen."""
    emitter, _ = emit(tmp_path, document("stale.md", "x\n"))
    emitter.begin()
    assert emitter.staged == ()
    assert not (tmp_path / STAGING / DOCUMENTS / "stale.md").exists()


def test_the_manifest_is_staged_and_promoted_with_the_rest(tmp_path: Path) -> None:
    emitter, _ = emit(tmp_path, document("a.md", "x\n"))
    emitter.stage_manifest('{"contract": "musubi.sync-manifest/1-draft"}\n')
    emitter.promote()
    assert (tmp_path / "manifest.json").is_file()


def test_the_emitter_names_itself(tmp_path: Path) -> None:
    emitter: Emitter = DocumentEmitter(tmp_path)
    assert emitter.name == "documents@1"


# -- determinism ------------------------------------------------------------


def test_two_runs_over_the_same_input_write_the_same_bytes(tmp_path: Path) -> None:
    """ADR-0003, at the only place it can finally be checked end to end."""
    source = "---\ntags: [x]\n---\n\n# 見出し\r\n\r\nテントは 2.4kg\r\n"

    def build(where: Path) -> dict[str, bytes]:
        emitter, _ = emit(where, document("design/gear.md", source))
        emitter.promote()
        return {
            path.relative_to(where).as_posix(): path.read_bytes()
            for path in sorted(where.rglob("*"))
            if path.is_file()
        }

    assert build(tmp_path / "one") == build(tmp_path / "two")


def test_the_corpus_is_utf8_with_lf_whatever_the_platform(tmp_path: Path) -> None:
    """A corpus whose bytes depend on which machine built it is a corpus whose
    hashes do."""
    emitter, _ = emit(tmp_path, document("a.md", "one\r\ntwo\r\n"))
    emitter.promote()
    raw = (tmp_path / DOCUMENTS / "a.md").read_bytes()
    assert b"\r" not in raw
    assert raw.decode("utf-8")


# -- defence in depth -------------------------------------------------------


def test_a_forged_key_cannot_talk_the_emitter_out_of_its_own_folder(tmp_path: Path) -> None:
    """`unit_key` already refuses `..`, so this is unreachable through the front
    door. It is checked anyway, because the emitter is what actually writes and
    a guard that lives only at the far end of a call chain is a guard somebody
    will one day route around."""
    doc = document("a.md", "x\n")
    forged = Document(
        unit=Unit(
            source_id="vault",
            unit_key="../../escaped.md",
            content_hash=doc.unit.content_hash,
            media_type="text/markdown",
        ),
        text=doc.text,
        trace=doc.trace,
        converter=doc.converter,
    )
    emitter = DocumentEmitter(tmp_path)
    emitter.begin()
    with pytest.raises(ConversionError, match="outside the staging area"):
        emitter.stage(forged)
    assert not (tmp_path.parent / "escaped.md").exists()
