"""Two musubi runs into one destination, and what the second does to the first.

There is no lock. `begin()` removes the staging area and makes it again, so a
run starting while another is mid-flight takes that one's files with it.

Measured, with the second run's `begin()` landing after four of six documents
had been promoted:

```text
  run A promote() raised FileNotFoundError after 4 files
  corpus: 6 documents, 4 carry run A's edit, manifest lists 6
  verify: FAULTS (8)
  after a normal sync: 6 carry the edit, verify holds
```

**So the design holds.** [ADR-0008]'s promotion order means a corpus is left
ahead of its own account rather than corrupt: `verify` names every document
that disagrees, and the next ordinary sync repairs all of it. That is what the
`promote()` docstring has always claimed about a crash, and a second run is a
crash with a cause.

What was wrong is how it arrived. `promote()` let the `FileNotFoundError` out,
so the command line said `Unreadable: the file system refused` -- and a person
reads that and goes to look at their disk. The file system was fine
([ADR-0053]).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from musubi import __version__
from musubi.application.pipeline import Settings, run
from musubi.application.sync import sync
from musubi.application.verify import verify
from musubi.domain.manifest import chunks
from musubi.errors import InterruptedRunError
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.corpus import Corpus
from musubi.infrastructure.emitters import DOCUMENTS, DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import FilesystemSource

EDIT = "Run A edited this."


def settings() -> Settings:
    return Settings(CORE, default_screener(), converter_for, __version__)


def vault(root: Path, body: str) -> Path:
    root.mkdir(exist_ok=True)
    for number in range(6):
        (root / f"note-{number}.md").write_text(f"# Note {number}\n\n{body}\n", encoding="utf-8")
    return root


def staged_run(root: Path, into: Path) -> DocumentEmitter:
    """A run that has staged everything and has not promoted."""
    emitter = DocumentEmitter(into)
    before = emitter.previous()
    emitter.begin()
    outcome = run(FilesystemSource(root), settings(), emitter, write=True, previous=before)
    emitter.stage_manifest(chunks(outcome.manifest))
    return emitter


def edited(into: Path) -> int:
    return sum(
        1 for path in (into / DOCUMENTS).glob("*.md") if EDIT in path.read_text(encoding="utf-8")
    )


# -- the failure, named ------------------------------------------------------


def test_a_second_run_taking_the_staging_area_is_named(tmp_path: Path) -> None:
    """It used to arrive as `Unreadable: the file system refused`, which is a
    sentence about the machine. The machine was fine."""
    root = vault(tmp_path / "vault", "Original.")
    into = tmp_path / "corpus"
    sync(FilesystemSource(root), settings(), DocumentEmitter(into))

    vault(tmp_path / "vault", EDIT)
    first = staged_run(root, into)
    DocumentEmitter(into).begin()  # the second run, which removes the first's staging

    with pytest.raises(InterruptedRunError, match="another musubi run"):
        first.promote()


def test_the_message_says_what_to_do_and_how_far_it_got(tmp_path: Path) -> None:
    """A failure that names no way forward is a dead end, and this one has a
    way forward that is one command long."""
    root = vault(tmp_path / "vault", "Original.")
    into = tmp_path / "corpus"
    sync(FilesystemSource(root), settings(), DocumentEmitter(into))

    vault(tmp_path / "vault", EDIT)
    first = staged_run(root, into)
    DocumentEmitter(into).begin()

    with pytest.raises(InterruptedRunError) as raised:
        first.promote()
    said = str(raised.value)
    assert "0 of" in said, "it does not say how far it got"
    assert "musubi verify" in said
    assert "repairs it" in said


# -- and the part that was already right ------------------------------------


def test_a_half_promoted_corpus_is_detected_and_then_repaired(tmp_path: Path) -> None:
    """The whole reason this is a failure and not a catastrophe.

    The staging area is taken **during** the promotion loop, so some documents
    move and the manifest does not. `verify` names every one that disagrees,
    and the next ordinary sync puts it right.
    """
    root = vault(tmp_path / "vault", "Original.")
    into = tmp_path / "corpus"
    sync(FilesystemSource(root), settings(), DocumentEmitter(into))

    vault(tmp_path / "vault", EDIT)
    first = staged_run(root, into)

    # The second run's `begin()` lands after four files have been moved.
    real = Path.replace
    moved = {"n": 0}

    def interrupted(self: Path, target: Path) -> Path:
        moved["n"] += 1
        if moved["n"] == 5:
            shutil.rmtree(first.staging, ignore_errors=True)
        return real(self, target)

    Path.replace = interrupted  # type: ignore[assignment, method-assign]
    try:
        with pytest.raises(InterruptedRunError):
            first.promote()
    finally:
        Path.replace = real  # type: ignore[method-assign]

    assert 0 < edited(into) < 6, "the point of this test is a corpus caught halfway"
    checked = verify(Corpus(into))
    assert not checked.holds, "a corpus ahead of its manifest and verify said nothing"
    assert len(checked.faults) >= 2

    sync(FilesystemSource(root), settings(), DocumentEmitter(into))
    assert edited(into) == 6, "the next ordinary run did not repair it"
    assert verify(Corpus(into)).holds


def test_an_ordinary_promotion_is_untouched(tmp_path: Path) -> None:
    """The guard only fires when the staging area is gone. A promotion that
    fails for any other reason still raises what it raised."""
    root = vault(tmp_path / "vault", "Original.")
    into = tmp_path / "corpus"
    result = sync(FilesystemSource(root), settings(), DocumentEmitter(into))
    assert len(result.promoted) == 13, "six documents, six maps and a manifest"
    assert verify(Corpus(into)).holds
