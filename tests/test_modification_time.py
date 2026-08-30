"""The one fact the filesystem carries about a note, and musubi used to drop.

`kiseki-notes` reads a document's mtime as the day the note was written. musubi
wrote new files, so every note in a corpus carried the conversion date and a
decade of history became one afternoon -- with musubi reporting success, the
manifest correct, and `musubi verify` passing. Neither side could see it: the
result is a consistent corpus in which every note happens to share a date.
"""

from __future__ import annotations

import contextlib
import datetime
import io
import os
import time
from pathlib import Path

import pytest

from musubi.interfaces.cli.main import main


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MUSUBI_INTO", raising=False)


#: Days ago, so the fixture is a vault with a history rather than a folder.
WRITTEN = {"old.md": 400, "middle.md": 250, "recent.md": 30}


def vault(root: Path) -> dict[str, float]:
    root.mkdir(parents=True, exist_ok=True)
    stamps = {}
    for name, ago in WRITTEN.items():
        path = root / name
        path.write_text(f"# {name}\n", encoding="utf-8", newline="\n")
        stamp = time.time() - ago * 86400
        os.utime(path, (stamp, stamp))
        stamps[name] = stamp
    return stamps


def synced(root: Path, into: Path) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        main(["sync", str(root), "--into", str(into)])


def day(path: Path) -> str:
    return datetime.date.fromtimestamp(path.stat().st_mtime).isoformat()


def test_a_note_keeps_the_day_it_was_written(tmp_path: Path) -> None:
    stamps = vault(tmp_path / "vault")
    into = tmp_path / "synced"
    synced(tmp_path / "vault", into)

    for name, stamp in stamps.items():
        written = (into / "documents" / name).stat().st_mtime
        assert written == pytest.approx(stamp, abs=2), f"{name} did not keep its timestamp"


def test_the_corpus_has_as_many_days_as_the_vault(tmp_path: Path) -> None:
    """The failure this exists for is not one wrong date. It is every date
    becoming the same one, which reads as a corpus rather than as damage."""
    root, into = tmp_path / "vault", tmp_path / "synced"
    vault(root)
    synced(root, into)

    source_days = {day(p) for p in root.glob("*.md")}
    corpus_days = {day(p) for p in (into / "documents").glob("*.md")}

    assert len(source_days) == 3
    assert corpus_days == source_days


def test_musubis_own_records_carry_the_runs_time(tmp_path: Path) -> None:
    """The map and the manifest are musubi's account of a run, not documents
    somebody wrote. Backdating them would be a claim about when the run
    happened, which is a different and false one."""
    root, into = tmp_path / "vault", tmp_path / "synced"
    vault(root)
    synced(root, into)

    now = datetime.date.today().isoformat()
    assert day(into / "manifest.json") == now
    assert day(into / "traces" / "old.md.json") == now
    assert day(into / "documents" / "old.md") != now


def test_the_timestamp_does_not_reach_the_content(tmp_path: Path) -> None:
    """ADR-0006 and the front matter's own reasoning: an artefact whose content
    depended on a modification time would be rewritten by a re-sync that changed
    nothing, and the corpus's hashes would depend on when it was built."""
    root, into = tmp_path / "vault", tmp_path / "synced"
    vault(root)
    synced(root, into)
    first = (into / "documents" / "old.md").read_text(encoding="utf-8")

    moved = time.time() - 5 * 86400
    os.utime(root / "old.md", (moved, moved))
    synced(root, into)
    second = (into / "documents" / "old.md").read_text(encoding="utf-8")

    assert first == second, "a modification time reached the artefact's content"
    assert "observed_at" not in second
    assert (into / "documents" / "old.md").stat().st_mtime == pytest.approx(moved, abs=2)


def test_a_re_sync_of_an_unchanged_vault_still_writes_the_same_bytes(tmp_path: Path) -> None:
    root, into = tmp_path / "vault", tmp_path / "synced"
    vault(root)
    synced(root, into)
    before = {p.name: p.read_bytes() for p in (into / "documents").glob("*.md")}

    synced(root, into)
    after = {p.name: p.read_bytes() for p in (into / "documents").glob("*.md")}

    assert before == after


def test_a_source_that_does_not_know_is_left_alone(tmp_path: Path) -> None:
    """``modified_at`` is ``None`` from a source with no timestamp to offer, and
    the written file then keeps the run's time rather than being given a
    guess."""
    from musubi.ports.emitter import Document
    from musubi.ports.source import Found

    assert Found(("a.md",), "text/markdown", 3, "a.md").modified_at is None
    assert Document.__dataclass_fields__["modified_at"].default is None
