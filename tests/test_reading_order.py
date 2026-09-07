"""Did it read the document, rather than did it read at all.

`traceable_coverage` says an offset resolves. `answer_width` says how tightly.
The conformance suite says the map is structurally honest. **None of them says
the text is right**, and the `Limits` block has always admitted it in words:

    A traceable character means an offset resolves to a place in the source.
    It does not mean the conversion read the document in the right order.

Saying it is not measuring it (#85). These fixtures have a **stated correct
reading**, so output can be compared against an answer instead of against
whatever the converter did last time.

## What changed here

The first version of this file asserted what musubi got *wrong* on all three
layouts. Two of those three answers turned out to be unreachable -- not because
musubi was bad at them but because the fixtures did not contain them
([ADR-0042]). So the most important test in this file is now
`test_every_stated_answer_is_reachable_by_some_strategy`, which is the guard
that would have caught it: an answer no configuration of musubi can produce is
either a missing strategy or a wrong fixture, and both want a person.
"""

from __future__ import annotations

import pytest

from musubi.domain.reading_order import (
    BASELINE_TOLERANCE,
    COLUMN_GAP,
    STRATEGIES,
    Run,
    columns,
    rows,
    strategy_named,
    text_of,
)
from musubi.infrastructure.converters import known_converters
from musubi.infrastructure.converters.pdf import PdfConverter
from musubi.ports.converter import Converted, Unconvertible
from pdf_fixtures import (
    COLUMNS,
    COLUMNS_READ,
    OUT_OF_ORDER_READ,
    TABLE,
    TABLE_READ,
    a_table,
    composite,
    out_of_order,
    scanned,
    two_columns,
)

PDF = "application/pdf"

#: Every layout whose right answer is written down, with the strategy that is
#: supposed to reach it. The population for most of this file.
LAYOUTS: tuple[tuple[str, bytes, str, str], ...] = (
    ("two columns", two_columns(), COLUMNS_READ, "columns"),
    ("a table", a_table(), TABLE_READ, "rows"),
    ("one line, out of order", out_of_order(), OUT_OF_ORDER_READ, "rows"),
)


def ordering(order: str) -> list[object]:
    """Every reader that can be asked for a reading order, built with it.

    Two of them now. `pdfium@1` was left out when the setting arrived and
    ignored it for three days ([ADR-0050]), so this is read out of what can
    place its text rather than named -- an extractor that gains positions is
    covered without anybody editing here.
    """
    from musubi.infrastructure.converters.external import PAGE_EXTRACTORS, PagedConverter

    made: list[object] = [PdfConverter(reading_order_name=order)]
    made += [
        PagedConverter(extractor, order)
        for extractor in PAGE_EXTRACTORS
        if extractor.load() is not None and extractor.place is not None
    ]
    return made


def named(reader: object) -> str:
    return str(reader.name)  # type: ignore[attr-defined]


def readers() -> list[object]:
    """Every converter that claims PDFs, installed or not.

    Parametrised over the registry rather than named, so a converter somebody
    adds is measured by this without the file being edited -- the same reason
    the conformance suite is built that way.
    """
    return [c for c in known_converters() if PDF in getattr(c, "media_types", ())]


def text_read(converter: object, made: bytes) -> str | None:
    """What this converter reads, or ``None`` if it refuses."""
    got = converter.convert(made, PDF)  # type: ignore[attr-defined]
    return got.text if isinstance(got, Converted) else None


def names() -> list[str]:
    return [c.name for c in readers()]  # type: ignore[attr-defined]


def ids(case: tuple[str, bytes, str, str]) -> str:
    return case[0]


# -- the population, first --------------------------------------------------


def test_there_is_something_to_measure() -> None:
    """A suite parametrised over an empty registry is green and measures
    nothing. `pdf_text@1` is always here; `pdfium@1` is here when the extra
    is installed, and its absence is a smaller measurement rather than none."""
    assert "pdf_text@1" in names()


def test_there_is_more_than_one_strategy_to_choose_between() -> None:
    """A registry with one entry is a setting with nothing to set."""
    assert set(STRATEGIES) >= {"columns", "rows"}


# -- the guard the last version of this file did not have -------------------


@pytest.mark.parametrize("case", LAYOUTS, ids=ids)
def test_every_stated_answer_is_reachable_by_some_strategy(
    case: tuple[str, bytes, str, str],
) -> None:
    """**The most important test here.**

    A fixture states a correct reading. Nothing checked that the correct
    reading was *in the fixture*, and two of the three were not:

    - the table put its second column one row too high, so `Mass` sat above
      `Item` rather than beside it and `TABLE_READ` described a grid the file
      did not contain;
    - the third layout was three ASCII runs side by side whose answer was the
      rightmost first, as 縦書き reads. The script that would have said so had
      been removed on purpose -- vertical Japanese needs a composite font,
      which `pdf_text@1` refuses -- and removing it removed the only evidence
      for the answer.

    Both stated a target no correct reader could reach. A test asserting that
    musubi gets a layout wrong passes just as happily when the layout is
    impossible, which makes it a red that is red about nothing: it can never
    go green, so it never tells anybody anything.

    So this asserts the other direction. If **no** strategy reaches the stated
    answer, either musubi is missing one or the fixture is wrong, and a person
    should find out which.
    """
    _, made, answer, _ = case
    reached = {
        f"{order}/{named(reader)}": text_read(reader, made)
        for order in sorted(STRATEGIES)
        for reader in ordering(order)
    }
    assert any(read is not None and read.strip() == answer for read in reached.values()), (
        f"no reading order reaches this answer. want: {answer!r}; got "
        + "; ".join(f"{where}: {read!r}" for where, read in reached.items())
    )


# -- the strategy that is supposed to reach each one ------------------------


@pytest.mark.parametrize("case", LAYOUTS, ids=ids)
def test_the_strategy_for_this_layout_reads_it_correctly(
    case: tuple[str, bytes, str, str],
) -> None:
    """A bound, not a score. A setting the owner asked for and got half of is
    worse than one that was never offered: they believe the corpus is in
    reading order and it is not."""
    _, made, answer, order = case
    for reader in ordering(order):
        assert text_read(reader, made) == answer + "\n", f"{named(reader)} did not"


# -- and what the file's own order still does, which is the default ---------


@pytest.mark.parametrize("converter", readers(), ids=names())
def test_a_two_column_page_is_not_read_in_reading_order_by_default(
    converter: object,
) -> None:
    """The concrete case #85 names, still true of the default.

    A producer laying out by baseline writes the left cell of a line, then the
    right cell of the same line. Reading order is column by column. Every
    offset still resolves, coverage is unchanged, and the prose is not in the
    document -- which is the whole difference between *converted* and
    *converted correctly*. `pdf-reading-order = "columns"` is the answer, and
    it is off until somebody asks for it ([ADR-0042]).
    """
    read = text_read(converter, two_columns())
    assert read is not None, "the page has a text layer"
    assert read.strip() != COLUMNS_READ

    for column in COLUMNS:
        for line in column:
            assert line in read
    assert read.index(COLUMNS[1][0]) < read.index(COLUMNS[0][1]), (
        "the right column's first line arrives before the left column's second"
    )


@pytest.mark.parametrize("converter", readers(), ids=names())
def test_a_table_written_by_column_is_not_read_by_row_by_default(converter: object) -> None:
    """A table emitted cell by cell down each column. Reading order is by row,
    so stream order pairs `Item` with `Tent` rather than with `Mass`."""
    read = text_read(converter, a_table())
    assert read is not None

    assert read.strip() != TABLE_READ
    assert read.index(TABLE[1][0]) < read.index(TABLE[0][1]), (
        "the second row's first cell arrives before the first row's second cell"
    )


def test_changing_the_reading_order_changes_the_converter_name() -> None:
    """Otherwise an incremental sync reuses every document it already has.

    Reuse is keyed on the source hash and the converter name
    (`application/pipeline.py`, [ADR-0036]). Reading in a different order
    produces different text under the same name, so the setting would change
    nothing until every source file happened to be edited -- and the corpus
    would keep an order its settings no longer ask for, with the manifest
    naming the converter that did not produce it.
    """
    assert PdfConverter().name == "pdf_text@1"
    assert PdfConverter(reading_order_name="columns").name == "pdf_text@1+columns"
    assert PdfConverter(reading_order_name="rows").name == "pdf_text@1+rows"


def test_an_unknown_reading_order_is_refused_where_the_settings_are_read() -> None:
    """And not silently on the first PDF of a long run, and never by falling
    back to stream order -- which would build the corpus the way its owner
    explicitly asked it not to be built."""
    with pytest.raises(KeyError, match="no reading order called"):
        PdfConverter(reading_order_name="colums")


# -- the defect the fixtures found on the way ------------------------------


def test_a_run_placed_by_tm_starts_a_new_line() -> None:
    """`Tm` sets the text matrix absolutely and a great many producers place
    every line with one instead of stepping with `Td`.

    It was not in the list of operators that end a line, so two separately
    placed runs were concatenated with nothing between them. Three runs came
    out as `middlerightleft`: one unbroken word, at full coverage, with every
    offset still resolving to the right page. Words that are not in the
    document, and nothing anywhere saying so.
    """
    read = text_read(PdfConverter(), out_of_order())
    assert read is not None
    assert "middlerightleft" not in read
    assert read.split() == ["middle", "right", "left"], "stream order, but as three words"


# -- the algorithm on its own, with no PDF anywhere -------------------------


def test_columns_reads_down_each_column_then_moves_right() -> None:
    left = [Run("one", 72.0, 720.0), Run("two", 72.0, 704.0)]
    right = [Run("three", 332.0, 720.0), Run("four", 332.0, 704.0)]
    # Interleaved, the way a producer laying out by baseline emits them.
    made = [left[0], right[0], left[1], right[1]]
    assert text_of(columns(made)) == "one\ntwo\nthree\nfour"


def test_rows_reads_across_each_line_then_moves_down() -> None:
    made = [
        Run("Item", 72.0, 720.0),
        Run("Tent", 72.0, 704.0),
        Run("Mass", 272.0, 720.0),
        Run("2.4kg", 272.0, 704.0),
    ]
    assert text_of(rows(made)) == "Item Mass\nTent 2.4kg"


def test_one_column_of_prose_reads_the_same_either_way() -> None:
    """What makes `columns` safe on an ordinary page. A document with one
    column is one cluster, and one cluster read down is what `rows` gives --
    so the setting cannot scramble a page that has no columns in it."""
    made = [Run("first", 72.0, 720.0), Run("second", 72.0, 704.0), Run("third", 72.0, 688.0)]
    assert text_of(columns(made)) == text_of(rows(made)) == "first\nsecond\nthird"


def test_a_baseline_nudged_within_the_tolerance_is_still_one_line() -> None:
    """A superscript or a mid-line font change moves a baseline by a point.
    Compared exactly, that is a new line and a footnote marker becomes its own
    paragraph."""
    made = [Run("mass", 72.0, 720.0), Run("2", 100.0, 720.0 + BASELINE_TOLERANCE - 0.5)]
    assert text_of(rows(made)) == "mass 2"


def test_a_gap_narrower_than_the_column_gap_is_not_a_column() -> None:
    """The other side of the same threshold: an indented first line is not a
    column of its own."""
    made = [
        Run("An indented opening", 72.0 + COLUMN_GAP - 1, 720.0),
        Run("and the rest of it", 72.0, 704.0),
    ]
    assert text_of(columns(made)) == "An indented opening\nand the rest of it"


def test_a_strategy_with_nothing_to_order_returns_nothing() -> None:
    """Rather than raising on `floors[0]`, which is what an empty page would
    have reached."""
    assert columns([]) == []
    assert rows([]) == []
    assert text_of([]) == ""


def test_the_file_s_own_order_is_not_one_of_the_geometric_strategies() -> None:
    """`stream` is the absence of a geometric decision rather than one of
    them, and the converter answers it without reading a coordinate -- which
    is what keeps the default path the code it has always been."""
    assert "stream" not in STRATEGIES
    with pytest.raises(KeyError):
        strategy_named("stream")


# -- a composite font, which is now refused rather than mangled -------------


def test_a_composite_font_is_refused_rather_than_read_as_glyph_numbers() -> None:
    """The defect these fixtures found.

    Under `Type0` / `Identity-H` a shown string holds **glyph indices**, and the
    map to characters is in a `ToUnicode` CMap this converter does not read. It
    read them as characters anyway and wrote the font's internal numbering --
    NUL bytes included -- into a corpus document at full coverage, with nothing
    saying so.

    This is how every PDF holding Japanese encodes its text, and how most
    current producers encode a subsetted Latin font. It is not an edge case,
    and it is why the third reading-order fixture could not be set in Japanese.
    """
    refused = PdfConverter().convert(composite(), PDF)
    assert isinstance(refused, Unconvertible)
    assert refused.reason == "composite_font"
    assert "musubi[pdf]" in refused.detail, "a refusal that names no way forward is a dead end"


def test_the_refusal_is_what_stops_the_glyph_numbers_reaching_a_document() -> None:
    """Potency: without the refusal, this is what the corpus would hold.

    Asserted on the fixture's own bytes rather than on the converter, so the
    test still says what the damage was after the converter stops doing it.
    """
    from musubi.infrastructure.converters.pdf import _text_of

    stream = b"BT /F1 12 Tf 72 720 Td <0024002500260027> Tj ET"
    assert _text_of(stream, -180.0) == "\x00$\x00%\x00&\x00'"
    assert "\x00" in _text_of(stream, -180.0), "NUL bytes, into a text document"


# -- and the refusal that was already right ---------------------------------


@pytest.mark.parametrize("converter", readers(), ids=names())
def test_a_page_with_no_text_layer_stays_a_refusal(converter: object) -> None:
    """#85's last fixture: the scan must not quietly become an empty document.

    An empty document has 100% traceable coverage over no characters, which is
    the shape [ADR-0033] found reads as success. A refusal says what happened.
    """
    assert text_read(converter, scanned()) is None
