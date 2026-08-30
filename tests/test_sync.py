"""`musubi sync`: the run that writes, and the two things it takes back.

ADR-0008's gate has a mechanism here for the first time: a credential means
nothing is promoted, not the offending unit skipped. And a corpus is not only
what was added — a note the owner deleted has to leave, or the corpus goes on
answering questions from a document they withdrew.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from musubi import __version__
from musubi.application.pipeline import Settings
from musubi.application.sync import Synced, sync
from musubi.errors import ContractError, CredentialFoundError
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.emitters import DOCUMENTS, MANIFEST, STAGING, TRACES, DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import ObsidianSource
from musubi.interfaces.cli import main

AWS = "AKIA" + "IOSFODNN7EXAMPLE"


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A CLI test that writes into a developer's real folder is worse here than
    anywhere else in this family: musubi's job is writing folders."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MUSUBI_INTO", raising=False)


def vault(root: Path, files: dict[str, str]) -> Path:
    if root.exists():
        for stale in root.rglob("*.md"):
            stale.unlink()
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    return root


def run_sync(root: Path, into: Path, **kwargs: object) -> Synced:
    settings = Settings(
        ruleset=CORE,
        screener=default_screener(),
        converter_for=converter_for,
        musubi_version=__version__,
        created_at="2026-08-30T00:00:00+00:00",
        **kwargs,  # type: ignore[arg-type]
    )
    return sync(ObsidianSource(root), settings, DocumentEmitter(into))


# -- what it writes ---------------------------------------------------------


def test_a_sync_builds_the_corpus(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"design/gear.md": "# 見出し\n"})
    into = tmp_path / "synced"
    result = run_sync(root, into)

    assert (into / DOCUMENTS / "design" / "gear.md").is_file()
    assert (into / TRACES / "design" / "gear.md.json").is_file()
    assert (into / MANIFEST).is_file()
    assert result.manifest.kind == "sync"


def test_the_staging_area_is_gone_afterwards(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"a.md": "x\n"})
    into = tmp_path / "synced"
    run_sync(root, into)
    assert not (into / STAGING).exists()


def test_the_manifest_it_wrote_is_the_manifest_it_returned(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"a.md": "x\n"})
    into = tmp_path / "synced"
    result = run_sync(root, into)
    body = json.loads((into / MANIFEST).read_text(encoding="utf-8"))
    assert body["run_id"] == result.manifest.run_id


def test_syncing_twice_over_an_unchanged_folder_writes_the_same_bytes(tmp_path: Path) -> None:
    """ADR-0003, at the level a user can see it."""
    root = vault(tmp_path / "vault", {"a.md": "x\n", "b/c.md": "y\n"})

    def build(into: Path) -> dict[str, bytes]:
        run_sync(root, into)
        return {
            path.relative_to(into).as_posix(): path.read_bytes()
            for path in sorted(into.rglob("*"))
            if path.is_file() and path.name != MANIFEST
        }

    assert build(tmp_path / "one") == build(tmp_path / "two")


# -- what it refuses --------------------------------------------------------


def test_a_credential_means_nothing_is_written(tmp_path: Path) -> None:
    """Not the offending unit skipped. Not the clean ones kept. Nothing."""
    root = vault(tmp_path / "vault", {"a.md": "fine\n", "setup.md": f"key: {AWS}\n"})
    into = tmp_path / "synced"

    with pytest.raises(CredentialFoundError) as refused:
        run_sync(root, into)

    assert not (into / DOCUMENTS).exists()
    assert not (into / STAGING).exists()
    assert "an AWS access key id" in str(refused.value)
    assert "--allow aws.access-key:setup.md" in str(refused.value)


def test_the_refusal_never_names_the_secret(tmp_path: Path) -> None:
    """The run stops so that the secret does not travel. An exception quoting it
    would send it to a log file instead of a corpus."""
    root = vault(tmp_path / "vault", {"setup.md": f"key: {AWS}\n"})
    with pytest.raises(CredentialFoundError) as refused:
        run_sync(root, tmp_path / "synced")
    assert AWS not in str(refused.value)


def test_more_than_one_hit_is_counted_in_the_message(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"a.md": f"{AWS}\n", "b.md": f"{AWS}\n"})
    with pytest.raises(CredentialFoundError, match="1 more were found"):
        run_sync(root, tmp_path / "synced")


def test_a_refusal_leaves_a_previous_corpus_standing(tmp_path: Path) -> None:
    """Failing to build is not the same as unbuilding. The corpus from the last
    good run is still the corpus."""
    root = vault(tmp_path / "vault", {"a.md": "first\n"})
    into = tmp_path / "synced"
    run_sync(root, into)

    vault(root, {"a.md": "first\n", "leak.md": f"{AWS}\n"})
    with pytest.raises(CredentialFoundError):
        run_sync(root, into)

    assert "first" in (into / DOCUMENTS / "a.md").read_text(encoding="utf-8")


def test_an_allowance_lets_the_run_through(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"setup.md": f"key: {AWS}\n"})
    into = tmp_path / "synced"
    result = run_sync(root, into, allowed=frozenset({"aws.access-key:setup.md"}))
    assert (into / DOCUMENTS / "setup.md").is_file()
    assert result.manifest.allowed == ("aws.access-key:setup.md",)


# -- what it takes back out -------------------------------------------------


def test_a_note_the_owner_deleted_leaves_the_corpus(tmp_path: Path) -> None:
    """A corpus that keeps a document its owner deleted goes on answering
    questions from something they withdrew."""
    root = vault(tmp_path / "vault", {"keep.md": "x\n", "gone.md": "y\n"})
    into = tmp_path / "synced"
    run_sync(root, into)
    assert (into / DOCUMENTS / "gone.md").is_file()

    vault(root, {"keep.md": "x\n"})
    result = run_sync(root, into)

    assert not (into / DOCUMENTS / "gone.md").exists()
    assert not (into / TRACES / "gone.md.json").exists()
    assert (into / DOCUMENTS / "keep.md").is_file()
    assert result.withdrawn == ("documents/gone.md", "traces/gone.md.json")


def test_the_manifest_says_what_was_taken_back_out(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"a.md": "x\n", "gone.md": "y\n"})
    into = tmp_path / "synced"
    run_sync(root, into)
    vault(root, {"a.md": "x\n"})
    run_sync(root, into)

    body = json.loads((into / MANIFEST).read_text(encoding="utf-8"))
    assert body["withdrawn"] == ["documents/gone.md", "traces/gone.md.json"]


def test_a_withdrawal_takes_the_empty_folder_with_it(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"deep/nested/a.md": "x\n"})
    into = tmp_path / "synced"
    run_sync(root, into)
    assert (into / DOCUMENTS / "deep" / "nested").is_dir()

    vault(root, {"other.md": "y\n"})
    run_sync(root, into)
    assert not (into / DOCUMENTS / "deep").exists()


def test_musubi_deletes_what_it_wrote_and_never_what_it_found(tmp_path: Path) -> None:
    """A folder somebody put something else in survives a sync intact."""
    root = vault(tmp_path / "vault", {"a.md": "x\n"})
    into = tmp_path / "synced"
    run_sync(root, into)

    stranger = into / DOCUMENTS / "not-ours.md"
    stranger.write_text("somebody else put this here\n", encoding="utf-8")

    vault(root, {"b.md": "y\n"})
    result = run_sync(root, into)

    assert stranger.is_file(), "musubi did not write it, so musubi does not remove it"
    assert result.withdrawn == ("documents/a.md", "traces/a.md.json")


def test_the_first_run_into_a_folder_withdraws_nothing(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"a.md": "x\n"})
    assert run_sync(root, tmp_path / "fresh").withdrawn == ()


def test_a_manifest_from_a_contract_nobody_recognises_stops_the_run(tmp_path: Path) -> None:
    """Guessing at it would produce a list of files to delete."""
    root = vault(tmp_path / "vault", {"a.md": "x\n"})
    into = tmp_path / "synced"
    into.mkdir()
    (into / MANIFEST).write_text('{"contract": "musubi.sync-manifest/9"}', encoding="utf-8")

    with pytest.raises(ContractError, match="does not recognise"):
        run_sync(root, into)


def test_a_manifest_that_is_not_json_stops_the_run(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"a.md": "x\n"})
    into = tmp_path / "synced"
    into.mkdir()
    (into / MANIFEST).write_text("not json at all", encoding="utf-8")

    with pytest.raises(ContractError, match="not readable as a manifest"):
        run_sync(root, into)


# -- the command ------------------------------------------------------------


def test_the_command_builds_and_reports(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = vault(tmp_path / "vault", {"a.md": "hello\n", "b.png": "x"})
    into = tmp_path / "synced"
    assert main(["sync", str(root), "--into", str(into)]) == 0

    out = capsys.readouterr().out
    assert "musubi sync" in out
    assert "Not read" in out
    assert "Limits" in out
    assert (into / DOCUMENTS / "a.md").is_file()


def test_the_command_reports_a_refusal_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = vault(tmp_path / "vault", {"setup.md": f"key: {AWS}\n"})
    into = tmp_path / "synced"
    assert main(["sync", str(root), "--into", str(into)]) == 1

    captured = capsys.readouterr()
    assert "an AWS access key id" in captured.err
    assert AWS not in captured.err
    assert not (into / DOCUMENTS).exists()


def test_the_command_reports_what_it_took_back_out(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = vault(tmp_path / "vault", {"a.md": "x\n", "gone.md": "y\n"})
    into = tmp_path / "synced"
    main(["sync", str(root), "--into", str(into)])
    capsys.readouterr()

    vault(root, {"a.md": "x\n"})
    main(["sync", str(root), "--into", str(into)])
    assert "Taken back out" in capsys.readouterr().out


def test_the_command_can_print_the_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = vault(tmp_path / "vault", {"a.md": "x\n"})
    assert main(["sync", str(root), "--into", str(tmp_path / "s"), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["kind"] == "sync"


def test_both_commands_take_the_same_options(capsys: pytest.CaptureFixture[str]) -> None:
    """A flag that exists on the dry run and not on the real one is the one way
    the shared pipeline cannot stop a plan from ceasing to predict a sync."""
    helps = {}
    for command in ("plan", "sync"):
        with pytest.raises(SystemExit):
            main([command, "--help"])
        helps[command] = capsys.readouterr().out

    for flag in ("--as", "--into", "--source-id", "--screen-entropy", "--allow", "--json"):
        assert flag in helps["plan"], flag
        assert flag in helps["sync"], flag
    assert "--show-removals" in helps["plan"]
    assert "--show-removals" not in helps["sync"], "there is nothing to preview after the fact"


def test_a_withdrawal_of_something_already_gone_is_not_an_error(tmp_path: Path) -> None:
    """Somebody deleted it by hand between two runs, or a previous withdrawal
    was interrupted. Either way the corpus is in the state the manifest wanted;
    saying so is better than failing."""
    into = tmp_path / "synced"
    (into / DOCUMENTS).mkdir(parents=True)
    emitter = DocumentEmitter(into)
    assert emitter.withdraw(["documents/never-existed.md", "../escaped.md"]) == ()
