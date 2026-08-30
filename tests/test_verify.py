"""`musubi verify`: the checks that run against a folder rather than a run.

Every other test in this suite builds a corpus and checks it in one breath, so
the files have had no opportunity to change. These damage a corpus after it was
written and ask whether the damage is found -- which is the only way to measure
a command whose whole purpose is the gap between writing and reading.

The checks here are deliberately a second implementation. `tests/test_invariants`
asserts the same properties with its own arithmetic; if these tests asserted on
`verify`'s output instead, one mistake in `verify` would make both agree.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from musubi.application.verify import verify
from musubi.errors import ContractError
from musubi.infrastructure.corpus import Corpus
from musubi.interfaces.cli.main import main


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MUSUBI_INTO", raising=False)


def built(tmp_path: Path, files: dict[str, str] | None = None) -> Path:
    """A corpus, written by a real sync, ready to be damaged."""
    root, into = tmp_path / "vault", tmp_path / "synced"
    for name, body in (files or {"a.md": "# a\n", "notes/b.md": "# b\nsee it\n"}).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8", newline="\n")
    root.mkdir(parents=True, exist_ok=True)
    with redirect_stdout(io.StringIO()):
        main(["sync", str(root), "--into", str(into)])
    return into


def manifest_of(into: Path) -> dict:
    return json.loads((into / "manifest.json").read_text(encoding="utf-8"))


def rewrite(into: Path, body: dict) -> None:
    (into / "manifest.json").write_text(
        json.dumps(body, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def invariants(into: Path) -> list[str]:
    return [fault.invariant for fault in verify(Corpus(into)).faults]


# -- the corpus as musubi wrote it ------------------------------------------


def test_a_corpus_as_written_holds(tmp_path: Path) -> None:
    checked = verify(Corpus(built(tmp_path)))
    assert checked.holds
    assert checked.artefacts == 2
    assert checked.faults == ()


def test_it_says_how_much_it_looked_at(tmp_path: Path) -> None:
    """A report of no faults is worth what the number of checks behind it is
    worth. Zero checks and zero faults reads exactly like a corpus that holds."""
    checked = verify(Corpus(built(tmp_path)))
    assert checked.checks == 5
    assert "5 checks" in checked.summary()


# -- damage done after the run ----------------------------------------------


def test_a_document_edited_underneath_the_manifest_is_found(tmp_path: Path) -> None:
    """The check no test in this suite can make for itself: the file on disk is
    not the file that was written."""
    into = built(tmp_path)
    document = into / "documents" / "a.md"
    document.write_text(
        document.read_text(encoding="utf-8") + "an edit nobody recorded\n",
        encoding="utf-8",
        newline="\n",
    )
    assert "content" in invariants(into)


def test_a_document_the_manifest_names_and_disk_does_not_have(tmp_path: Path) -> None:
    into = built(tmp_path)
    (into / "documents" / "a.md").unlink()
    assert "manifest 4" in invariants(into)


def test_coverage_that_stopped_agreeing_with_the_artefacts(tmp_path: Path) -> None:
    into = built(tmp_path)
    body = manifest_of(into)
    body["coverage"]["characters"] += 7
    rewrite(into, body)
    assert "manifest 2" in invariants(into)


def test_a_run_id_that_no_longer_derives_from_its_inputs(tmp_path: Path) -> None:
    """Re-derived from the manifest's own fields, not by rebuilding the
    producer's object: an id that only re-derives through the code that wrote it
    has not been shown to be re-derivable by anybody else."""
    into = built(tmp_path)
    body = manifest_of(into)
    body["converters"] = [*body["converters"], "invented@1"]
    rewrite(into, body)
    assert "manifest 1" in invariants(into)


def test_a_removal_about_a_unit_no_artefact_came_from(tmp_path: Path) -> None:
    into = built(tmp_path, {"a.md": "# a\nhttps://x.test/p?utm_source=z\n"})
    body = manifest_of(into)
    assert body["removals"], "this fixture is supposed to produce a removal"
    body["removals"][0]["unit_key"] = "a-note-that-was-never-read.md"
    rewrite(into, body)
    assert "manifest 3" in invariants(into)


def test_a_map_that_is_not_where_the_layout_puts_it(tmp_path: Path) -> None:
    into = built(tmp_path)
    body = manifest_of(into)
    body["artefacts"][0]["trace_map"] = "traces/somewhere-else.json"
    rewrite(into, body)
    assert "manifest 4" in invariants(into)


def test_a_map_about_a_different_unit(tmp_path: Path) -> None:
    into = built(tmp_path)
    body = manifest_of(into)
    body["artefacts"][0]["source"]["unit_key"] = "not-the-one-the-map-names.md"
    rewrite(into, body)
    faults = invariants(into)
    assert "manifest 4" in faults


def test_a_trace_map_that_stopped_tiling_its_document(tmp_path: Path) -> None:
    into = built(tmp_path)
    trace = into / "traces" / "a.md.json"
    body = json.loads(trace.read_text(encoding="utf-8"))
    body["segments"] = body["segments"][:-1]
    trace.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8", newline="\n")
    assert "trace 1" in invariants(into)


# -- refusing rather than reporting nothing ---------------------------------


def test_a_destination_with_no_manifest_is_refused(tmp_path: Path) -> None:
    """Not zero faults. There is nothing to check anything against, and a report
    saying the corpus holds would be true and dishonest."""
    empty = tmp_path / "not-a-corpus"
    empty.mkdir()
    with pytest.raises(ContractError) as raised:
        verify(Corpus(empty))
    assert "manifest.json" in str(raised.value)


# -- the command ------------------------------------------------------------


def test_the_command_exits_zero_on_a_corpus_that_holds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    into = built(tmp_path)
    capsys.readouterr()
    assert main(["verify", str(into)]) == 0
    assert "all hold" in capsys.readouterr().out


def test_the_command_exits_one_and_names_each_fault(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    into = built(tmp_path)
    document = into / "documents" / "a.md"
    document.write_text("something else entirely\n", encoding="utf-8", newline="\n")
    capsys.readouterr()

    assert main(["verify", str(into)]) == 1
    out = capsys.readouterr().out
    assert "Did not hold" in out
    assert "content" in out
    assert "docs/contracts.md" in out


def test_the_json_form_is_a_document(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    into = built(tmp_path)
    document = into / "documents" / "a.md"
    document.write_text("something else entirely\n", encoding="utf-8", newline="\n")
    capsys.readouterr()

    main(["verify", str(into), "--json"])
    body = json.loads(capsys.readouterr().out)

    assert body["holds"] is False
    assert body["artefacts"] == 2
    assert {fault["invariant"] for fault in body["faults"]} >= {"content"}
    assert all({"invariant", "subject", "detail"} <= set(f) for f in body["faults"])
