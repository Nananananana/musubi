"""The number that goes up when the guarantee stops holding.

`traceable_coverage` reads 100% for a map with one `transformed` segment
covering the whole document: every offset resolves, to the entire file. That is
the shape a corpus gets when an extractor and its source disagree — a page
whose paragraphs were reflowed, a PDF read in the wrong column order — and the
failure reports the **higher** coverage (#81, [ADR-0033]).

`answer_width` was added to `TraceMap` and left there. The manifest is where
people read numbers, so these are about it arriving there correctly: the
aggregate being a sum of numerators rather than a mean of means, the mixed
corpus that has no such number, and `verify` adding it up.

The first test is the one the rest exist for. It builds the failure and shows
coverage staying at 100% while the width goes to the length of the document.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from musubi import __version__
from musubi.application.pipeline import Settings
from musubi.application.sync import sync
from musubi.application.verify import verify
from musubi.domain.manifest import Artefact, Coverage, Manifest, render
from musubi.domain.span import Span
from musubi.domain.trace import CHARACTERS, OPAQUE, Kind, Segment, TraceMap
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.corpus import Corpus
from musubi.infrastructure.emitters import MANIFEST, DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import ObsidianSource
from musubi.interfaces.cli import main

NOTE = "# テント設計メモ\n\nテントは 2.4kg。\n"


def artefact(**fields: object) -> Artefact:
    base: dict[str, object] = {
        "path": "documents/a.md",
        "content_hash": "sha256:" + "0" * 64,
        "trace_path": "traces/a.md.json",
        "source_id": "vault",
        "unit_key": "a.md",
        "converter": "markdown@1",
        "traceable_characters": 10,
        "characters": 10,
        "layer": "fact",
    }
    return Artefact(**{**base, **fields})  # type: ignore[arg-type]


def built(tmp_path: Path, files: dict[str, str] | None = None) -> Path:
    root = tmp_path / "vault"
    for name, body in (files or {"gear.md": NOTE}).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    into = tmp_path / "corpus"
    sync(
        ObsidianSource(root),
        Settings(CORE, default_screener(), converter_for, __version__, created_at="t"),
        DocumentEmitter(into),
    )
    return into


# -- the failure the metric exists to catch ---------------------------------


def test_a_map_that_resolves_everywhere_and_locates_nothing_reports_it() -> None:
    """100% traceable, and every offset answers with the whole document.

    This is what an alignment that matched nothing produces, and coverage
    cannot tell it from a perfect map. The width can: it is the length of the
    document rather than 1.
    """
    exact = TraceMap(
        segments=(Segment(out=Span(0, 40), src=Span(0, 40), kind=Kind.VERBATIM),),
        artefact_length=40,
        source_length=40,
    )
    useless = TraceMap(
        segments=(
            Segment(out=Span(0, 40), src=Span(0, 40), kind=Kind.TRANSFORMED, rule="aligned"),
        ),
        artefact_length=40,
        source_length=40,
    )

    assert exact.traceable_coverage == useless.traceable_coverage == 1.0
    assert exact.answer_width == 1.0
    assert useless.answer_width == 40.0
    assert exact.answered_source_units == 40
    assert useless.answered_source_units == 1600


# -- the aggregate is not a mean of means -----------------------------------


def test_the_corpus_width_is_a_sum_of_numerators_over_a_sum_of_denominators() -> None:
    """A four-character document answering with forty and a forty-thousand
    character one answering exactly. The mean of the two widths is alarming
    about a corpus that is almost entirely exact; the weighted answer is not,
    and the weighted answer is the true one."""
    tiny = artefact(
        unit_key="tiny.md", traceable_characters=4, characters=4, answered_source_units=40
    )
    huge = artefact(
        unit_key="huge.md",
        traceable_characters=40_000,
        characters=40_000,
        answered_source_units=40_000,
    )
    coverage = Manifest(kind="sync", musubi_version="0", artefacts=(tiny, huge)).coverage

    assert tiny.answer_width == 10.0
    assert huge.answer_width == 1.0
    mean_of_means = (tiny.answer_width + huge.answer_width) / 2
    assert mean_of_means == pytest.approx(5.5), "what the wrong arithmetic would say"

    assert coverage.answer_width == pytest.approx(40_040 / 40_004)
    assert coverage.answer_width == pytest.approx(1.0009, abs=0.0002)


def test_a_run_with_nothing_traceable_has_no_width() -> None:
    coverage = Manifest(kind="sync", musubi_version="0").coverage
    assert coverage.answer_width is None
    assert coverage.source_units == ()


# -- a corpus of mixed formats has no such number ---------------------------


def test_pages_are_not_added_to_characters() -> None:
    """A PDF's map answers in pages and a Markdown map answers in characters.
    Their sum is a number with no dimension, and printing it to four decimal
    places would be the most confident wrong answer in the manifest."""
    text = artefact(unit_key="a.md", answered_source_units=12, source_unit=CHARACTERS)
    pdf = artefact(unit_key="b.pdf", answered_source_units=3, source_unit=OPAQUE)
    mixed = Manifest(kind="sync", musubi_version="0", artefacts=(text, pdf)).coverage

    assert sorted(mixed.source_units) == [CHARACTERS, OPAQUE]
    assert mixed.answer_width is None
    assert mixed.traceable_characters == 20, "coverage survives the same corpus"
    assert mixed.traceable_coverage == 1.0


def test_an_empty_document_does_not_make_a_corpus_look_mixed() -> None:
    """Its unit says nothing about whether two widths may be added, and
    counting it would take the width away from a corpus for holding one empty
    file."""
    real = artefact(unit_key="a.md", answered_source_units=10, source_unit=CHARACTERS)
    empty = artefact(
        unit_key="b.pdf",
        traceable_characters=0,
        characters=0,
        answered_source_units=0,
        source_unit=OPAQUE,
    )
    coverage = Manifest(kind="sync", musubi_version="0", artefacts=(real, empty)).coverage

    assert coverage.source_units == (CHARACTERS,)
    assert coverage.answer_width == 1.0


# -- it reaches the manifest, and the manifest is checked -------------------


def test_the_manifest_carries_the_numerator_and_the_units(tmp_path: Path) -> None:
    into = built(tmp_path)
    body = json.loads((into / MANIFEST).read_text(encoding="utf-8"))
    (entry,) = body["artefacts"]

    assert entry["source_unit"] == CHARACTERS
    assert entry["answered_source_units"] >= entry["traceable_characters"]
    assert body["coverage"]["source_units"] == [CHARACTERS]
    assert body["coverage"]["answered_source_units"] == entry["answered_source_units"]


def test_the_new_fields_are_not_in_the_run_id(tmp_path: Path) -> None:
    """The id is over the outputs. A number derived from the map that is
    already in the map would change the id of every existing corpus on
    upgrade, and with it every journal's parent chain."""
    manifest = Manifest(kind="sync", musubi_version="0", artefacts=(artefact(),))
    widened = Manifest(
        kind="sync",
        musubi_version="0",
        artefacts=(artefact(answered_source_units=999, source_unit=OPAQUE),),
    )
    assert manifest.run_id == widened.run_id


def test_verify_adds_the_numerator_up(tmp_path: Path) -> None:
    """A published number nothing adds up is a number free to drift, and this
    one is the numerator of the metric that exists to catch coverage lying."""
    into = built(tmp_path)
    assert verify(Corpus(into)).holds

    body = json.loads((into / MANIFEST).read_text(encoding="utf-8"))
    body["coverage"]["answered_source_units"] += 1
    (into / MANIFEST).write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")

    checked = verify(Corpus(into))
    assert any(fault.subject == "coverage.answered_source_units" for fault in checked.faults)


def test_verify_catches_a_coverage_that_claims_the_wrong_units(tmp_path: Path) -> None:
    """The field a reader consults to decide whether the width means anything.
    A corpus of Markdown and PDFs claiming one unit would have that reader
    dividing pages-plus-characters by characters and believing it."""
    into = built(tmp_path)
    body = json.loads((into / MANIFEST).read_text(encoding="utf-8"))
    body["coverage"]["source_units"] = [OPAQUE]
    (into / MANIFEST).write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")

    checked = verify(Corpus(into))
    assert any(fault.invariant == "manifest 5" for fault in checked.faults)


# -- and a reader who stops at the headline still sees it -------------------


def test_the_summary_carries_the_width_beside_the_percentage() -> None:
    one = artefact(answered_source_units=40, traceable_characters=10, characters=10)
    manifest = Manifest(kind="sync", musubi_version="0", artefacts=(one,))
    assert "100.0% traceable" in manifest.summary()
    assert "4.00 answer width" in manifest.summary()


def test_a_mixed_summary_says_nothing_rather_than_something_wrong() -> None:
    text = artefact(unit_key="a.md", answered_source_units=10, source_unit=CHARACTERS)
    pdf = artefact(unit_key="b.pdf", answered_source_units=3, source_unit=OPAQUE)
    manifest = Manifest(kind="sync", musubi_version="0", artefacts=(text, pdf))
    assert "answer width" not in manifest.summary()
    assert "traceable" in manifest.summary()


def test_the_report_prints_it_under_the_percentage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "vault"
    root.mkdir()
    (root / "gear.md").write_text(NOTE, encoding="utf-8")
    assert main(["sync", str(root), "--into", str(tmp_path / "corpus")]) == 0

    out = capsys.readouterr().out
    assert "characters traceable" in out
    assert "answer width" in out
    assert "source characters" in out, "the unit is named rather than assumed"


def test_the_report_says_when_there_is_no_such_number(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from musubi.interfaces.cli.main import _answer_width

    _answer_width(
        Coverage(
            units_read=2,
            emitted=2,
            skipped=0,
            characters=20,
            traceable_characters=20,
            answered_source_units=13,
            source_units=(CHARACTERS, OPAQUE),
        )
    )
    out = capsys.readouterr().out
    assert "no single number" in out
    assert CHARACTERS in out and OPAQUE in out


def test_a_manifest_read_back_without_the_fields_still_parses(tmp_path: Path) -> None:
    """A manifest written before these fields omits them, and a run reading one
    should carry on rather than refuse: absent is not wrong."""
    from musubi.infrastructure.emitters.documents import _artefact_from

    body = json.loads(render(Manifest(kind="sync", musubi_version="0", artefacts=(artefact(),))))
    (entry,) = body["artefacts"]
    del entry["source_unit"]
    del entry["answered_source_units"]

    read = _artefact_from(entry)
    assert read is not None
    assert read.source_unit == CHARACTERS
    assert read.answered_source_units == 0
    # Not 0.0. A width of zero claims that a character resolves to no source at
    # all, which no real map can produce -- and inventing a number for an
    # absent one is the shape #81 was filed about.
    assert read.answer_width is None
