"""A unit whose bytes did not change is not converted again.

[ADR-0006] promised *a re-export that changed nothing produces an empty diff*
and, measured, a no-change re-sync cost 1.01 of a cold one (#77). This is the
comparison that was missing, and the tests are about the ways it could be
wrong rather than about the speed:

  * a unit carried forward that should have been converted -- the ruleset
    moved, the signature list moved, the converter moved, the file on the
    disk moved -- which is a corpus whose account of itself is stale;
  * a manifest that differs from the one a cold run would have written, which
    is a corpus whose account of itself depends on how it was built;
  * a plan that predicts a different set than the sync then keeps.

The speed is measured once, in `tools/scaling.py --only resync`, and recorded
in `docs/measurements.md`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from musubi import __version__
from musubi.application.pipeline import Settings, run
from musubi.application.sync import Synced, sync
from musubi.application.verify import verify
from musubi.domain.removal import Ruleset
from musubi.errors import CredentialFoundError
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.corpus import Corpus
from musubi.infrastructure.emitters import MANIFEST, DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import ObsidianSource
from musubi.ports.converter import Converted, Converter, Unconvertible

NOTE = "# gear\n\nテントは 2.4kg。 https://example.com/?utm_source=x\n"


class Counting:
    """The real converter, with a tally of how often it was asked."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, media_type: str) -> Converter | None:
        found = converter_for(media_type)
        if found is None:
            return None
        inner: Converter = found
        outer = self

        class Wrapped:
            name = inner.name
            media_types = inner.media_types

            def convert(self, content: bytes, media_type: str) -> Converted | Unconvertible:
                outer.calls += 1
                return inner.convert(content, media_type)

        return Wrapped()


def settings(
    *,
    counting: Counting | None = None,
    ruleset: Ruleset = CORE,
    allowed: frozenset[str] = frozenset(),
    version: str = __version__,
    at: str = "2026-09-05T00:00:00+00:00",
) -> Settings:
    return Settings(
        ruleset=ruleset,
        screener=default_screener(),
        converter_for=counting or converter_for,
        musubi_version=version,
        allowed=allowed,
        created_at=at,
    )


def vault(tmp_path: Path, files: dict[str, str] | None = None) -> Path:
    root = tmp_path / "notes"
    root.mkdir(exist_ok=True)
    for name, text in (files or {"gear.md": NOTE, "stove.md": "# stove\n"}).items():
        (root / name).write_text(text, encoding="utf-8")
    return root


def synced(root: Path, into: Path, chosen: Settings | None = None) -> Synced:
    return sync(ObsidianSource(root), chosen or settings(), DocumentEmitter(into))


def manifest_of(into: Path) -> dict[str, Any]:
    body: dict[str, Any] = json.loads((into / MANIFEST).read_text(encoding="utf-8"))
    return body


def files_of(into: Path) -> dict[str, bytes]:
    return {
        path.relative_to(into).as_posix(): path.read_bytes()
        for path in sorted(into.rglob("*"))
        if path.is_file() and path.name not in {MANIFEST, "runs.jsonl"}
    }


# -- the property ------------------------------------------------------------


def test_a_no_change_re_sync_converts_nothing(tmp_path: Path) -> None:
    root = vault(tmp_path)
    into = tmp_path / "corpus"
    first = Counting()
    synced(root, into, settings(counting=first))
    assert first.calls == 2

    again = Counting()
    result = synced(root, into, settings(counting=again, at="2026-09-05T00:00:01+00:00"))

    assert again.calls == 0
    assert result.kept == ("gear.md", "stove.md")
    assert result.promoted == (MANIFEST,), "only the manifest should have moved"


def test_a_re_sync_writes_the_manifest_a_cold_run_would_have(tmp_path: Path) -> None:
    """The account of the corpus does not depend on how the corpus was built.

    The removals and the findings are the part this catches: a run that
    converted nothing has nothing to say about which rules fired, and carrying
    the artefact forward without its removals would leave a corpus nobody can
    appeal ([ADR-0005]).
    """
    root = vault(tmp_path)
    into = tmp_path / "corpus"
    synced(root, into)
    synced(root, into, settings(at="2026-09-05T00:00:01+00:00"))
    warm = manifest_of(into)
    warm_files = files_of(into)

    cold_into = tmp_path / "cold"
    synced(root, cold_into, settings(at="2026-09-05T00:00:01+00:00"))
    cold = manifest_of(cold_into)

    assert warm["removals"], "the fixture should have a tracking parameter to remove"
    assert warm == cold
    assert warm_files == files_of(cold_into)


def test_a_changed_unit_is_converted_and_the_rest_are_kept(tmp_path: Path) -> None:
    root = vault(tmp_path)
    into = tmp_path / "corpus"
    synced(root, into)

    (root / "gear.md").write_text(NOTE + "\nedited\n", encoding="utf-8")
    again = Counting()
    result = synced(root, into, settings(counting=again, at="2026-09-05T00:00:01+00:00"))

    assert again.calls == 1
    assert result.kept == ("stove.md",)
    assert "edited" in (into / "documents" / "gear.md").read_text(encoding="utf-8")
    assert verify(Corpus(into)).holds


def test_a_plan_keeps_what_the_sync_would_keep(tmp_path: Path) -> None:
    """The dry run predicts the real one, kept set included, and reads
    nothing it would not have read anyway."""
    root = vault(tmp_path)
    into = tmp_path / "corpus"
    synced(root, into)
    (root / "gear.md").write_text(NOTE + "\nedited\n", encoding="utf-8")

    counting = Counting()
    planned = run(
        ObsidianSource(root), settings(counting=counting), DocumentEmitter(into), write=False
    )
    assert planned.kept == ("stove.md",)
    assert counting.calls == 1

    result = synced(root, into, settings(at="2026-09-05T00:00:01+00:00"))
    assert result.kept == planned.kept


# -- everything that must make the run cold ----------------------------------


def test_a_different_ruleset_converts_everything(tmp_path: Path) -> None:
    """The cache key is not the bytes alone (#77). A new rule has to meet the
    old corpus."""
    root = vault(tmp_path)
    into = tmp_path / "corpus"
    synced(root, into)

    again = Counting()
    bumped = Ruleset(id=CORE.id, version=CORE.version + ".1", rules=CORE.rules)
    result = synced(root, into, settings(counting=again, ruleset=bumped))
    assert again.calls == 2
    assert result.kept == ()


def test_a_different_allowance_converts_everything(tmp_path: Path) -> None:
    """An allowance is part of what decided the previous run. Losing one is
    the fail-closed direction and a run must notice."""
    root = vault(tmp_path)
    into = tmp_path / "corpus"
    synced(root, into)

    again = Counting()
    result = synced(root, into, settings(counting=again, allowed=frozenset({"aws.access-key:x"})))
    assert again.calls == 2
    assert result.kept == ()


def test_a_different_musubi_converts_everything(tmp_path: Path) -> None:
    """On purpose. A converter that changed without changing its name is the
    one case nothing else here would catch, and an upgrade is the moment it
    happens."""
    root = vault(tmp_path)
    into = tmp_path / "corpus"
    synced(root, into)

    again = Counting()
    result = synced(root, into, settings(counting=again, version=__version__ + "+next"))
    assert again.calls == 2
    assert result.kept == ()


def test_a_different_converter_for_the_media_type_converts_that_unit(tmp_path: Path) -> None:
    root = vault(tmp_path)
    into = tmp_path / "corpus"
    synced(root, into)

    class Renamed:
        """The same output under a different name, which is what a settings
        change to another extractor looks like from here."""

        name = "markdown@next"
        media_types: tuple[str, ...] = ("text/markdown",)

        def convert(self, content: bytes, media_type: str) -> Converted | Unconvertible:
            inner = converter_for(media_type)
            assert inner is not None
            return inner.convert(content, media_type)

    def chooser(media_type: str) -> Converter | None:
        if media_type == "text/markdown":
            return Renamed()
        return converter_for(media_type)

    chosen = Settings(
        ruleset=CORE,
        screener=default_screener(),
        converter_for=chooser,
        musubi_version=__version__,
        created_at="2026-09-05T00:00:01+00:00",
    )
    result = synced(root, into, chosen)
    assert result.kept == ()


def test_a_document_edited_on_the_disk_is_converted_again(tmp_path: Path) -> None:
    """The check that makes carrying a record forward safe rather than
    hopeful. Trusting the manifest would leave the edit in place with the
    manifest describing something else -- the fault `verify` exists to find,
    put there by `sync`."""
    root = vault(tmp_path)
    into = tmp_path / "corpus"
    synced(root, into)
    (into / "documents" / "gear.md").write_text("somebody edited this\n", encoding="utf-8")

    again = Counting()
    result = synced(root, into, settings(counting=again, at="2026-09-05T00:00:01+00:00"))
    assert "gear.md" not in result.kept
    assert again.calls == 1
    assert "somebody" not in (into / "documents" / "gear.md").read_text(encoding="utf-8")
    assert verify(Corpus(into)).holds


def test_a_missing_sidecar_is_converted_again(tmp_path: Path) -> None:
    root = vault(tmp_path)
    into = tmp_path / "corpus"
    synced(root, into)
    (into / "traces" / "gear.md.json").unlink()

    result = synced(root, into, settings(at="2026-09-05T00:00:01+00:00"))
    assert "gear.md" not in result.kept
    assert (into / "traces" / "gear.md.json").is_file()


def test_a_manifest_without_source_hashes_makes_a_cold_run(tmp_path: Path) -> None:
    """A corpus written before ADR-0036 records no source hash, and nothing is
    inferred from its absence."""
    root = vault(tmp_path)
    into = tmp_path / "corpus"
    synced(root, into)
    body = manifest_of(into)
    for artefact in body["artefacts"]:
        artefact["source"].pop("content_hash")
    (into / MANIFEST).write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")

    again = Counting()
    result = synced(root, into, settings(counting=again, at="2026-09-05T00:00:01+00:00"))
    assert again.calls == 2
    assert result.kept == ()


# -- the timestamp, and the refusal ------------------------------------------


def test_a_touched_note_is_kept_and_its_document_gets_the_new_date(tmp_path: Path) -> None:
    """[ADR-0022]: the document keeps the day the note was written. Bytes
    unchanged and mtime moved is exactly a note somebody touched, and the
    corpus owes it the new date without converting it."""
    root = vault(tmp_path)
    into = tmp_path / "corpus"
    synced(root, into)

    moved = 1_700_000_000.0
    os.utime(root / "gear.md", (moved, moved))
    result = synced(root, into, settings(at="2026-09-05T00:00:01+00:00"))

    assert "gear.md" in result.kept
    assert (into / "documents" / "gear.md").stat().st_mtime == pytest.approx(moved, abs=2)


def test_a_refused_re_sync_touches_no_timestamp(tmp_path: Path) -> None:
    """Fail-closed includes the retained documents: a run that stopped must
    have changed nothing in the destination, and a timestamp is a change."""
    root = vault(tmp_path)
    into = tmp_path / "corpus"
    synced(root, into)
    before = (into / "documents" / "gear.md").stat().st_mtime

    moved = 1_700_000_000.0
    os.utime(root / "gear.md", (moved, moved))
    (root / "leak.md").write_text("AKIAIOSFODNN7EXAMPLE\n", encoding="utf-8")
    with pytest.raises(CredentialFoundError):
        synced(root, into, settings(at="2026-09-05T00:00:01+00:00"))

    assert (into / "documents" / "gear.md").stat().st_mtime == pytest.approx(before, abs=2)


# -- the corpus's own records ----------------------------------------------


def test_the_manifest_is_promoted_last(tmp_path: Path) -> None:
    """Sorted, `documents/` < `manifest.json` < `traces/`: a crash between the
    second and the third left a manifest describing maps not yet there."""
    root = vault(tmp_path)
    into = tmp_path / "corpus"
    result = synced(root, into)
    assert result.promoted[-1] == MANIFEST
    assert any(path.startswith("traces/") for path in result.promoted[:-1])


def test_a_no_change_re_sync_is_an_empty_journal_entry(tmp_path: Path) -> None:
    root = vault(tmp_path)
    into = tmp_path / "corpus"
    synced(root, into)
    synced(root, into, settings(at="2026-09-05T00:00:01+00:00"))

    last = Corpus(into).journal()[-1]
    assert last.change.is_empty
    assert last.names_nothing


def test_every_artefact_records_the_hash_of_its_source(tmp_path: Path) -> None:
    """The field the whole path rests on, and the same value the trace map
    already carried."""
    root = vault(tmp_path)
    into = tmp_path / "corpus"
    synced(root, into)
    for artefact in manifest_of(into)["artefacts"]:
        sidecar = json.loads((into / artefact["trace_map"]).read_text(encoding="utf-8"))
        assert artefact["source"]["content_hash"] == sidecar["source"]["content_hash"]


# -- and the command says so --------------------------------------------------


def test_the_commands_report_what_they_kept(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Through `main()`, not the service: the pipeline kept every document and
    the report printed nothing about it, because the count was wired into the
    printer and not into the two calls to it. A number that only the tests can
    see is a number the report is not making."""
    from musubi.interfaces.cli import main

    root = vault(tmp_path)
    into = tmp_path / "corpus"
    monkeypatch.chdir(tmp_path)
    assert main(["sync", str(root), "--into", str(into)]) == 0
    capsys.readouterr()

    assert main(["plan", str(root), "--into", str(into)]) == 0
    planned = capsys.readouterr().out
    assert "2 of them unchanged since the last run and carried forward unconverted" in planned

    assert main(["sync", str(root), "--into", str(into)]) == 0
    synced_out = capsys.readouterr().out
    assert "2 of them unchanged since the last run and carried forward unconverted" in synced_out
