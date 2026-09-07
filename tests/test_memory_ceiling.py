"""What a run may hold at once, as a gate rather than a printout.

`tools/scaling.py --only memory` has measured this for months and **nothing
failed when it moved**. `docs/measurements.md` said 1.5x, 1.3x, 1.3x;
by the time somebody looked again it was 1.8x, 1.7x, 1.7x, and no test, no
report and no reader had any way to know. That is #84's finding about the
converter scores, in a second place, and the answer is the same one: the number
that is printed and the number that is checked have to be the same number.

## A ceiling, not a floor

The converter register holds **floors** — a quality score must not fall. This is
the other direction: a run must not hold *more*. The care is identical, and so
is the reason for the headroom. A ceiling set at today's measurement makes every
honest experiment a build failure, so it sits above what was measured, and the
gap is written down.

## Why tracemalloc and not the resident set

`tracemalloc` counts Python allocations and nothing else: no interpreter
start-up, no allocator behaviour, no other process. A resident-set reading
differs between three operating systems and two Python versions, and a gate that
is noisy is a gate somebody disables.
"""

from __future__ import annotations

import shutil
import tempfile
import tracemalloc
from pathlib import Path

from musubi import __version__
from musubi.application.pipeline import Settings
from musubi.application.sync import sync
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.emitters import DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import FilesystemSource

#: The same note `tools/scaling.py` uses, so the tool and the gate measure one
#: thing. A fixture kept in two places is two fixtures.
PARAGRAPH = "Some ordinary prose in a paragraph that a person actually wrote.\n\n"
NOTE = "# A note\n\n" + PARAGRAPH * 40

#: Enough notes that the per-run constants are not the measurement, few enough
#: that this stays a test. The ratio is flat from here up.
NOTES = 100

#: What a run may hold, as a multiple of the bytes it read.
#:
#: Measured at **0.83x** on 2026-09-09, after the manifest stopped being built
#: as one string ([ADR-0045]). Before that it was 1.87x and the recorded figure
#: was 1.3x, which is the drift this exists to stop.
#:
#: The headroom is wide on purpose. This counts Python allocations across three
#: operating systems and two versions, and dictionaries resize in steps. What it
#: is sized to catch is a **return to holding the whole document**, which was
#: more than twice this.
CEILING = 1.3

#: What it measured when the ceiling was set. The gap is the headroom.
MEASURED = 0.83


def _peak() -> tuple[int, int]:
    """Bytes read, and the peak Python allocation during the sync."""
    root = Path(tempfile.mkdtemp())
    try:
        vault = root / "vault"
        vault.mkdir()
        read = 0
        for number in range(NOTES):
            (vault / f"note-{number:04d}.md").write_text(NOTE, encoding="utf-8")
            read += len(NOTE.encode("utf-8"))

        settings = Settings(CORE, default_screener(), converter_for, __version__)
        tracemalloc.start()
        try:
            sync(FilesystemSource(vault), settings, DocumentEmitter(root / "corpus"))
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        return read, peak
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_run_does_not_hold_more_than_the_ceiling() -> None:
    read, peak = _peak()
    ratio = peak / read
    assert ratio <= CEILING, (
        f"a run held {ratio:.2f}x what it read, and the ceiling is {CEILING:.2f}x. "
        f"It measured {MEASURED:.2f}x when that was set. Either this is a "
        f"regression, or the ceiling is wrong and moving it is a commit with a "
        f"reason in it."
    )


def test_the_ceiling_sits_above_what_it_was_measured_at() -> None:
    """Ceilings, not targets. A gate at today's number makes an honest
    experiment a build failure, which is what the converter floors say in the
    other direction."""
    assert CEILING > MEASURED, "no headroom: an experiment costing a byte fails the build"


def test_the_recorded_measurement_still_holds() -> None:
    """Not exact equality -- allocation counts drift a little between versions.

    What this catches is a **recorded number that has come loose from
    reality**, which is exactly what happened: the docs said 1.3x while runs
    were holding 1.7x, so the headroom was not what anybody thought it was.
    """
    read, peak = _peak()
    ratio = peak / read
    assert abs(ratio - MEASURED) < 0.4, (
        f"a run holds {ratio:.2f}x and this file records {MEASURED:.2f}x. The "
        f"gate may still pass while the number beside it is fiction."
    )


def test_the_measurement_is_of_something() -> None:
    """The guard that makes the rest worth anything.

    A ratio computed over no input, or over a sync that wrote nothing, is a
    number this file would happily report and nobody could use. Both of those
    have to be impossible before the ceiling above means a thing.
    """
    read, peak = _peak()
    assert read > 100_000, "the corpus is too small for the constants to have washed out"
    assert peak > 0, "tracemalloc measured nothing at all"
