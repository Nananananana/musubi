"""What each converter must not get worse than, and what set the number.

`tools/html_coverage.py`, `tools/pdf_coverage.py` and `tools/reading_order.py`
measure quality per converter and **print**. Nothing failed when a number fell:
a change that dropped `trafilatura@1` from 99.7% traceable to 70% passed every
test in the repository (#84).

## Floors, not targets

`docs/proposals/0001-the-design.md` §9 already decided the shape and the care in
it is the point:

> Floors in CI, set deliberately **below** the measured scores. **Floors, not
> targets** — a gate set at today's number makes every honest experiment a
> build failure, and tuning to reach a threshold is what `mamori`'s ADR-0023
> records.

So every entry here carries what it was measured at, when, and why the headroom
is the size it is. A floor moves **up** only deliberately, and moving one is a
commit somebody has to write a reason in.

## Not one number

Coverage means different things per `source_unit` — a character map answers
with a character, a PDF's answers with a page — and `docs/measurements.md`
already warns about the aggregate. So these are per converter and per measure,
and there is no total anywhere.

## Two of them are bounds rather than floors

`content kept` and `refuses a scan` have no headroom, on purpose. Losing a
planted paragraph is not a quality score getting worse; it is a corpus quietly
answering questions without a paragraph the page had. And a page with no text
layer becoming an empty document rather than a refusal is [ADR-0033]'s shape:
100% traceable over no characters, reading as success.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from html_fixtures import BOILERPLATE, CONTENT, page
from musubi.infrastructure.converters import known_converters
from musubi.ports.converter import Converted
from pdf_fixtures import (
    COLUMNS_READ,
    FIRST_LINE,
    SECOND_LINE,
    TABLE_READ,
    VERTICAL_READ,
    a_table,
    classic,
    modern,
    scanned,
    two_columns,
    vertical,
)

HTML = "text/html"
PDF = "application/pdf"


@dataclass(frozen=True, slots=True)
class Floor:
    """One number a converter must not fall below, and what put it there."""

    converter: str
    measure: str
    floor: float
    #: What it measured when the floor was set. The headroom is the difference.
    measured: float
    when: str
    why: str

    @property
    def headroom(self) -> float:
        return self.measured - self.floor


#: Converters that claim a media type these measures cover and have no floor,
#: each with the reason. Listed rather than omitted: a converter that is not
#: measured because nobody noticed is what this register exists to prevent.
NOT_FLOORED: dict[str, str] = {}

FLOORS: tuple[Floor, ...] = (
    # -- HTML, measured by tools/html_coverage.py on one generated page ------
    Floor(
        "html@1",
        "traceable coverage",
        0.85,
        0.935,
        "2026-09-08",
        "musubi's own scan of tags, which builds its map while converting. The "
        "headroom is wide because the number moves with the fixture's markup "
        "and a rule added to the pack is an honest reason for it to dip.",
    ),
    Floor(
        "html@1",
        "boilerplate rejected",
        2 / 6,
        3 / 6,
        "2026-09-08",
        "a scan of tags rejects the containers it knows and keeps the rest. "
        "One below the measurement: this is the number the extra exists to "
        "beat, and holding it to its own ceiling would fail the honest "
        "experiment of changing which tags it knows.",
    ),
    Floor(
        "trafilatura@1",
        "traceable coverage",
        0.90,
        0.997,
        "2026-09-08",
        "the map is recovered by alignment rather than built while converting "
        "([ADR-0028]), so this is the number that falls if alignment stops "
        "finding the extractor's output in the source. Ten points of headroom "
        "because a window or a minimum-run change may cost a little and is "
        "allowed to.",
    ),
    Floor(
        "trafilatura@1",
        "boilerplate rejected",
        4 / 6,
        6 / 6,
        "2026-09-08",
        "the whole case for the extra is that it beats the scan. Set above "
        "html@1's measurement rather than below trafilatura's, so the floor "
        "says what it is for: falling to the scan's level is the regression.",
    ),
    # -- PDF, measured by tools/pdf_coverage.py -----------------------------
    Floor(
        "pdfium@1",
        "reads a PDF 1.5",
        1.0,
        1.0,
        "2026-09-08",
        "the reason `musubi[pdf]` exists. A compressed object stream is what a "
        "PDF 1.5 *is* and almost every current producer writes one; losing "
        "this makes the extra pointless. No headroom: it reads it or it does "
        "not.",
    ),
    # -- reading order, measured by tools/reading_order.py ------------------
    Floor(
        "pdf_text@1",
        "reading order agreement",
        0.55,
        0.68,
        "2026-09-08",
        "the mean over the three layouts of #97, whose answers are written "
        "down. Neither reader gets any of them right, so this is not a "
        "quality bar -- it is the number that catches a change making the "
        "wrong order *wronger* while coverage stays flat.",
    ),
    Floor(
        "pdfium@1",
        "reading order agreement",
        0.55,
        0.68,
        "2026-09-08",
        "the same three layouts and the same purpose. Both readers score the "
        "same today and fail differently, which the per-fixture assertions in "
        "tests/test_reading_order.py record.",
    ),
)

#: Measures with no headroom, and why each is a bound rather than a floor.
BOUNDS: dict[str, str] = {
    "content kept": (
        "losing a planted paragraph is not a score getting worse -- it is a "
        "corpus answering questions without something the page said, and "
        "nothing anywhere saying so"
    ),
    "refuses a scan": (
        "a page with no text layer becoming an empty document is [ADR-0033]'s "
        "shape: 100% traceable over no characters, reading as success"
    ),
    "reads a PDF 1.4": "the shape every reader here was written against",
}


def claiming(media_type: str) -> list[object]:
    return [c for c in known_converters() if media_type in getattr(c, "media_types", ())]


def _agreement(answer: str, read: str | None) -> float:
    if read is None:
        return 0.0
    return difflib.SequenceMatcher(None, answer.split(), read.split()).ratio()


def _read(converter: object, made: bytes, media_type: str) -> str | None:
    got = converter.convert(made, media_type)  # type: ignore[attr-defined]
    return got.text if isinstance(got, Converted) else None


def measured() -> dict[tuple[str, str], float]:
    """Every measure, per converter, run now.

    One function so that the gate and the report cannot disagree about what a
    number is -- the failure `tools/` and `tests/` keeping separate copies of a
    fixture would produce, which is why `tools/reading_order.py` imports these
    fixtures rather than restating them.
    """
    found: dict[tuple[str, str], float] = {}

    document = page()
    for converter in claiming(HTML):
        text = _read(converter, document, HTML)
        name = converter.name  # type: ignore[attr-defined]
        if text is None:
            found[name, "traceable coverage"] = 0.0
            found[name, "boilerplate rejected"] = 0.0
            found[name, "content kept"] = 0.0
            continue
        got = converter.convert(document, HTML)  # type: ignore[attr-defined]
        found[name, "traceable coverage"] = got.trace.traceable_coverage
        found[name, "boilerplate rejected"] = sum(
            1 for phrase in BOILERPLATE if phrase not in text
        ) / len(BOILERPLATE)
        found[name, "content kept"] = sum(1 for phrase in CONTENT if phrase in text) / len(CONTENT)

    layouts = ((two_columns(), COLUMNS_READ), (a_table(), TABLE_READ), (vertical(), VERTICAL_READ))
    for converter in claiming(PDF):
        name = converter.name  # type: ignore[attr-defined]
        for label, made in (("reads a PDF 1.4", classic()), ("reads a PDF 1.5", modern())):
            text = _read(converter, made, PDF)
            whole = text is not None and FIRST_LINE in text and SECOND_LINE in text
            found[name, label] = 1.0 if whole else 0.0
        found[name, "refuses a scan"] = 1.0 if _read(converter, scanned(), PDF) is None else 0.0
        found[name, "reading order agreement"] = sum(
            _agreement(answer, _read(converter, made, PDF)) for made, answer in layouts
        ) / len(layouts)

    return found


def breaches() -> list[tuple[Floor, float]]:
    """Every floor that is not met, with what it measured."""
    now = measured()
    return [
        (floor, now[floor.converter, floor.measure])
        for floor in FLOORS
        if now.get((floor.converter, floor.measure), 0.0) < floor.floor
    ]
