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
from musubi.infrastructure.converters.pdf import PdfConverter
from musubi.ports.converter import Converted
from pdf_fixtures import (
    COLUMNS_READ,
    FIRST_LINE,
    OUT_OF_ORDER_READ,
    SECOND_LINE,
    TABLE_READ,
    a_table,
    classic,
    modern,
    out_of_order,
    scanned,
    two_columns,
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
        0.678,
        "2026-09-09",
        "the mean over the three layouts of #97 **in the file's own order**, "
        "which is the default and what every existing corpus has. Stream "
        "order gets none of them right, so this is not a quality bar -- it is "
        "the number that catches a change making the wrong order wronger "
        "while coverage stays flat.",
    ),
    Floor(
        "pdfium@1",
        "reading order agreement",
        0.55,
        0.789,
        "2026-09-09",
        "the same three layouts and the same purpose. It scores above "
        "pdf_text@1 because it groups by baseline, which happens to be right "
        "for one of the three; it has no reading-order setting yet, so this "
        "is the only reading-order number it has.",
    ),
    # -- the geometric strategies, which are bounds and not floors ----------
    Floor(
        "pdf_text@1",
        "two columns down",
        1.0,
        1.0,
        "2026-09-09",
        'a bound. `pdf-reading-order = "columns"` exists to read a '
        "two-column page down its columns, and a setting that is asked for "
        "and half delivered is worse than one that was never offered: the "
        "owner set it, believes the corpus is in reading order, and it is not.",
    ),
    Floor(
        "pdf_text@1",
        "a table across",
        1.0,
        1.0,
        "2026-09-09",
        "a bound, for the same reason and the opposite geometry. `rows` "
        "exists so a table emitted column by column is read row by row, and "
        "pairing `Item` with `Tent` is a corpus asserting something the "
        "document does not say.",
    ),
    Floor(
        "pdf_text@1",
        "one line, out of order",
        1.0,
        1.0,
        "2026-09-09",
        "a bound, and the smallest case in the set: three runs on one "
        "baseline shown middle-first. One baseline is one line whatever order "
        "the stream had, and this is what caught `Tm` missing from the "
        "line-break operators -- the whole page as one word.",
    ),
    # -- and the optional reader, wired to the same strategies --------------
    Floor(
        "pdfium@1",
        "two columns down",
        1.0,
        1.0,
        "2026-09-10",
        "a bound, and the same one `pdf_text@1` carries. `pdf-reading-order` "
        "was silently ignored by `pdfium@1` for the first three days it "
        "existed -- by the reader an owner installs *because* their PDFs need "
        "a better one ([ADR-0050]).",
    ),
    Floor(
        "pdfium@1",
        "a table across",
        1.0,
        1.0,
        "2026-09-10",
        "a bound. The runs come from pdfium's own text rects rather than from "
        "characters this grouped by a threshold, so there is no new number "
        "under this number -- which is why it can be a bound at all.",
    ),
    Floor(
        "pdfium@1",
        "one line, out of order",
        1.0,
        1.0,
        "2026-09-10",
        "a bound, and the one `pdfium@1` already passed in stream order "
        "because it sorts what it finds. Kept so that a change to how runs "
        "are built cannot lose it without saying so.",
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
    "two columns down": (
        'the whole case for `pdf-reading-order = "columns"`. Reading a '
        "two-column page as one column is what #97 is, and a strategy that "
        "asks for columns and does not deliver them is worse than the default "
        "-- the owner set it and got the interleaving anyway"
    ),
    "a table across": (
        'the whole case for `pdf-reading-order = "rows"`. A table read down '
        "its columns pairs `Item` with `Tent` rather than with `Mass`, which "
        "is a corpus stating a fact the document does not"
    ),
    "one line, out of order": (
        "three runs on one baseline, shown middle-first. One baseline is one "
        "line however the stream ordered it, and this is the smallest case "
        "where geometry and stream order disagree"
    ),
}

#: The strategy each of the geometric bounds is measured under, and the fixture
#: with the answer it has to reach. Kept beside the bounds rather than inside
#: `measured()` so that adding a layout is one entry rather than an edit in two
#: places.
GEOMETRIC: tuple[tuple[str, str, bytes, str], ...] = (
    ("two columns down", "columns", two_columns(), COLUMNS_READ),
    ("a table across", "rows", a_table(), TABLE_READ),
    ("one line, out of order", "rows", out_of_order(), OUT_OF_ORDER_READ),
)


def claiming(media_type: str) -> list[object]:
    return [c for c in known_converters() if media_type in getattr(c, "media_types", ())]


def _geometric(order: str) -> list[object]:
    """Every reader that can be asked for a reading order, so asked.

    Built here rather than taken from the registry, which holds the default:
    measuring the registry's instance would be measuring the setting switched
    off. `pdfium@1` is included when the extra is installed, and its absence is
    a smaller measurement rather than a missing floor ([ADR-0050]).
    """
    from musubi.infrastructure.converters.external import PAGE_EXTRACTORS, PagedConverter

    made: list[object] = [PdfConverter(reading_order_name=order)]
    made += [
        PagedConverter(extractor, order)
        for extractor in PAGE_EXTRACTORS
        if extractor.load() is not None and extractor.place is not None
    ]
    return made


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

    # The geometric strategies, which only `pdf_text@1` offers. Measured on the
    # converter the settings would build rather than the registry's instance --
    # the registry holds the default, and measuring that would be measuring the
    # setting being off.
    for measure, order, made, answer in GEOMETRIC:
        for reader in _geometric(order):
            name = str(reader.name)  # type: ignore[attr-defined]
            found[name.split("+")[0], measure] = _agreement(answer, _read(reader, made, PDF))

    layouts = (
        (two_columns(), COLUMNS_READ),
        (a_table(), TABLE_READ),
        (out_of_order(), OUT_OF_ORDER_READ),
    )
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
