"""Two places a corpus's account of itself was short.

Both came from the `sora` orchestrator's second round
(`musubi-work/01_sora_round2.md`).

**What a crash leaves behind (R8.3).** It asked whether a `sync` killed part
way is always recovered by the next one, reading the design as *the manifest
lands last, so a killed corpus is wholly old*. It is not: a run that promoted
its manifest and died before finishing its withdrawal leaves the deleted
document on the disk and out of the manifest, where no later run would ever
look at it again. Measured before it was fixed.

**What a document is called (R7).** The manifest named an artefact by its path,
`feed/2026-09-05/a1b2.html`, which is not a name to put on a screen. Without a
title the consumer opens every document and takes the first line -- the
manifest's job, done by somebody who cannot see the front matter.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from musubi import __version__
from musubi.application.pipeline import Settings
from musubi.application.pipeline import run as pipeline
from musubi.application.sync import sync, withdrawals
from musubi.application.verify import verify
from musubi.domain.frontmatter import title_of
from musubi.domain.manifest import Artefact, Manifest, chunks
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.corpus import Corpus
from musubi.infrastructure.emitters import DOCUMENTS, MANIFEST, STAGING, TRACES, DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import ObsidianSource


def settings(at: str = "t") -> Settings:
    return Settings(CORE, default_screener(), converter_for, __version__, created_at=at)


def vault(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for stale in root.rglob("*.md"):
        stale.unlink()
    for name, body in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def held(into: Path) -> list[str]:
    return sorted(p.relative_to(into).as_posix() for p in into.rglob("*") if p.is_file())


def crash_after_promoting(root: Path, into: Path, at: str) -> tuple[str, ...]:
    """A sync that promotes everything and dies before it withdraws.

    The real sequence out of `sync`, stopped one step early. Simulated at this
    seam rather than by killing a process, because the seam is where the
    interruption matters and a killed process cannot be aimed.
    """
    emitter = DocumentEmitter(into)
    before = emitter.previous()
    emitter.begin()
    outcome = pipeline(ObsidianSource(root), settings(at), emitter, write=True, previous=before)
    taken = withdrawals(before.written | before.withdrawn, outcome.manifest)
    emitter.stage_manifest(chunks(replace(outcome.manifest, withdrawn=taken)))
    emitter.promote()
    return taken


# -- what a crash leaves behind ---------------------------------------------


def test_a_withdrawal_interrupted_after_the_manifest_landed_is_finished_next_run(
    tmp_path: Path,
) -> None:
    """The finding. Before this, the deleted document stayed for ever.

    The new manifest does not list it, so `withdrawals` -- which compares the
    previous manifest against the new one -- had nothing to compare it to. It
    was invisible to `musubi export`, indexed by anything walking the folder,
    and no later run would ever consider it again: a corpus answering questions
    from a note its owner deleted, which is the failure withdrawal exists to
    prevent.
    """
    root = vault(tmp_path / "vault", {"keep.md": "x\n", "gone.md": "y\n"})
    into = tmp_path / "corpus"
    sync(ObsidianSource(root), settings("t1"), DocumentEmitter(into))

    vault(root, {"keep.md": "x\n"})
    taken = crash_after_promoting(root, into, "t2")
    assert taken == ("documents/gone.md", "traces/gone.md.json")
    assert "documents/gone.md" in held(into), "the crash left it on the disk"

    finished = sync(ObsidianSource(root), settings("t3"), DocumentEmitter(into))

    assert finished.withdrawn == taken, "the next run finished what the last one started"
    assert "documents/gone.md" not in held(into)
    assert "traces/gone.md.json" not in held(into)
    assert (into / DOCUMENTS / "keep.md").is_file()


def test_the_manifest_is_what_carries_the_unfinished_withdrawal(tmp_path: Path) -> None:
    """It was already recorded and nobody read it. `withdrawn` is written into
    the manifest *before* the promotion, so the intent survives the crash that
    interrupted the act -- the recovery is reading a field that was there."""
    root = vault(tmp_path / "vault", {"keep.md": "x\n", "gone.md": "y\n"})
    into = tmp_path / "corpus"
    sync(ObsidianSource(root), settings("t1"), DocumentEmitter(into))
    vault(root, {"keep.md": "x\n"})
    crash_after_promoting(root, into, "t2")

    body = json.loads((into / MANIFEST).read_text(encoding="utf-8"))
    assert body["withdrawn"] == ["documents/gone.md", "traces/gone.md.json"]
    assert DocumentEmitter(into).previous().withdrawn == frozenset(body["withdrawn"])


def test_a_crash_while_staging_leaves_the_corpus_as_it_was(tmp_path: Path) -> None:
    """The other kill point, and the one that was always safe: nothing is in
    the destination until `promote`, and the next `begin()` clears the staging
    area rather than promoting a mixture of two runs."""
    root = vault(tmp_path / "vault", {"a.md": "first\n"})
    into = tmp_path / "corpus"
    sync(ObsidianSource(root), settings("t1"), DocumentEmitter(into))
    before = held(into)

    vault(root, {"a.md": "second\n"})
    emitter = DocumentEmitter(into)
    emitter.begin()
    pipeline(ObsidianSource(root), settings("t2"), emitter, write=True)
    # and stop, with the staging area full.

    assert (into / STAGING).exists()
    assert "first" in (into / DOCUMENTS / "a.md").read_text(encoding="utf-8")

    sync(ObsidianSource(root), settings("t3"), DocumentEmitter(into))
    assert held(into) == before
    assert "second" in (into / DOCUMENTS / "a.md").read_text(encoding="utf-8")
    assert not (into / STAGING).exists()


# -- a corpus larger than its own account -----------------------------------


def test_verify_reports_a_document_the_manifest_does_not_name(tmp_path: Path) -> None:
    """The only check that can see a corpus *larger* than its account. Every
    other one asks whether what the manifest names is here."""
    root = vault(tmp_path / "vault", {"a.md": "x\n"})
    into = tmp_path / "corpus"
    sync(ObsidianSource(root), settings("t1"), DocumentEmitter(into))
    assert verify(Corpus(into)).holds

    (into / DOCUMENTS / "dropped.md").write_text("somebody put this here\n", encoding="utf-8")

    checked = verify(Corpus(into))
    assert not checked.holds
    (fault,) = [f for f in checked.faults if f.invariant == "manifest 6"]
    assert fault.subject == "documents/dropped.md"


def test_the_staging_area_is_not_an_orphan(tmp_path: Path) -> None:
    """It is musubi's own, and a run that died while staging leaves one for
    the next `begin()` to clear. Reporting it as a fault would make an
    interrupted run look like a corrupted corpus."""
    root = vault(tmp_path / "vault", {"a.md": "x\n"})
    into = tmp_path / "corpus"
    sync(ObsidianSource(root), settings("t1"), DocumentEmitter(into))
    (into / STAGING / DOCUMENTS).mkdir(parents=True)
    (into / STAGING / DOCUMENTS / "half.md").write_text("partial\n", encoding="utf-8")

    assert verify(Corpus(into)).holds


def test_the_orphan_check_sees_a_stray_map_too(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"a.md": "x\n"})
    into = tmp_path / "corpus"
    sync(ObsidianSource(root), settings("t1"), DocumentEmitter(into))
    (into / TRACES / "ghost.md.json").write_text("{}", encoding="utf-8")

    assert any(f.subject == "traces/ghost.md.json" for f in verify(Corpus(into)).faults)


# -- what a document is called ----------------------------------------------


def test_the_front_matter_title_wins() -> None:
    assert title_of("---\ntitle: The gear list\n---\n\n# A heading\n") == "The gear list"


def test_the_first_heading_is_used_when_the_front_matter_says_nothing() -> None:
    assert title_of("---\nlayer: fact\n---\n\n## テント設計メモ\n\nbody\n") == "テント設計メモ"
    assert title_of("# Just a heading\n\nbody\n") == "Just a heading"


def test_a_document_that_says_nothing_has_no_title() -> None:
    assert title_of("just prose, no heading\n") is None
    assert title_of("") is None


def test_a_stated_empty_title_is_not_the_same_answer_as_saying_nothing() -> None:
    """A document that states `title:` with nothing after it has said
    something; one that says nothing has not. A consumer that cannot tell them
    apart falls back for the wrong one.

    **That was this test's docstring while its assertions made both `None`.**
    `docs/contracts.md` tells consumers the two are different answers and must
    not be collapsed, and `sora` wrote the branch for it -- for a value musubi
    had never once produced ([ADR-0051]).
    """
    assert title_of("---\ntitle:\n---\n\n# A heading\n") == ""
    assert title_of("---\ntitle:   \n---\n") == ""
    assert title_of("---\ntitle: ''\n---\n") == ""
    assert title_of("just prose\n") is None, "and saying nothing is still None"


def test_a_title_the_author_had_to_quote_arrives_unquoted() -> None:
    """**YAML requires quoting for a value containing a colon**, so a note
    called `gear: a list` can only be written `title: "gear: a list"`. The
    quotes came through into the manifest and onto whatever screen showed it.
    """
    assert title_of('---\ntitle: "A name"\n---\n') == "A name"
    assert title_of("---\ntitle: 'A name'\n---\n") == "A name"
    assert title_of('---\ntitle: "gear: a list"\n---\n') == "gear: a list"


def test_an_unterminated_quote_is_repeated_rather_than_guessed_at() -> None:
    """This is not a YAML parser and does not become one. Repeating what the
    author wrote is the same standing every other front-matter value has."""
    assert title_of('---\ntitle: "unclosed\n---\n') == '"unclosed'
    assert title_of('---\ntitle: say "this"\n---\n') == 'say "this"'


def test_a_heading_needs_something_after_the_hashes() -> None:
    assert title_of("#\n\nbody\n") is None
    assert title_of("#hashtag not a heading\n") is None


def test_the_manifest_carries_the_title_and_null_where_there_is_none(tmp_path: Path) -> None:
    root = vault(
        tmp_path / "vault",
        {
            "gear.md": "# テント設計メモ\n\nbody\n",
            "named.md": "---\ntitle: Stated\n---\n\n# Other\n",
        },
    )
    (root / "plain.txt").write_text("no heading here\n", encoding="utf-8")
    into = tmp_path / "corpus"
    sync(ObsidianSource(root), settings("t1"), DocumentEmitter(into))

    body = json.loads((into / MANIFEST).read_text(encoding="utf-8"))
    titles = {a["source"]["unit_key"]: a["title"] for a in body["artefacts"]}
    assert titles == {"gear.md": "テント設計メモ", "named.md": "Stated", "plain.txt": None}
    assert '"title": null' in (into / MANIFEST).read_text(encoding="utf-8")


def test_the_title_is_not_in_the_run_id() -> None:
    """It is derived from the artefact's own text, which `content_hash` already
    covers. In the id it would change every corpus on upgrade."""
    base = Artefact(
        path="documents/a.md",
        content_hash="sha256:" + "0" * 64,
        trace_path="traces/a.md.json",
        source_id="vault",
        unit_key="a.md",
        converter="markdown@1",
        traceable_characters=1,
        characters=1,
        layer="fact",
    )
    one = Manifest(kind="sync", musubi_version="0", artefacts=(base,))
    named = Manifest(kind="sync", musubi_version="0", artefacts=(replace(base, title="A name"),))
    assert one.run_id == named.run_id


def test_a_manifest_written_before_the_field_reads_back_as_none(tmp_path: Path) -> None:
    from musubi.infrastructure.emitters.documents import _artefact_from

    root = vault(tmp_path / "vault", {"gear.md": "# A name\n"})
    into = tmp_path / "corpus"
    sync(ObsidianSource(root), settings("t1"), DocumentEmitter(into))
    (entry,) = json.loads((into / MANIFEST).read_text(encoding="utf-8"))["artefacts"]
    assert entry["title"] == "A name"

    del entry["title"]
    read = _artefact_from(entry)
    assert read is not None and read.title is None
