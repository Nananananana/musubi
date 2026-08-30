"""`musubi plan`: the six stages, and the promise that nothing is written.

ADR-0012. A misclassified photograph can be looked at again; a corpus built from
rules that had not yet met this particular vault cannot be un-built without
somebody noticing first. So the command that writes nothing is the one that
exists, and it reports everything a sync would do.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from musubi import __version__
from musubi.application.pipeline import Settings, run
from musubi.domain.manifest import CONTRACT, LIMITS, Manifest, render
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.emitters import DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import ObsidianSource
from musubi.interfaces.cli import main

AWS = "AKIA" + "IOSFODNN7EXAMPLE"


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every CLI test chdirs and strips MUSUBI_*. A test that writes into a
    developer's real folder is worse here than anywhere else in this family:
    musubi's job is writing folders, and its subject is somebody's notes."""
    monkeypatch.chdir(tmp_path)
    for name in list(dict(**__import__("os").environ)):
        if name.startswith("MUSUBI_"):
            monkeypatch.delenv(name, raising=False)


def vault(root: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def plan(root: Path, into: Path, **kwargs: object) -> Manifest:
    settings = Settings(
        ruleset=CORE,
        screener=default_screener(),
        converter_for=converter_for,
        musubi_version=__version__,
        **kwargs,  # type: ignore[arg-type]
    )
    outcome = run(ObsidianSource(root), settings, DocumentEmitter(into), write=False)
    return outcome.manifest


# -- the pipeline -----------------------------------------------------------


def test_a_plan_reports_what_would_be_written(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"design/gear.md": "# 見出し\n\nテントは 2.4kg\n"})
    manifest = plan(root, tmp_path / "out")

    assert manifest.kind == "plan"
    assert [a.path for a in manifest.artefacts] == ["documents/design/gear.md"]
    assert manifest.artefacts[0].unit_key == "design/gear.md"
    assert manifest.artefacts[0].layer == "fact"


def test_a_plan_writes_nothing_at_all(tmp_path: Path) -> None:
    """The whole promise, checked the only way it can be: look at the disk."""
    root = vault(tmp_path / "vault", {"a.md": "x\n"})
    destination = tmp_path / "out"
    plan(root, destination)
    assert not destination.exists()


def test_the_numbers_a_plan_reports_are_the_ones_a_sync_would(tmp_path: Path) -> None:
    """Two implementations of one pipeline is exactly how a dry run stops
    predicting the real one, so there is only one."""
    root = vault(tmp_path / "vault", {"a.md": "# 見出し\n"})
    predicted = plan(root, tmp_path / "out")

    emitter = DocumentEmitter(tmp_path / "out")
    emitter.begin()
    settings = Settings(CORE, default_screener(), converter_for, __version__)
    real = run(ObsidianSource(root), settings, emitter, write=True).manifest
    emitter.discard()

    assert [a.content_hash for a in real.artefacts] == [a.content_hash for a in predicted.artefacts]
    assert real.run_id == predicted.run_id, "the kind is metadata, not an input"


def test_the_stages_run_in_the_order_that_is_safe(tmp_path: Path) -> None:
    """Screening before conversion. A secret never reaches a file musubi wrote,
    so a run that stops has nothing on disk to clean up (ADR-0008)."""
    root = vault(tmp_path / "vault", {"setup.md": f"key: {AWS}\n"})
    settings = Settings(CORE, default_screener(), converter_for, __version__)
    outcome = run(ObsidianSource(root), settings, DocumentEmitter(tmp_path / "out"), write=True)

    assert outcome.refused
    assert outcome.manifest.artefacts == ()
    assert not (tmp_path / "out" / "documents").exists()


def test_every_hit_is_reported_rather_than_only_the_first(tmp_path: Path) -> None:
    """A plan that reports one hit and stops sends its reader back for another
    run."""
    root = vault(tmp_path / "vault", {"a.md": f"{AWS}\n", "b.md": f"{AWS}\n"})
    settings = Settings(CORE, default_screener(), converter_for, __version__)
    outcome = run(ObsidianSource(root), settings, DocumentEmitter(tmp_path / "o"), write=False)
    assert [key for key, _ in outcome.refusals] == ["a.md", "b.md"]


def test_an_allowance_lets_a_unit_through_and_is_recorded(tmp_path: Path) -> None:
    """An exemption nobody can see is an exemption that outlives its reason."""
    root = vault(tmp_path / "vault", {"a.md": f"{AWS}\n"})
    manifest = plan(root, tmp_path / "o", allowed=frozenset({"aws.access-key:a.md"}))
    assert [a.unit_key for a in manifest.artefacts] == ["a.md"]
    assert manifest.allowed == ("aws.access-key:a.md",)
    assert [f.rule for _, f in manifest.findings] == ["aws.access-key"], "still reported"


def test_a_tracking_parameter_is_removed_and_accounted_for(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"a.md": "see https://x.example/?utm_source=n&id=7\n"})
    manifest = plan(root, tmp_path / "o")
    assert [record.rule for _, record in manifest.removals] == ["tracking.utm-family"]


def test_what_will_not_be_read_is_reported_with_its_reason(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"a.md": "x\n", "photo.png": "y", ".obsidian/w.md": "z"})
    manifest = plan(root, tmp_path / "o")
    assert {(s.origin, s.reason) for s in manifest.skipped} == {
        ("photo.png", "unknown_format"),
        (".obsidian", "machinery"),
    }


def test_a_file_musubi_will_not_decode_is_reported_rather_than_mangled(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "a.md").write_bytes("これはシフトJISです".encode("shift_jis"))
    manifest = plan(root, tmp_path / "o")
    assert [(s.origin, s.reason) for s in manifest.skipped] == [("a.md", "undecodable")]
    assert manifest.artefacts == ()


def test_a_secret_in_a_file_that_cannot_be_converted_is_still_caught(tmp_path: Path) -> None:
    """Screening a unit about to be reported unreadable is the one place a
    secret in an unconvertible file still gets caught."""
    root = tmp_path / "vault"
    root.mkdir()
    (root / "a.md").write_bytes("メモ".encode("shift_jis") + f" {AWS}".encode())
    settings = Settings(CORE, default_screener(), converter_for, __version__)
    outcome = run(ObsidianSource(root), settings, DocumentEmitter(tmp_path / "o"), write=False)
    assert outcome.refused


# -- the manifest -----------------------------------------------------------


def test_the_manifest_publishes_its_denominator(tmp_path: Path) -> None:
    """`emitted` alone would let a reader compute a ratio against the wrong
    total, and they would."""
    root = vault(tmp_path / "vault", {"a.md": "hello\n", "b.png": "x"})
    coverage = plan(root, tmp_path / "o").coverage
    assert (coverage.units_read, coverage.emitted, coverage.skipped) == (2, 1, 1)
    assert coverage.characters > coverage.traceable_characters, "front matter is synthetic"


def test_the_run_id_ignores_the_clock(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"a.md": "x\n"})
    early = plan(root, tmp_path / "o", created_at="2026-01-01T00:00:00+00:00")
    late = plan(root, tmp_path / "o", created_at="2026-12-31T23:59:59+00:00")
    assert early.run_id == late.run_id


def test_the_run_id_ignores_where_the_folder_lives(tmp_path: Path) -> None:
    """An id that embedded an absolute path would differ between two machines
    holding the same corpus."""
    here = vault(tmp_path / "here", {"a.md": "x\n"})
    there = vault(tmp_path / "there", {"a.md": "x\n"})
    assert plan(here, tmp_path / "o").run_id == plan(there, tmp_path / "o").run_id


def test_the_run_id_changes_when_the_content_does(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"a.md": "one\n"})
    before = plan(root, tmp_path / "o").run_id
    vault(root, {"a.md": "two\n"})
    assert plan(root, tmp_path / "o").run_id != before


def test_the_manifest_names_what_was_in_force(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"a.md": "x\n"})
    manifest = plan(root, tmp_path / "o")
    assert manifest.rulesets == (("core", "2026.08"),)
    assert manifest.converters == ("markdown@1",)
    assert manifest.screener.startswith("signatures@")
    assert manifest.emitter == "documents@1"
    assert manifest.sources[0].key_derivation == "path"


def test_the_document_carries_its_own_limits(tmp_path: Path) -> None:
    """The artefact travels and the documentation does not."""
    root = vault(tmp_path / "vault", {"a.md": "x\n"})
    body = json.loads(render(plan(root, tmp_path / "o")))
    assert body["contract"] == CONTRACT
    assert body["limits"] == list(LIMITS)
    assert any("has not been measured" in limit for limit in body["limits"])


def test_the_document_renders_the_same_bytes_twice(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"a.md": "x\n", "b/c.md": "y\n"})
    manifest = plan(root, tmp_path / "o", created_at="2026-08-30T00:00:00+00:00")
    assert render(manifest) == render(manifest)
    assert render(manifest).endswith("}\n")


def test_a_removal_is_recorded_by_hash_and_never_by_value(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"a.md": "https://x.example/?utm_source=who-i-am\n"})
    body = render(plan(root, tmp_path / "o"))
    assert "who-i-am" not in body
    assert "removed_sha256" in body


def test_a_finding_is_recorded_by_hash_and_never_by_value(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"a.md": f"{AWS}\n"})
    body = render(plan(root, tmp_path / "o", allowed=frozenset({"aws.access-key:a.md"})))
    assert AWS not in body
    assert "matched_sha256" in body


# -- the command ------------------------------------------------------------


def test_the_command_prints_a_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = vault(tmp_path / "vault", {"a.md": "hello\n", "b.png": "x"})
    assert main(["plan", str(root)]) == 0

    out = capsys.readouterr().out
    assert "musubi plan" in out
    assert "nothing was written" in out
    assert "Would not be read" in out
    assert "b.png" in out
    assert "Limits" in out


def test_the_command_writes_nothing(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"a.md": "x\n"})
    main(["plan", str(root), "--into", str(tmp_path / "out")])
    assert not (tmp_path / "out").exists()


def test_a_credential_makes_the_command_fail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = vault(tmp_path / "vault", {"setup.md": f"key: {AWS}\n"})
    assert main(["plan", str(root)]) == 1
    out = capsys.readouterr().out
    assert "Would refuse" in out
    assert "an AWS access key id" in out
    assert AWS not in out, "the run stops so the secret does not travel"


def test_the_command_can_print_the_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = vault(tmp_path / "vault", {"a.md": "x\n"})
    assert main(["plan", str(root), "--json"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["kind"] == "plan"


def test_show_removals_prints_values_to_the_terminal_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = vault(tmp_path / "vault", {"a.md": "https://x.example/?utm_source=n\n"})
    assert main(["plan", str(root), "--show-removals"]) == 0
    out = capsys.readouterr().out
    assert "terminal only, never written" in out
    assert "tracking.utm-family" in out


def test_an_allowance_can_be_passed_on_the_command_line(tmp_path: Path) -> None:
    root = vault(tmp_path / "vault", {"a.md": f"{AWS}\n"})
    assert main(["plan", str(root), "--allow", "aws.access-key:a.md"]) == 0


def test_a_folder_musubi_refuses_reports_and_does_not_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["plan", str(tmp_path / "nowhere")]) == 1
    assert "does not exist" in capsys.readouterr().err


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "plan" in capsys.readouterr().out


def test_the_entropy_tier_is_opt_in_and_says_what_it_costs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        main(["plan", "--help"])
    assert "21.1%" in capsys.readouterr().out


# -- the branches nothing in a real run reaches yet -------------------------


def test_a_media_type_no_converter_claims_is_skipped_with_its_reason(tmp_path: Path) -> None:
    """Unreachable through the CLI today, because a source only offers media
    types a converter holds. It stops being unreachable the moment a source
    learns a format before a converter does, which is the order those two
    always arrive in."""
    root = vault(tmp_path / "vault", {"a.md": "x\n"})
    source = ObsidianSource(root)
    settings = Settings(CORE, default_screener(), lambda media: None, __version__)
    manifest = run(source, settings, DocumentEmitter(tmp_path / "o"), write=False).manifest
    assert [(s.origin, s.reason, s.detail) for s in manifest.skipped] == [
        ("a.md", "no_converter", "text/markdown")
    ]


def test_an_empty_artefact_is_not_reported_as_untraceable(tmp_path: Path) -> None:
    """0/0. Reporting 0% would read as a failure of the guarantee when no
    character fails it."""
    root = tmp_path / "vault"
    root.mkdir()
    (root / "a.txt").write_text("", encoding="utf-8")
    (artefact,) = plan(root, tmp_path / "o").artefacts
    assert artefact.characters == 0
    assert artefact.traceable_coverage == 1.0

    written = vault(tmp_path / "other", {"a.md": "hello\n"})
    (real,) = plan(written, tmp_path / "o").artefacts
    assert 0.0 < real.traceable_coverage < 1.0, "the front matter musubi wrote is not traceable"
