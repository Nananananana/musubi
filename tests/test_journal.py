"""The corpus's history, and the two things it must never get wrong.

A journal is trusted in exactly the situation where nobody can check it by
looking: a document in the corpus is being questioned, months later, and the
question is when it arrived and which run put it there. So the tests here are
mostly about the ways a history can be quietly wrong rather than absent --

  * a fold that loses a change,
  * an id that names two different runs,
  * a line appended for a run that then refused,
  * a file that drifts from the corpus beside it and nothing compares them.

The last one is why `verify` grew a journal check. A history nothing verifies
against the corpus is a log, and a log can be wrong for a year.
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from musubi import __version__
from musubi.application.pipeline import Settings, run
from musubi.application.sync import sync
from musubi.application.verify import verify
from musubi.domain.journal import (
    CONTRACT,
    Change,
    Entry,
    attribution,
    changes,
    entry_from,
    folded,
    run_named,
    touching,
)
from musubi.domain.manifest import render
from musubi.errors import ContractError, CredentialFoundError
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.corpus import Corpus
from musubi.infrastructure.emitters import DocumentEmitter
from musubi.infrastructure.emitters.documents import JOURNAL
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import ObsidianSource

PATHS = st.text(st.characters(codec="utf-8", min_codepoint=32), min_size=1, max_size=12)
HASHES = st.sampled_from(["a", "b", "c"])
CORPORA = st.dictionaries(PATHS, HASHES, max_size=6)


def settings() -> Settings:
    return Settings(
        ruleset=CORE,
        screener=default_screener(),
        converter_for=converter_for,
        musubi_version=__version__,
        created_at="2026-09-05T00:00:00+00:00",
    )


def synced(root: Path, destination: Path, *, at: str = "") -> None:
    """One real sync, through the application service that appends the entry."""
    chosen = settings()
    if at:
        chosen = Settings(
            ruleset=chosen.ruleset,
            screener=chosen.screener,
            converter_for=chosen.converter_for,
            musubi_version=chosen.musubi_version,
            created_at=at,
        )
    sync(ObsidianSource(root), chosen, DocumentEmitter(destination))


def entry(run_id: str, parent: str | None, change: Change, *, at: str = "t") -> Entry:
    return Entry(
        run_id=run_id,
        parent=parent,
        created_at=at,
        musubi_version="0",
        kind="sync",
        change=change,
    )


# -- what one run did -------------------------------------------------------


@given(before=CORPORA, after=CORPORA)
def test_a_change_partitions_the_two_corpora(before: dict[str, str], after: dict[str, str]) -> None:
    """Every path in either corpus is accounted for exactly once.

    The property a diff has to have before any of the rest is worth anything:
    a path that is in neither list and not counted has silently vanished from
    the history.
    """
    change = changes(before, after)
    named = set(change.added) | set(change.changed) | set(change.removed)

    assert named <= set(before) | set(after)
    assert len(named) + change.unchanged == len(set(before) | set(after))
    assert set(change.added) == set(after) - set(before)
    assert set(change.removed) == set(before) - set(after)


@given(corpus=CORPORA)
def test_a_corpus_against_itself_changed_nothing(corpus: dict[str, str]) -> None:
    change = changes(corpus, corpus)
    assert change.is_empty
    assert change.unchanged == len(corpus)
    assert change.total == len(corpus)


@given(before=CORPORA, after=CORPORA)
def test_the_lists_are_sorted(before: dict[str, str], after: dict[str, str]) -> None:
    """[ADR-0003] wants two runs over the same inputs to write the same bytes,
    and a journal line is bytes."""
    change = changes(before, after)
    for names in (change.added, change.changed, change.removed):
        assert list(names) == sorted(names)


# -- what a range of runs did -----------------------------------------------


@given(corpora=st.lists(CORPORA, min_size=1, max_size=6))
def test_folding_a_history_is_comparing_its_ends(corpora: list[dict[str, str]]) -> None:
    """`musubi diff` over a range says exactly what `changes()` says end to end.

    **Plain equality, with no exception named.** The first version of this
    asserted equality *except* for a path that was removed and added back with
    identical content, which the fold could only call `changed` -- it had the
    verbs and not the bytes. [ADR-0035] carried the hashes and the exception
    went away, so the test says so: an allowance kept after the reason for it
    is gone is an allowance that hides the next regression.
    """
    entries = []
    parent = None
    for index, (before, after) in enumerate(pairwise(corpora)):
        run_id = f"run-{index}"
        entries.append(entry(run_id, parent, changes(before, after)))
        parent = run_id

    fold = folded(entries)
    direct = changes(corpora[0], corpora[-1])

    assert fold.added == direct.added
    assert fold.changed == direct.changed
    assert fold.removed == direct.removed
    assert fold.exact


def test_added_then_removed_cancels() -> None:
    fold = folded(
        [
            entry("a", None, Change(added=("x",), changed=(), removed=(), unchanged=1)),
            entry("b", "a", Change(added=(), changed=(), removed=("x",), unchanged=1)),
        ]
    )
    assert fold.is_empty


def test_added_then_changed_is_still_added() -> None:
    """The corpus did not have it before the range and has it after. Calling
    that *changed* would tell a reader to look for an earlier version."""
    fold = folded(
        [
            entry("a", None, Change(added=("x",), changed=(), removed=(), unchanged=0)),
            entry("b", "a", Change(added=(), changed=("x",), removed=(), unchanged=0)),
        ]
    )
    assert fold.added == ("x",)
    assert not fold.changed


def test_removed_then_added_with_the_same_bytes_is_no_change_at_all() -> None:
    """What [ADR-0035] bought, stated as the smallest case.

    A document deleted on Monday and restored on Tuesday from a backup: the
    corpus on Wednesday is the corpus of Sunday, and a reader asking what
    changed over the week should be told nothing did.
    """
    fold = folded(
        [
            entry("a", None, Change((), (), ("x",), 0, previous=(("x", "h1"),))),
            entry("b", "a", Change(("x",), (), (), 0, hashes=(("x", "h1"),))),
        ]
    )
    assert fold.is_empty
    assert fold.exact


def test_removed_then_added_with_different_bytes_is_changed() -> None:
    fold = folded(
        [
            entry("a", None, Change((), (), ("x",), 0, previous=(("x", "h1"),))),
            entry("b", "a", Change(("x",), (), (), 0, hashes=(("x", "h2"),))),
        ]
    )
    assert fold.changed == ("x",)
    assert not fold.added and not fold.removed


def test_a_range_containing_an_unhashed_line_falls_back_and_says_so() -> None:
    """A journal that spans [ADR-0035] has lines of both kinds.

    The conservative answer *and* the flag. Either alone is worse than both:
    the answer without the flag is a guess presented as a fact, and the flag
    without the answer is a refusal where something useful could be said.
    """
    fold = folded(
        [
            entry("a", None, Change((), (), ("x",), 0)),
            entry("b", "a", Change(("x",), (), (), 0)),
        ]
    )
    assert fold.changed == ("x",)
    assert not fold.exact


def test_folding_nothing_says_nothing() -> None:
    assert folded([]).is_empty


# -- a rename, which a journal of paths alone cannot see -------------------


def test_a_path_that_left_and_a_path_that_arrived_holding_the_same_bytes_is_a_move() -> None:
    change = changes({"old.md": "hA", "k.md": "hK"}, {"new.md": "hA", "k.md": "hK"})
    assert change.moves == (("old.md", "new.md"),)
    # And the lists still say what the corpus did, because that is what it did.
    assert change.added == ("new.md",)
    assert change.removed == ("old.md",)


def test_a_move_is_counted_once_in_the_headline() -> None:
    """*1 added, 1 removed* is two events, neither of which happened."""
    change = changes({"old.md": "hA"}, {"new.md": "hA"})
    assert change.summary() == "1 moved, 0 unchanged"


def test_two_files_with_the_same_content_are_not_evidence_about_which_became_which() -> None:
    """The pairing rule, and the reason for it.

    Two empty notes, or a stub copied twice. Guessing a pair would put a
    confident wrong answer exactly where an honest silence belongs, and the
    reader would have no way to tell it from a real one.
    """
    change = changes({"a.md": "h", "b.md": "h"}, {"c.md": "h", "d.md": "h"})
    assert change.moves == ()
    assert change.added == ("c.md", "d.md")
    assert change.removed == ("a.md", "b.md")


def test_a_move_needs_hashes_and_says_nothing_without_them() -> None:
    assert Change(added=("new.md",), changed=(), removed=("old.md",), unchanged=0).moves == ()


def test_a_rename_in_a_real_vault_reads_as_a_move(tmp_path: Path) -> None:
    vault = tmp_path / "notes"
    vault.mkdir()
    (vault / "stove.md").write_text("# stove\n\nalcohol\n", encoding="utf-8")
    destination = tmp_path / "synced"
    synced(vault, destination, at="2026-09-05T00:00:00+00:00")

    (vault / "stove.md").rename(vault / "cooking.md")
    synced(vault, destination, at="2026-09-05T00:00:01+00:00")

    last = Corpus(destination).journal()[-1]
    assert last.change.moves == (("documents/stove.md", "documents/cooking.md"),)


# -- one document's part of the history --------------------------------------


def test_touching_gives_one_documents_history(tmp_path: Path) -> None:
    vault = tmp_path / "notes"
    vault.mkdir()
    (vault / "gear.md").write_text("# gear\n", encoding="utf-8")
    (vault / "stove.md").write_text("# stove\n", encoding="utf-8")
    destination = tmp_path / "synced"
    synced(vault, destination, at="2026-09-05T00:00:00+00:00")

    (vault / "gear.md").write_text("# gear\n\nedited\n", encoding="utf-8")
    synced(vault, destination, at="2026-09-05T00:00:01+00:00")
    (vault / "stove.md").write_text("# stove\n\nedited\n", encoding="utf-8")
    synced(vault, destination, at="2026-09-05T00:00:02+00:00")

    entries = Corpus(destination).journal()
    gear = touching(entries, "documents/gear.md")
    assert [one.created_at for one in gear] == [
        "2026-09-05T00:00:00+00:00",
        "2026-09-05T00:00:01+00:00",
    ]


def test_a_removal_is_part_of_a_documents_history() -> None:
    """The one event that explains why the corpus does not hold something a
    reader expected. Leaving it out makes a deleted document look like one
    that was never there."""
    entries = [
        entry("a", None, Change(("x",), (), (), 0)),
        entry("b", "a", Change((), (), ("x",), 0)),
    ]
    assert touching(entries, "x") == tuple(entries)


# -- which run put this document here ---------------------------------------


def test_attribution_names_the_run_that_added_and_the_run_that_last_changed() -> None:
    first = entry("a", None, Change(("x",), (), (), 0), at="1")
    second = entry("b", "a", Change((), ("x",), (), 0), at="2")
    third = entry("c", "b", Change((), ("x",), (), 0), at="3")

    (one,) = attribution([first, second, third], ["x"])
    assert one.first_seen is first
    assert one.last_touched is third
    assert one.revisions == 2
    assert one.is_answered


def test_attribution_abstains_for_an_artefact_the_history_never_saw() -> None:
    """The answer that matters most, and the one a report is tempted to drop.

    Attributing an artefact to the oldest run it happens to sit beside would
    be a confident wrong answer in the one place this library exists to prevent
    one -- and it would be invisible, because it would look exactly like a real
    answer.
    """
    (one,) = attribution([entry("a", None, Change(("x",), (), (), 0))], ["y"])
    assert one.first_seen is None
    assert one.last_touched is None
    assert not one.is_answered


def test_attribution_returns_every_path_it_was_asked_about() -> None:
    """Dropping the unanswerable ones would make the answer look complete when
    it is the corpus that is complete and the history that is short."""
    found = attribution([entry("a", None, Change(("x",), (), (), 0))], ["x", "y", "z"])
    assert [one.path for one in found] == ["x", "y", "z"]


def test_a_document_removed_and_added_again_is_attributed_to_the_run_that_put_it_back() -> None:
    """The artefact in the corpus now is the one that run put there. The
    earlier life is still in `musubi log --path`."""
    entries = [
        entry("a", None, Change(("x",), (), (), 0), at="1"),
        entry("b", "a", Change((), (), ("x",), 0), at="2"),
        entry("c", "b", Change(("x",), (), (), 0), at="3"),
    ]
    (one,) = attribution(entries, ["x"])
    assert one.first_seen is entries[2]
    assert one.revisions == 0


def test_blame_over_a_real_corpus(tmp_path: Path) -> None:
    vault = tmp_path / "notes"
    vault.mkdir()
    (vault / "gear.md").write_text("# gear\n", encoding="utf-8")
    destination = tmp_path / "synced"
    synced(vault, destination, at="2026-09-05T00:00:00+00:00")
    (vault / "gear.md").write_text("# gear\n\nedited\n", encoding="utf-8")
    synced(vault, destination, at="2026-09-05T00:00:01+00:00")

    entries = Corpus(destination).journal()
    (one,) = attribution(entries, ["documents/gear.md"])
    assert one.first_seen is not None and one.first_seen.created_at == "2026-09-05T00:00:00+00:00"
    assert one.last_touched is not None and one.last_touched.created_at == (
        "2026-09-05T00:00:01+00:00"
    )
    assert one.revisions == 1


# -- the join the hashes opened ---------------------------------------------


def test_verify_finds_a_corpus_whose_documents_the_history_does_not_recognise(
    tmp_path: Path,
) -> None:
    """`journal 3`. Two files now say what a document hashes to, and a
    duplicated fact nothing compares is a fact free to drift."""
    vault = tmp_path / "notes"
    vault.mkdir()
    (vault / "gear.md").write_text("# gear\n", encoding="utf-8")
    destination = tmp_path / "synced"
    synced(vault, destination)
    assert verify(Corpus(destination)).holds

    body = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    body["artefacts"][0]["content_hash"] = "sha256:" + "0" * 64
    (destination / "manifest.json").write_text(
        json.dumps(body, ensure_ascii=False), encoding="utf-8"
    )

    checked = verify(Corpus(destination))
    assert any(fault.invariant == "journal 3" for fault in checked.faults)


def test_a_history_without_hashes_does_not_fail_the_join(tmp_path: Path) -> None:
    """Absent is not the same as wrong. Treating it as wrong would fail every
    corpus written before [ADR-0035] the first time anybody verified one."""
    vault = tmp_path / "notes"
    vault.mkdir()
    (vault / "gear.md").write_text("# gear\n", encoding="utf-8")
    destination = tmp_path / "synced"
    synced(vault, destination)

    lines = []
    for line in (destination / JOURNAL).read_text(encoding="utf-8").splitlines():
        body = json.loads(line)
        body.pop("hashes", None)
        lines.append(json.dumps(body, ensure_ascii=False))
    (destination / JOURNAL).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    assert verify(Corpus(destination)).holds


# -- the id that had to exist -----------------------------------------------


def test_a_corpus_that_returns_to_a_previous_state_reuses_its_run_id() -> None:
    """The finding this module was rewritten for, kept as a test.

    Add a file, edit it, delete it: the corpus is byte-for-byte what it was
    three runs ago, and `run_id` is over the artefacts' content hashes
    ([ADR-0003]), so the third run has the first run's id. Three entries then
    answered to one short id and `--since` could not say which was meant.

    A run id is a **tree** id. It was never a commit id.
    """
    first = entry("corpus-1", None, Change((), (), (), 3), at="1")
    third = entry("corpus-1", "corpus-2", Change((), (), ("x",), 3), at="3")

    assert first.run_id == third.run_id
    assert first.entry_id != third.entry_id


def test_an_entry_id_covers_the_parent_and_the_time() -> None:
    base = entry("r", "p", Change((), (), (), 0), at="1")
    assert base.entry_id != entry("r", "p", Change((), (), (), 0), at="2").entry_id
    assert base.entry_id != entry("r", "q", Change((), (), (), 0), at="1").entry_id
    assert base.entry_id != entry("s", "p", Change((), (), (), 0), at="1").entry_id


def test_an_entry_id_does_not_cover_the_change() -> None:
    """Deliberate, and worth pinning: the change is *derived* from the two runs
    the entry already names. Hashing it too would let a line whose change list
    was rewritten still verify against a recomputed id, which is backwards --
    the point of the id is that it is fixed by the two corpus states."""
    one = entry("r", "p", Change(("x",), (), (), 0))
    other = entry("r", "p", Change((), (), ("y",), 9))
    assert one.entry_id == other.entry_id


def test_a_short_id_drops_the_algorithm_and_can_still_be_typed_back() -> None:
    entries = [entry(f"corpus-{n}", None, Change((), (), (), 0), at=str(n)) for n in range(4)]
    for index, one in enumerate(entries):
        assert not one.short.startswith("sha256")
        assert run_named(entries, one.short) == index
        assert run_named(entries, one.entry_id) == index


def test_an_ambiguous_prefix_is_an_error_and_not_the_first_match() -> None:
    # Two runs that genuinely are the same entry: the same corpus, the same
    # parent, the same instant. Different change lists, because the change is
    # derived and deliberately not part of the id.
    entries = [
        entry("r", "p", Change(("a",), (), (), 0)),
        entry("r", "p", Change((), (), ("b",), 0)),
    ]
    assert entries[0].entry_id == entries[1].entry_id
    with pytest.raises(LookupError, match="2 runs"):
        run_named(entries, entries[0].short)


def test_a_prefix_naming_nothing_is_an_error() -> None:
    with pytest.raises(LookupError, match="no run"):
        run_named([entry("r", None, Change((), (), (), 0))], "zzzz")


def test_a_run_whose_id_equals_its_parents_changed_nothing() -> None:
    assert entry("r", "r", Change((), (), (), 4)).names_nothing
    assert not entry("r", "q", Change((), (), (), 4)).names_nothing


# -- the line, written and read back ----------------------------------------


def test_a_line_round_trips() -> None:
    original = entry("r", "p", Change(("a",), ("b",), ("c",), 7), at="2026-09-05T00:00:00+00:00")
    assert entry_from(json.loads(json.dumps(original.document()))) == original


def test_a_line_naming_an_unknown_contract_is_refused() -> None:
    document = entry("r", None, Change((), (), (), 0)).document()
    document["contract"] = "musubi.run-journal/2"
    with pytest.raises(ValueError, match="does not recognise"):
        entry_from(document)


def test_a_line_whose_entry_id_disagrees_with_its_fields_is_refused() -> None:
    """The written id is a convenience for a reader with `jq`, and is checked
    rather than trusted. A file that can name a different run than its own
    fields describe is a history that can lie about which corpus it belongs
    to."""
    document = entry("r", None, Change((), (), (), 0)).document()
    document["run_id"] = "someone-elses-corpus"
    with pytest.raises(ValueError, match="One of the two was edited"):
        entry_from(document)


def test_the_contract_is_the_one_the_schema_publishes() -> None:
    from musubi.schemas import load

    assert load(CONTRACT)["properties"]["contract"]["pattern"].startswith("^musubi\\.run-journal/1")


def test_every_line_conforms_to_the_published_schema(tmp_path: Path) -> None:
    """Against real output, never a document assembled in a test."""
    from jsonschema import Draft202012Validator

    from musubi.schemas import load

    root = tmp_path / "vault"
    root.mkdir()
    (root / "one.md").write_text("first\n", encoding="utf-8")
    destination = tmp_path / "synced"

    synced(root, destination, at="2026-09-05T00:00:00+00:00")
    (root / "two.md").write_text("second\n", encoding="utf-8")
    synced(root, destination, at="2026-09-05T00:00:01+00:00")

    check = Draft202012Validator(load(CONTRACT))
    lines = (destination / JOURNAL).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        check.validate(json.loads(line))


# -- against a corpus a real run wrote --------------------------------------


def test_a_sync_appends_one_entry_naming_the_run_it_was(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "one.md").write_text("first\n", encoding="utf-8")
    destination = tmp_path / "synced"

    synced(root, destination)

    entries = Corpus(destination).journal()
    assert len(entries) == 1
    assert entries[0].parent is None
    assert (
        entries[0].run_id
        == json.loads((destination / "manifest.json").read_text(encoding="utf-8"))["run_id"]
    )
    assert entries[0].change.added == ("documents/one.md",)


def test_a_history_records_each_run_in_turn(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "one.md").write_text("first\n", encoding="utf-8")
    destination = tmp_path / "synced"

    synced(root, destination, at="2026-09-05T00:00:00+00:00")
    (root / "two.md").write_text("second\n", encoding="utf-8")
    synced(root, destination, at="2026-09-05T00:00:01+00:00")
    (root / "one.md").write_text("edited\n", encoding="utf-8")
    synced(root, destination, at="2026-09-05T00:00:02+00:00")
    (root / "two.md").unlink()
    synced(root, destination, at="2026-09-05T00:00:03+00:00")

    entries = Corpus(destination).journal()
    assert [e.change.added for e in entries] == [
        ("documents/one.md",),
        ("documents/two.md",),
        (),
        (),
    ]
    assert [e.change.changed for e in entries] == [(), (), ("documents/one.md",), ()]
    assert [e.change.removed for e in entries] == [(), (), (), ("documents/two.md",)]

    for older, newer in pairwise(entries):
        assert newer.parent == older.run_id


def test_a_re_sync_of_an_untouched_folder_writes_an_entry_that_says_so(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "one.md").write_text("first\n", encoding="utf-8")
    destination = tmp_path / "synced"

    synced(root, destination, at="2026-09-05T00:00:00+00:00")
    synced(root, destination, at="2026-09-05T00:00:01+00:00")

    entries = Corpus(destination).journal()
    assert entries[1].change.is_empty
    assert entries[1].names_nothing
    assert entries[1].change.unchanged == 1


def test_a_refused_run_appends_nothing(tmp_path: Path) -> None:
    """[ADR-0008] is fail-closed and the journal is inside that promise.

    An entry written for a run that then refused would be a history claiming a
    corpus that was never built -- and the journal is the one file a reader
    consults precisely when they cannot check by looking.
    """
    root = tmp_path / "vault"
    root.mkdir()
    (root / "one.md").write_text("first\n", encoding="utf-8")
    destination = tmp_path / "synced"
    synced(root, destination, at="2026-09-05T00:00:00+00:00")

    (root / "leak.md").write_text("AKIAIOSFODNN7EXAMPLE\n", encoding="utf-8")
    with pytest.raises(CredentialFoundError):
        synced(root, destination, at="2026-09-05T00:00:01+00:00")

    assert len(Corpus(destination).journal()) == 1


def test_a_corpus_with_no_journal_has_no_history_and_is_not_broken(tmp_path: Path) -> None:
    """A corpus written before this feature keeps none. Empty is the answer,
    not a fault -- the alternative makes every existing corpus invalid."""
    root = tmp_path / "vault"
    root.mkdir()
    (root / "one.md").write_text("first\n", encoding="utf-8")
    destination = tmp_path / "synced"

    emitter = DocumentEmitter(destination)
    emitter.begin()
    outcome = run(ObsidianSource(root), settings(), emitter, write=True)
    emitter.stage_manifest(render(outcome.manifest))
    emitter.promote()

    assert Corpus(destination).journal() == ()
    assert verify(Corpus(destination)).holds


def test_a_line_that_will_not_parse_is_a_refusal_and_not_a_shorter_history(
    tmp_path: Path,
) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "one.md").write_text("first\n", encoding="utf-8")
    destination = tmp_path / "synced"
    synced(root, destination)

    with (destination / JOURNAL).open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("{not json\n")

    with pytest.raises(ContractError, match="line 2"):
        Corpus(destination).journal()


# -- what verify now checks -------------------------------------------------


def test_verify_finds_a_corpus_and_a_history_that_have_come_apart(tmp_path: Path) -> None:
    """The check that makes the file worth trusting.

    Without it the journal is a log: written beside the corpus, compared
    against nothing, free to drift for a year before anybody notices.
    """
    root = tmp_path / "vault"
    root.mkdir()
    (root / "one.md").write_text("first\n", encoding="utf-8")
    destination = tmp_path / "synced"
    synced(root, destination, at="2026-09-05T00:00:00+00:00")
    (root / "two.md").write_text("second\n", encoding="utf-8")
    synced(root, destination, at="2026-09-05T00:00:01+00:00")

    assert verify(Corpus(destination)).holds

    # The corpus moved on and the history did not: somebody restored the
    # journal from a backup, or ran a musubi old enough not to append.
    lines = (destination / JOURNAL).read_text(encoding="utf-8").splitlines()
    (destination / JOURNAL).write_text(lines[0] + "\n", encoding="utf-8", newline="\n")

    checked = verify(Corpus(destination))
    assert not checked.holds
    assert any(fault.invariant == "journal 1" for fault in checked.faults)


def test_verify_finds_a_break_in_the_chain(tmp_path: Path) -> None:
    """A lost line matters more here than it looks. `musubi diff` folds a range
    of entries, so a missing one silently removes the changes it recorded."""
    root = tmp_path / "vault"
    root.mkdir()
    (root / "one.md").write_text("first\n", encoding="utf-8")
    destination = tmp_path / "synced"
    synced(root, destination, at="2026-09-05T00:00:00+00:00")
    (root / "two.md").write_text("second\n", encoding="utf-8")
    synced(root, destination, at="2026-09-05T00:00:01+00:00")
    (root / "three.md").write_text("third\n", encoding="utf-8")
    synced(root, destination, at="2026-09-05T00:00:02+00:00")

    lines = (destination / JOURNAL).read_text(encoding="utf-8").splitlines()
    del lines[1]
    (destination / JOURNAL).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    checked = verify(Corpus(destination))
    assert any(fault.invariant == "journal 2" for fault in checked.faults)


def test_the_journal_check_is_one_of_the_checks_verify_counts(tmp_path: Path) -> None:
    """A check that runs and is not counted is a check the report understates.

    Not decoration: `Verified.summary` is the number a person reads to decide
    whether the corpus was looked at properly, so a count that lags the checks
    makes that judgement quietly wrong. The arithmetic is spelled out rather
    than compared against itself -- a test that only says "the same either way"
    passes just as well when the journal is never checked at all.
    """
    root = tmp_path / "vault"
    root.mkdir()
    (root / "one.md").write_text("first\n", encoding="utf-8")
    (root / "two.md").write_text("second\n", encoding="utf-8")
    destination = tmp_path / "synced"
    synced(root, destination)

    checked = verify(Corpus(destination))
    # Four checks of the manifest and its history -- run_id, coverage totals,
    # records naming units, the journal -- and one per artefact.
    assert checked.artefacts == 2
    assert checked.checks == 4 + checked.artefacts

    # And the count does not depend on whether there is a history to check: a
    # corpus written before ADR-0034 was looked at just as hard.
    (destination / JOURNAL).unlink()
    assert verify(Corpus(destination)).checks == checked.checks
