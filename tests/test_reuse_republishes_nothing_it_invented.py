"""A record that does not say is not a record that says no.

[ADR-0036] reuses a document whose source bytes did not change, and copies its
manifest record forward rather than converting again. That is sound only while
the record is **complete**. A field musubi publishes today and an older manifest
does not have gets a default on the way in, and copying that default out again
turns an absence into a claim.

Measured before it was fixed, on a Shift-JIS vault read entirely by detection:

```text
  first sync      encoding='cp932'   detected=True
  re-sync (kept)  encoding='cp932'   detected=True
  after upgrade   encoding='utf-8'   detected=False     <- every document
```

Nothing failed. The manifest said the corpus was UTF-8 and declared, `musubi
verify` passed, and the run report -- added for #82 so an owner could ask *how
much of this rests on a guess* -- answered **none of it**.

## Reading is not republishing

The two tests this had to be reconciled with are right, and they are about the
other half: `test_a_manifest_read_back_without_the_fields_still_parses` and
`test_a_manifest_written_before_the_field_reads_back_as_none` both say *absent
is not wrong*, and a reader carrying on is correct. So the gate is not in the
parser. It is where `source_hash` already gates the same thing: a record musubi
cannot reuse **whole** is a reason to convert, not a reason to stop.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from musubi import __version__
from musubi.application.pipeline import Settings
from musubi.application.sync import sync
from musubi.domain.manifest import published_artefact_fields
from musubi.infrastructure.algorithms import chooser
from musubi.infrastructure.decoding import detector
from musubi.infrastructure.emitters import MANIFEST, DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import FilesystemSource

NOTE = "# 設計メモ\n\nテントは 2.4kg。ブーツのほうが効く。山では軽さがすべて。\n"

available = pytest.mark.skipif(detector() is None, reason="charset-normalizer is not installed")


def settings(*, detect: bool = False) -> Settings:
    return Settings(CORE, default_screener(), chooser({}, detect=detect), __version__)


def older(manifest: Path, *without: str) -> None:
    """Rewrite a manifest as a musubi that predates those fields wrote it."""
    body = json.loads(manifest.read_text(encoding="utf-8"))
    for entry in body["artefacts"]:
        for field in without:
            entry.pop(field, None)
    manifest.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")


# -- the population, which is what makes the rest general -------------------


def test_the_fields_a_reused_record_must_have_come_from_the_renderer() -> None:
    """Not a list beside `render`. A field added to the manifest is a field a
    reused record must already carry, and nobody should have to remember it --
    which is exactly what went wrong: `encoding` was added and this gate was
    not told."""
    published = published_artefact_fields()
    assert {"encoding", "encoding_detected", "source_unit", "title"} <= published
    assert "facts" not in published, "written only when there are any, so optional"


@pytest.mark.parametrize("field", sorted(published_artefact_fields()), ids=lambda f: f)
def test_a_record_missing_any_published_field_is_converted_again(
    field: str, tmp_path: Path
) -> None:
    """Every field, not the one that was noticed.

    `encoding` is how this was found; `source_unit` would have been worse.
    Defaulting it to `characters` for a PDF says a page range is a character
    count, which is the thing [ADR-0025] exists to keep apart -- and it would
    have made two coverage numbers look addable that are not.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text(NOTE, encoding="utf-8")
    into = tmp_path / "corpus"

    first = sync(FilesystemSource(vault), settings(), DocumentEmitter(into))
    (before,) = first.manifest.artefacts

    older(into / MANIFEST, field)
    again = sync(FilesystemSource(vault), settings(), DocumentEmitter(into))
    (after,) = again.manifest.artefacts

    assert after == before, (
        f"a record missing {field!r} was reused, so whatever musubi defaulted it to "
        f"has been republished as though the corpus said it"
    )


# -- and the case that found it --------------------------------------------


@available
def test_a_detected_encoding_is_not_republished_as_a_declared_one(tmp_path: Path) -> None:
    """The measured defect.

    A vault musubi could only read by guessing came out of an upgrade recorded
    as `utf-8`, declared, on every document -- and #82's whole point was that
    a corpus should say where it guessed.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "old.md").write_bytes((NOTE * 4).encode("cp932"))
    into = tmp_path / "corpus"

    sync(FilesystemSource(vault), settings(detect=True), DocumentEmitter(into))
    older(into / MANIFEST, "encoding", "encoding_detected")

    again = sync(FilesystemSource(vault), settings(detect=True), DocumentEmitter(into))
    (artefact,) = again.manifest.artefacts

    assert artefact.encoding == "cp932", "a guess republished as a declaration"
    assert artefact.encoding_detected, "the corpus stopped saying it guessed"


# -- without breaking the thing the gate is in the middle of ---------------


def test_an_ordinary_re_sync_still_reuses(tmp_path: Path) -> None:
    """The other half of the trade, and the one that matters more day to day.

    A gate that refused every record would be correct and would also delete
    [ADR-0036]. `tools/scaling.py --only resync` is the number; this is the
    behaviour.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    for number in range(5):
        (vault / f"note-{number}.md").write_text(NOTE, encoding="utf-8")
    into = tmp_path / "corpus"

    sync(FilesystemSource(vault), settings(), DocumentEmitter(into))
    again = sync(FilesystemSource(vault), settings(), DocumentEmitter(into))

    assert len(again.kept) == 5, "nothing changed and everything was converted again"


def test_the_sync_after_an_upgrade_costs_one_conversion_and_then_stops(tmp_path: Path) -> None:
    """What the fix costs, stated: the first run after a field is added
    converts everything, and the run after that reuses again."""
    vault = tmp_path / "vault"
    vault.mkdir()
    for number in range(5):
        (vault / f"note-{number}.md").write_text(NOTE, encoding="utf-8")
    into = tmp_path / "corpus"

    sync(FilesystemSource(vault), settings(), DocumentEmitter(into))
    older(into / MANIFEST, "encoding")

    upgraded = sync(FilesystemSource(vault), settings(), DocumentEmitter(into))
    assert upgraded.kept == (), "the incomplete records were reused"

    settled = sync(FilesystemSource(vault), settings(), DocumentEmitter(into))
    assert len(settled.kept) == 5, "the corpus never settles back into reuse"
