"""The names musubi prints when it fails, and whether the list of them is true.

`sora` keeps an incident log and folds it by **the word before the first colon
on stderr**, keeping nothing else from the line, because a message can quote a
path from somebody's own machine. That makes the set of those words an
interface, and `musubi errors --json` publishes it.

An interface published wrongly is worse than one not published. A catalogue
listing six of seven kinds means the seventh arrives at a reader that has never
been told about it, and the whole point of the exercise was that a reader can
name what it sees.

So the important tests here are the two population guards: **every kind the
code can print is in the catalogue**, and **every kind in the catalogue is one
the code can print**. Neither is satisfiable by a list somebody remembered to
update.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
import re
from pathlib import Path

import pytest

from musubi.errors import (
    CATALOGUE,
    DONE,
    FAILED,
    NOT_PRINTED,
    OPEN_NAMESPACES,
    REFUSED,
    USAGE,
    MusubiError,
)
from musubi.interfaces.cli import main

MAIN = Path(__file__).resolve().parent.parent / "src" / "musubi" / "interfaces" / "cli" / "main.py"

#: `sora`'s vocabulary. musubi produces two of the four; the other two are here
#: so that a kind claiming one turns this red rather than reaching a reader
#: that has no branch for it.
OUTCOMES = frozenset({"refused", "unavailable", "failed", "timed_out"})

KINDS = {kind.kind: kind for kind in CATALOGUE}


def raised() -> set[str]:
    """Every `MusubiError` subclass in musubi, by name.

    **Every module is imported first**, and that is not tidiness. The class
    tree only holds what has been imported, so this passed on its own and
    failed in a full run -- `OutsideRootError` lives in the MCP server, which
    nothing else in this file loads. A guard whose population depends on which
    tests ran before it is a coin toss, and the full run is what found the two
    real gaps: that kind, and `MusubiError` itself being raised bare.
    """
    package = importlib.import_module("musubi")
    for module in pkgutil.walk_packages(package.__path__, prefix="musubi."):
        importlib.import_module(module.name)

    found: set[str] = set()
    pending = [MusubiError]
    while pending:
        current = pending.pop()
        for subclass in current.__subclasses__():
            if subclass.__module__.startswith("musubi."):
                found.add(subclass.__name__)
                pending.append(subclass)
    return found


def printed() -> set[str]:
    """Every name the command line can put before a colon on stderr.

    Read out of the source rather than listed, for the same reason the
    converter floors read their population out of the registry: a kind added
    next to the others is a kind nobody has to remember to catalogue.
    """
    source = MAIN.read_text(encoding="utf-8")
    return set(re.findall(r'_stderr\(\s*"([A-Za-z]+)"', source)) | set(
        re.findall(r'print\(f"([A-Za-z]+): \{message\}"', source)
    )


# -- the two population guards ----------------------------------------------


def test_every_error_musubi_raises_is_in_the_catalogue() -> None:
    """Read out of the class tree, so a new exception is catalogued or red.

    `MusubiError` itself is excluded because nothing raises it any more. It
    used to: the MCP server raised the bare base class for a root that is not
    a folder, which put the word `MusubiError` on stderr -- a kind meaning
    *an error with no kind*, and a bucket that tells its reader nothing.
    """
    assert raised(), "no MusubiError subclasses found; this guard is measuring nothing"
    missing = sorted(raised() - set(KINDS) - set(NOT_PRINTED))
    assert not missing, (
        f"{missing} can reach stderr and are not in the catalogue. A kind sora has "
        f"never been told about is an incident it cannot name. If one of these "
        f"cannot reach stderr, name it in NOT_PRINTED with the reason."
    )


def test_every_name_the_command_line_prints_is_in_the_catalogue() -> None:
    """The other half, and the one the exception tree cannot give.

    `Usage`, `Unverified`, `Unreadable` and `Unexpected` are names the command
    line chooses without an exception class behind them, so they are read out
    of the source of `main.py` itself.
    """
    names = printed()
    assert names, "found no printed kinds; the pattern this reads has moved"
    missing = sorted(names - set(KINDS))
    assert not missing, f"{missing} are printed and not catalogued"


@pytest.mark.parametrize("name", sorted(NOT_PRINTED), ids=lambda n: n)
def test_a_kind_excluded_from_the_catalogue_still_exists(name: str) -> None:
    """The exclusion register checked in both directions. An entry for a class
    nobody defines any more is an exemption outliving its reason, which is what
    the manifest's `allowed` list is careful about for the same reason."""
    assert name in raised(), f"{name} is excused from the catalogue and does not exist"
    assert len(NOT_PRINTED[name]) > 60, f"{name} is excluded without a real reason"


def test_the_catalogue_names_nothing_that_cannot_happen() -> None:
    """Backwards. An entry for a kind nothing produces is an entry that passes
    by never being tested, and a reader writing a branch for it waits forever.
    """
    reachable = (raised() - set(NOT_PRINTED)) | printed()
    stale = sorted(set(KINDS) - reachable)
    assert not stale, f"{stale} are catalogued and nothing produces them"


# -- what each entry says ---------------------------------------------------


@pytest.mark.parametrize("kind", CATALOGUE, ids=lambda k: k.kind)
def test_every_entry_is_answerable(kind: object) -> None:
    entry = KINDS[kind.kind]  # type: ignore[attr-defined]
    assert entry.exit_code in {DONE, FAILED, USAGE, REFUSED}
    assert entry.exit_code != DONE, "a kind that exits 0 is not a failure"
    assert entry.outcome in OUTCOMES
    assert len(entry.detail) > 40, "a kind with no sentence under it explains nothing"
    assert entry.detail_ja, "sora asked musubi to write the Japanese, not to translate it"
    assert any(ord(letter) > 0x2FF for letter in entry.detail_ja), (
        f"{entry.kind}'s detail_ja is not Japanese"
    )


@pytest.mark.parametrize("kind", CATALOGUE, ids=lambda k: k.kind)
def test_a_refusal_exits_with_the_refusal_code(kind: object) -> None:
    """The distinction the whole exit-code table exists for: a refusal is not
    retried, a failure is. A kind whose outcome and code disagree tells a
    caller two different things."""
    entry = KINDS[kind.kind]  # type: ignore[attr-defined]
    if entry.outcome == "refused":
        assert entry.exit_code == REFUSED
    else:
        assert entry.exit_code != REFUSED


@pytest.mark.parametrize("kind", CATALOGUE, ids=lambda k: k.kind)
def test_no_entry_carries_something_that_could_be_a_value(kind: object) -> None:
    """`sora` asked for this by name, and the reason is good: it can say its
    incident log holds no content only because it keeps names and drops
    sentences. A catalogue carrying an example path or a `{}` template invites
    a reader to fill it in from a log, and then the log has the value in it.
    """
    entry = KINDS[kind.kind]  # type: ignore[attr-defined]
    for text in (entry.detail, entry.detail_ja):
        assert "{" not in text and "}" not in text, "a message template"
        assert not re.search(r"(^|\s)[/~]\S*[/\\]", text), "something shaped like a path"
        assert "C:" not in text


def test_musubi_produces_two_of_soras_four_outcomes_and_says_which() -> None:
    """`unavailable` and `timed_out` never appear, and that is a fact about
    [ADR-0007] rather than an omission: musubi reads a folder that is already
    on the disk, so there is no service to be unavailable and nothing to wait
    for. Asserted so that a kind claiming one has to argue with this test.
    """
    used = {kind.outcome for kind in CATALOGUE}
    assert used == {"refused", "failed"}


def test_only_the_file_system_is_retryable() -> None:
    """`retryable` is the field sora said only musubi can fill in. If every
    entry answered the same way it would be a field that says nothing, so the
    one that differs is worth pinning: a full disk may not be full next time,
    and no other failure here is about the machine.
    """
    retryable = {kind.kind for kind in CATALOGUE if kind.retryable}
    assert retryable == {"Unreadable"}


@pytest.mark.parametrize("kind", CATALOGUE, ids=lambda k: k.kind)
def test_the_process_exits_with_the_code_the_catalogue_publishes(kind: object) -> None:
    """The catalogue is not a description of the code; it **is** the code.

    `main` used to decide a refusal from a hand-written tuple of exception
    classes. It named two of the three refusals the day a third arrived, so
    `DifferentSourceError` -- which had just stopped a corpus from being
    deleted -- exited 1, which tells an orchestrator to retry it ([ADR-0049]).
    """
    from musubi.interfaces.cli.main import _EXIT_CODES

    entry = KINDS[kind.kind]  # type: ignore[attr-defined]
    if entry.kind in _EXIT_CODES:
        assert _EXIT_CODES[entry.kind] == entry.exit_code


def test_every_exception_the_process_maps_is_one_the_catalogue_knows() -> None:
    """And nothing is mapped that the published document does not mention."""
    from musubi.interfaces.cli.main import _EXIT_CODES

    assert _EXIT_CODES, "the table is empty, so the test above checks nothing"
    assert set(_EXIT_CODES) <= set(KINDS)


# -- the document a program actually reads ----------------------------------


def test_the_catalogue_is_a_document_with_a_contract(
    capsysbinary: pytest.CaptureFixture[bytes],
) -> None:
    assert main(["errors", "--json"]) == DONE
    body = json.loads(capsysbinary.readouterr().out.decode("utf-8"))

    assert body["contract"] == "musubi.errors/1-draft"
    assert body["by"].startswith("musubi/")
    assert body["open_namespaces"] == list(OPEN_NAMESPACES)
    assert [one["kind"] for one in body["errors"]] == [kind.kind for kind in CATALOGUE]
    for one in body["errors"]:
        assert set(one) == {"kind", "exit_code", "outcome", "retryable", "detail", "detail_ja"}


def test_the_open_namespaces_list_is_empty_because_the_set_is_closed() -> None:
    """Empty rather than absent. musubi assembles no kind from anybody else's
    vocabulary, and saying so is an answer; leaving the field out is a shrug a
    reader has to guess at."""
    assert OPEN_NAMESPACES == ()


# -- and the names as they actually arrive ----------------------------------


def test_a_usage_error_begins_with_its_kind(capsys: pytest.CaptureFixture[str]) -> None:
    """argparse writes `usage: ...` first, so a reader taking the word before
    the colon filed every bad command line under a kind called `usage`."""
    with pytest.raises(SystemExit) as exit_code:
        main(["sync", "--nonexistent-flag"])
    assert exit_code.value.code == USAGE
    assert capsys.readouterr().err.splitlines()[0].startswith("Usage: ")


def test_a_refusal_begins_with_its_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """It used to be `musubi: ...`, so every failure musubi has folded into
    one bucket called `musubi`."""
    monkeypatch.chdir(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "setup.md").write_text("key: AKIAIOSFODNN7EXAMPLE\n", encoding="utf-8")

    assert main(["sync", str(vault), "--into", str(tmp_path / "corpus")]) == REFUSED
    first = capsys.readouterr().err.splitlines()[0]
    assert first.startswith("CredentialFoundError: ")
    assert first.split(":")[0] in KINDS, "a name no catalogue reader can look up"


def test_a_failure_begins_with_its_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["sync", str(tmp_path / "nothing-here")]) == FAILED
    first = capsys.readouterr().err.splitlines()[0]
    assert first.split(":")[0] in KINDS


def test_a_corpus_that_does_not_verify_says_so_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """It exited 1 with **nothing on stderr at all**, so a reader had an exit
    code and no word for what happened."""
    monkeypatch.chdir(tmp_path)
    into = tmp_path / "corpus"
    into.mkdir()
    (into / "manifest.json").write_text("{not json", encoding="utf-8")

    assert main(["verify", str(into)]) == FAILED
    err = capsys.readouterr().err
    assert err, "exit 1 and silence: a caller has a number and no name"
    assert err.splitlines()[0].split(":")[0] in KINDS
