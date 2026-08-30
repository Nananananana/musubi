"""`musubi trace`: the command the whole design is for.

Everything else in musubi is a pipeline somebody else also has. This is the part
that only works because of ADR-0004 — a range in a document musubi built,
resolved through every transformation, to a place in the file the owner has.

ADR-0018 is exercised here too, and this is the layer it was deferred to: the
map is in characters, and the byte offset is computed by the thing holding the
file.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pytest

from musubi import __version__
from musubi.application.pipeline import Settings
from musubi.application.sync import sync
from musubi.application.trace import Resolution, resolve
from musubi.domain.span import Span
from musubi.domain.trace import Kind
from musubi.errors import ContractError, TraceError
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.corpus import Corpus
from musubi.infrastructure.emitters import DOCUMENTS, MANIFEST, TRACES, DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import ObsidianSource
from musubi.interfaces.cli import main

NOTE = "# テント設計メモ\n\nテントは 2.4kg。\n\n参考: https://example.com/g?utm_source=news&id=7\n"


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def built(tmp_path: Path, files: dict[str, str] | None = None) -> tuple[Path, Path]:
    """A real corpus, built by a real sync."""
    root = tmp_path / "vault"
    for name, body in (files or {"design/gear.md": NOTE}).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    into = tmp_path / "synced"
    sync(
        ObsidianSource(root),
        Settings(CORE, default_screener(), converter_for, __version__),
        DocumentEmitter(into),
    )
    return root, into


def where(into: Path, key: str, needle: str) -> tuple[Corpus, str, Span]:
    """A corpus, a key and the range of a phrase in the artefact."""
    at = (into / DOCUMENTS / key).read_text(encoding="utf-8").index(needle)
    return Corpus(into), key, Span(at, at + len(needle))


# -- the answer -------------------------------------------------------------


def test_a_range_resolves_to_the_file_the_owner_has(tmp_path: Path) -> None:
    root, into = built(tmp_path)
    corpus, key, span = where(into, "design/gear.md", "2.4kg")
    found = resolve(corpus, key, span)

    assert found.kinds == (Kind.VERBATIM,)
    assert found.excerpt == "2.4kg"
    assert found.source.unit_key == "design/gear.md"
    assert found.source_excerpt == "2.4kg"
    assert found.source_path == root / "design" / "gear.md"


def test_the_byte_offset_is_computed_here_because_here_is_where_the_file_is(
    tmp_path: Path,
) -> None:
    """ADR-0018. The map is in characters; a byte offset takes the encoding, the
    byte-order mark and the file, and this is the layer with all three."""
    root, into = built(tmp_path)
    corpus, key, span = where(into, "design/gear.md", "2.4kg")
    found = resolve(corpus, key, span)

    assert found.source_bytes is not None
    raw = (root / "design" / "gear.md").read_bytes()
    assert raw[found.source_bytes.start : found.source_bytes.end].decode() == "2.4kg"
    assert found.source_bytes != found.source_span, "CJK before it: bytes are not characters"


def test_a_byte_order_mark_is_counted_into_the_offset(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "a.md").write_bytes(b"\xef\xbb\xbf" + "見出し 2.4kg\n".encode())
    into = tmp_path / "synced"
    sync(
        ObsidianSource(root),
        Settings(CORE, default_screener(), converter_for, __version__),
        DocumentEmitter(into),
    )
    corpus, key, span = where(into, "a.md", "2.4kg")
    found = resolve(corpus, key, span)

    assert found.source.bom_bytes == 3
    raw = (root / "a.md").read_bytes()
    assert found.source_bytes is not None
    assert raw[found.source_bytes.start : found.source_bytes.end].decode() == "2.4kg"


def test_a_range_musubi_wrote_says_so(tmp_path: Path) -> None:
    """The honest answer, and the one a naive resolver gets wrong by reporting a
    source range for text that has no source."""
    _, into = built(tmp_path)
    corpus, key, span = where(into, "design/gear.md", "producer: musubi.sync/1")
    found = resolve(corpus, key, span)

    assert found.is_synthetic
    assert found.kinds == (Kind.SYNTHETIC,)
    assert found.rules == ("front_matter",)


def test_a_range_over_a_cut_query_reports_the_transformation(tmp_path: Path) -> None:
    """The query kept `id=7` and lost the tracking parameter, so it is the same
    content in different characters, and the range covers what was taken."""
    _, into = built(tmp_path)
    corpus, key, span = where(into, "design/gear.md", "https://example.com/g?id=7")
    found = resolve(corpus, key, span)

    assert Kind.TRANSFORMED in found.kinds
    assert "url_query" in found.rules
    assert found.source_excerpt is not None
    assert "utm_source=news" in found.source_excerpt


def test_a_range_stopping_at_the_boundary_claims_nothing_beyond_it(tmp_path: Path) -> None:
    _, into = built(tmp_path)
    corpus, key, span = where(into, "design/gear.md", "https://example.com/g")
    assert resolve(corpus, key, span).kinds == (Kind.VERBATIM,)


def test_a_range_that_had_something_taken_out_of_it_says_so(tmp_path: Path) -> None:
    """A removal occupies no output, so it overlaps nothing and a span union
    covers it silently. Somebody tracing a range that had a tracking parameter
    cut out of the middle of it should be told -- ADR-0005 applied to a query
    rather than to a manifest.
    """
    stripped = "see https://x.example/?utm_source=news and stop\n"
    _, into = built(tmp_path, {"a.md": stripped})
    corpus, key, span = where(into, "a.md", "https://x.example/ and")
    found = resolve(corpus, key, span)

    assert Kind.REMOVAL in found.kinds
    assert "url_query" in found.rules
    assert found.source_excerpt is not None
    assert "utm_source=news" in found.source_excerpt, "the range covers what was taken"


def test_a_range_spanning_several_runs_reports_each_kind_once(tmp_path: Path) -> None:
    _, into = built(tmp_path)
    whole = Span.over((into / DOCUMENTS / "design" / "gear.md").read_text(encoding="utf-8"))
    found = resolve(Corpus(into), "design/gear.md", whole)
    assert set(found.kinds) >= {Kind.SYNTHETIC, Kind.VERBATIM, Kind.TRANSFORMED}
    assert len(found.kinds) == len(set(found.kinds))


# -- and what it will not pretend -------------------------------------------


def test_a_source_that_has_changed_since_the_sync_is_reported(tmp_path: Path) -> None:
    """The offsets are then about a document that no longer exists, and
    reporting them without saying so points a reader confidently at the wrong
    place."""
    root, into = built(tmp_path)
    corpus, key, span = where(into, "design/gear.md", "2.4kg")
    (root / "design" / "gear.md").write_text("something else entirely\n", encoding="utf-8")

    found = resolve(corpus, key, span)
    assert found.changed


def test_a_source_that_is_no_longer_there_degrades_rather_than_fails(tmp_path: Path) -> None:
    """The character range is what the map holds, so it is still an answer. What
    it cannot do without the file is give a byte offset, and it says so."""
    root, into = built(tmp_path)
    corpus, key, span = where(into, "design/gear.md", "2.4kg")
    (root / "design" / "gear.md").unlink()

    found = resolve(corpus, key, span)
    assert found.source_bytes is None
    assert found.source_path is None
    assert found.source_span.length == 5, "the map still knows where it was"


def test_an_artefact_edited_since_the_sync_stops_the_answer(tmp_path: Path) -> None:
    _, into = built(tmp_path)
    (into / DOCUMENTS / "design" / "gear.md").write_text("shorter\n", encoding="utf-8")

    with pytest.raises(TraceError, match="has been edited since the sync"):
        resolve(Corpus(into), "design/gear.md", Span(0, 5))


def test_a_range_past_the_end_of_the_artefact_is_refused(tmp_path: Path) -> None:
    _, into = built(tmp_path)
    with pytest.raises(TraceError, match="is outside"):
        resolve(Corpus(into), "design/gear.md", Span(0, 99999))


def test_a_map_from_a_contract_nobody_recognises_stops_the_answer(tmp_path: Path) -> None:
    """A map read wrong points a reader at the wrong place in their own file."""
    _, into = built(tmp_path)
    sidecar = into / TRACES / "design" / "gear.md.json"
    body = json.loads(sidecar.read_text(encoding="utf-8"))
    body["contract"] = "musubi.trace-map/9"
    sidecar.write_text(json.dumps(body), encoding="utf-8")

    with pytest.raises(ContractError, match="does not recognise"):
        resolve(Corpus(into), "design/gear.md", Span(0, 3))


def test_a_map_measured_in_something_else_stops_the_answer(tmp_path: Path) -> None:
    """ADR-0018 kept `source_unit` so an old reader can see a locator it does
    not understand. Refusing is the intended behaviour."""
    _, into = built(tmp_path)
    sidecar = into / TRACES / "design" / "gear.md.json"
    body = json.loads(sidecar.read_text(encoding="utf-8"))
    body["source_unit"] = "pdf-page"
    sidecar.write_text(json.dumps(body), encoding="utf-8")

    with pytest.raises(ContractError, match="does not know how to read"):
        resolve(Corpus(into), "design/gear.md", Span(0, 3))


def test_a_map_that_does_not_hold_stops_the_answer(tmp_path: Path) -> None:
    _, into = built(tmp_path)
    sidecar = into / TRACES / "design" / "gear.md.json"
    body = json.loads(sidecar.read_text(encoding="utf-8"))
    body["segments"] = body["segments"][1:]  # a gap at the start
    sidecar.write_text(json.dumps(body), encoding="utf-8")

    with pytest.raises(TraceError, match="does not hold"):
        resolve(Corpus(into), "design/gear.md", Span(0, 3))


def test_a_segment_this_cannot_read_stops_the_answer(tmp_path: Path) -> None:
    _, into = built(tmp_path)
    sidecar = into / TRACES / "design" / "gear.md.json"
    body = json.loads(sidecar.read_text(encoding="utf-8"))
    body["segments"][0]["kind"] = "guessed"
    sidecar.write_text(json.dumps(body), encoding="utf-8")

    with pytest.raises(ContractError, match="cannot read"):
        resolve(Corpus(into), "design/gear.md", Span(0, 3))


# -- finding things ---------------------------------------------------------


def test_the_corpus_is_found_by_walking_up_from_the_document(tmp_path: Path) -> None:
    """A reader following a citation has a path to a document and no reason to
    know how musubi arranges a destination."""
    _, into = built(tmp_path)
    corpus, key = Corpus.holding(into / DOCUMENTS / "design" / "gear.md")
    assert corpus.destination == into.resolve()
    assert key == "design/gear.md"


def test_a_file_outside_a_destination_says_so(tmp_path: Path) -> None:
    stray = tmp_path / "elsewhere.md"
    stray.write_text("x\n", encoding="utf-8")
    with pytest.raises(TraceError, match="not inside a musubi destination"):
        Corpus.holding(stray)


def test_a_decomposed_filename_is_still_found(tmp_path: Path) -> None:
    """ADR-0014's stated cost, paid. A key is NFC and a macOS filename is NFD,
    so `root / unit_key` misses on the machine the notes were written on."""
    decomposed = unicodedata.normalize("NFD", "café.md")
    _, into = built(tmp_path, {decomposed: "テントは 2.4kg。\n"})

    key = unicodedata.normalize("NFC", "café.md")
    corpus, key, span = where(into, key, "2.4kg")
    found = resolve(corpus, key, span)

    assert found.source_path is not None
    assert found.source_excerpt == "2.4kg"


def test_a_source_root_the_manifest_does_not_name_gives_no_file(tmp_path: Path) -> None:
    _, into = built(tmp_path)
    body = json.loads((into / MANIFEST).read_text(encoding="utf-8"))
    body["sources"][0]["root"] = ""
    (into / MANIFEST).write_text(json.dumps(body), encoding="utf-8")

    corpus, key, span = where(into, "design/gear.md", "2.4kg")
    assert resolve(corpus, key, span).source_path is None


def test_a_destination_with_no_manifest_still_traces(tmp_path: Path) -> None:
    """The map is enough for the character range; the manifest is only how the
    source file gets found."""
    _, into = built(tmp_path)
    (into / MANIFEST).unlink()
    corpus, key, span = where(into, "design/gear.md", "2.4kg")
    found = resolve(corpus, key, span)
    assert found.source_span.length == 5
    assert found.source_path is None


def test_a_corpus_can_be_named_instead_of_walked_to(tmp_path: Path) -> None:
    _, into = built(tmp_path)
    assert resolve(Corpus(into), "design/gear.md", Span(0, 3)).artefact == "design/gear.md"


# -- the command ------------------------------------------------------------


def target(into: Path, key: str, needle: str) -> str:
    _, _, span = where(into, key, needle)
    return f"{into / DOCUMENTS / key}:{span.start}-{span.end}"


def test_the_command_prints_the_answer(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, into = built(tmp_path)
    assert main(["trace", target(into, "design/gear.md", "2.4kg")]) == 0

    out = capsys.readouterr().out
    assert "verbatim" in out
    assert "vault:design/gear.md" in out
    assert "characters" in out
    assert "bytes" in out
    assert "2.4kg" in out


def test_the_command_says_when_musubi_wrote_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, into = built(tmp_path)
    assert main(["trace", target(into, "design/gear.md", "layer: fact")]) == 0
    assert "musubi wrote this" in capsys.readouterr().out


def test_the_command_warns_when_the_source_has_moved_on(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, into = built(tmp_path)
    where_it_is = target(into, "design/gear.md", "2.4kg")
    (root / "design" / "gear.md").write_text("different\n", encoding="utf-8")

    assert main(["trace", where_it_is]) == 0
    assert "The source has changed since the sync" in capsys.readouterr().out


def test_the_command_can_print_a_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, into = built(tmp_path)
    assert main(["trace", target(into, "design/gear.md", "2.4kg"), "--json"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["kinds"] == ["verbatim"]
    assert body["source"]["excerpt"] == "2.4kg"
    assert body["source"]["bytes"][1] > body["source"]["characters"][1]


def test_the_command_takes_a_key_and_a_destination(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, into = built(tmp_path)
    assert main(["trace", "design/gear.md:0-3", "--into", str(into)]) == 0
    assert "design/gear.md" in capsys.readouterr().out


def test_a_target_that_is_not_a_range_says_how_to_write_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["trace", "gear.md"]) == 1
    assert "document.md:1204-1231" in capsys.readouterr().err


def test_a_range_that_is_not_two_offsets_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["trace", "gear.md:a-b"]) == 1
    assert "not a range of two offsets" in capsys.readouterr().err


def test_a_backwards_range_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["trace", "gear.md:9-4"]) == 1
    assert "ends before it starts" in capsys.readouterr().err


# -- the round trip, end to end ---------------------------------------------


def test_every_verbatim_range_of_a_real_corpus_round_trips(tmp_path: Path) -> None:
    """The property the whole project is for, asserted over a real sync: a
    verbatim range of the artefact reads the same in the owner's own file."""
    root, into = built(tmp_path)
    corpus = Corpus(into)
    text = (into / DOCUMENTS / "design" / "gear.md").read_text(encoding="utf-8")

    for at in range(len(text) - 1):
        found: Resolution = resolve(corpus, "design/gear.md", Span(at, at + 1))
        if found.kinds == (Kind.VERBATIM,):
            assert found.source_excerpt == found.excerpt
            assert found.source_bytes is not None
            raw = (root / "design" / "gear.md").read_bytes()
            piece = raw[found.source_bytes.start : found.source_bytes.end]
            assert piece.decode() == found.excerpt


# -- the edges ---------------------------------------------------------------


def test_a_source_that_is_no_longer_decodable_is_reported_as_changed(tmp_path: Path) -> None:
    """It has certainly been edited. The character range is still what the map
    holds, so it is still an answer."""
    root, into = built(tmp_path)
    corpus, key, span = where(into, "design/gear.md", "2.4kg")
    (root / "design" / "gear.md").write_bytes("シフトJIS".encode("shift_jis"))

    found = resolve(corpus, key, span)
    assert found.changed
    assert found.source_bytes is None
    assert found.source_path is not None


def test_a_source_shorter_than_the_map_is_reported_as_changed(tmp_path: Path) -> None:
    root, into = built(tmp_path)
    corpus, key, span = where(into, "design/gear.md", "2.4kg")
    (root / "design" / "gear.md").write_text("x\n", encoding="utf-8")

    found = resolve(corpus, key, span)
    assert found.changed
    assert found.source_bytes is None


def test_a_source_that_cannot_be_opened_gives_no_file(tmp_path: Path) -> None:
    """A directory where the manifest says a file is. Degrades rather than
    fails: the map alone is still an answer."""
    root, into = built(tmp_path)
    corpus, key, span = where(into, "design/gear.md", "2.4kg")
    (root / "design" / "gear.md").unlink()
    (root / "design" / "gear.md").mkdir()

    found = resolve(corpus, key, span)
    assert found.source_path is None
    assert found.source_bytes is None


def test_a_key_naming_a_directory_that_is_not_there_gives_no_file(tmp_path: Path) -> None:
    _, into = built(tmp_path, {"deep/a.md": "テントは 2.4kg。\n"})
    corpus, key, span = where(into, "deep/a.md", "2.4kg")
    sidecar = into / TRACES / "deep" / "a.md.json"
    body = json.loads(sidecar.read_text(encoding="utf-8"))
    body["source"]["unit_key"] = "nowhere/a.md"
    sidecar.write_text(json.dumps(body), encoding="utf-8")

    assert resolve(corpus, key, span).source_path is None


def test_an_artefact_that_is_not_there_says_which(tmp_path: Path) -> None:
    _, into = built(tmp_path)
    with pytest.raises(TraceError, match="cannot read"):
        resolve(Corpus(into), "never-written.md", Span(0, 1))


def test_a_map_that_is_not_json_says_so(tmp_path: Path) -> None:
    _, into = built(tmp_path)
    (into / TRACES / "design" / "gear.md.json").write_text("not json", encoding="utf-8")
    with pytest.raises(ContractError, match="not readable as a document"):
        resolve(Corpus(into), "design/gear.md", Span(0, 3))


def test_a_map_that_is_not_an_object_says_so(tmp_path: Path) -> None:
    _, into = built(tmp_path)
    (into / TRACES / "design" / "gear.md.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ContractError, match="not an object"):
        resolve(Corpus(into), "design/gear.md", Span(0, 3))


def test_an_empty_query_at_a_point_answers_for_that_point(tmp_path: Path) -> None:
    _, into = built(tmp_path)
    found = resolve(Corpus(into), "design/gear.md", Span(0, 0))
    assert found.excerpt == ""
    assert found.kinds == (Kind.SYNTHETIC,), "the front matter starts here"


def test_a_key_whose_folder_is_actually_a_file_gives_no_file(tmp_path: Path) -> None:
    """The search ADR-0014 requires walks one level at a time, so it has to cope
    with a level that is not a directory."""
    _, into = built(tmp_path)
    sidecar = into / TRACES / "design" / "gear.md.json"
    body = json.loads(sidecar.read_text(encoding="utf-8"))
    body["source"]["unit_key"] = "design/gear.md/deeper.md"
    sidecar.write_text(json.dumps(body), encoding="utf-8")

    assert resolve(Corpus(into), "design/gear.md", Span(0, 3)).source_path is None


def test_the_command_names_the_rules_a_range_went_through(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, into = built(tmp_path)
    assert main(["trace", target(into, "design/gear.md", "https://example.com/g?id=7")]) == 0
    assert "through: url_query" in capsys.readouterr().out
