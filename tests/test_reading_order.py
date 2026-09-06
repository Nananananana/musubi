"""Did it read the document, rather than did it read at all.

`traceable_coverage` says an offset resolves. `answer_width` says how tightly.
The conformance suite says the map is structurally honest. **None of them says
the text is right**, and the `Limits` block has always admitted it in words:

    A traceable character means an offset resolves to a place in the source.
    It does not mean the conversion read the document in the right order.

Saying it is not measuring it (#85). These fixtures have a **stated correct
reading**, so output can be compared against an answer instead of against
whatever the converter did last time.

Two of the tests below assert what musubi gets *wrong*. That is deliberate and
it is not the same as accepting it: a measured limitation nobody has written
down is indistinguishable from one nobody has found, and a test that records
one goes red the day somebody fixes it -- which is exactly when a reader wants
to be told.
"""

from __future__ import annotations

import pytest

from musubi.infrastructure.converters import known_converters
from musubi.ports.converter import Converted, Unconvertible
from pdf_fixtures import (
    COLUMNS,
    COLUMNS_READ,
    TABLE,
    TABLE_READ,
    VERTICAL,
    VERTICAL_READ,
    a_table,
    composite,
    scanned,
    two_columns,
    vertical,
)

PDF = "application/pdf"


def readers() -> list[object]:
    """Every converter that claims PDFs, installed or not.

    Parametrised over the registry rather than named, so a converter somebody
    adds is measured by this without the file being edited -- the same reason
    the conformance suite is built that way.
    """
    return [c for c in known_converters() if PDF in getattr(c, "media_types", ())]


def text_of(converter: object, made: bytes) -> str | None:
    """What this converter reads, or ``None`` if it refuses."""
    got = converter.convert(made, PDF)  # type: ignore[attr-defined]
    return got.text if isinstance(got, Converted) else None


def names() -> list[str]:
    return [c.name for c in readers()]  # type: ignore[attr-defined]


# -- the population, first --------------------------------------------------


def test_there_is_something_to_measure() -> None:
    """A suite parametrised over an empty registry is green and measures
    nothing. `pdf_text@1` is always here; `pdfium@1` is here when the extra
    is installed, and its absence is a smaller measurement rather than none."""
    assert "pdf_text@1" in names()


# -- reading order, which neither reader gets right -------------------------


@pytest.mark.parametrize("converter", readers(), ids=names())
def test_a_two_column_page_is_not_read_in_reading_order(converter: object) -> None:
    """The concrete case #85 names, reproduced and measured.

    A producer laying out by baseline writes the left cell of a line, then the
    right cell of the same line. Reading order is column by column. Every
    offset still resolves, coverage is unchanged, and the prose is not in the
    document -- which is the whole difference between *converted* and
    *converted correctly*.
    """
    read = text_of(converter, two_columns())
    assert read is not None, "the page has a text layer"

    assert read.strip() != COLUMNS_READ, (
        "a converter here now reads two columns in reading order. That is good "
        "news and this test is the wrong shape for it: assert the answer."
    )
    # And what it does instead, so the failure is a measurement rather than a
    # shrug: every line of the document is present, in an order that is not the
    # document's.
    for column in COLUMNS:
        for line in column:
            assert line in read
    assert read.index(COLUMNS[1][0]) < read.index(COLUMNS[0][1]), (
        "the right column's first line arrives before the left column's second"
    )


@pytest.mark.parametrize("converter", readers(), ids=names())
def test_a_table_written_by_column_is_not_read_by_row(converter: object) -> None:
    """A table emitted cell by cell down each column. Reading order is by row,
    so stream order pairs `Item` with `Tent` rather than with `Mass`."""
    read = text_of(converter, a_table())
    assert read is not None

    assert read.strip() != TABLE_READ
    assert read.index(TABLE[1][0]) < read.index(TABLE[0][1]), (
        "the second row's first cell arrives before the first row's second cell"
    )


@pytest.mark.parametrize("converter", readers(), ids=names())
def test_columns_that_run_right_to_left_are_read_left_to_right(converter: object) -> None:
    """The geometry of 縦書き, with the script left out on purpose -- real
    vertical Japanese needs a composite font, which is the next test and a
    different failure."""
    read = text_of(converter, vertical())
    assert read is not None

    assert read.strip() != VERTICAL_READ
    assert read.index(VERTICAL[2]) < read.index(VERTICAL[0]), (
        "the leftmost column arrives first, and it is read last"
    )


# -- a composite font, which is now refused rather than mangled -------------


def test_a_composite_font_is_refused_rather_than_read_as_glyph_numbers() -> None:
    """The defect these fixtures found.

    Under `Type0` / `Identity-H` a shown string holds **glyph indices**, and the
    map to characters is in a `ToUnicode` CMap this converter does not read. It
    read them as characters anyway and wrote the font's internal numbering --
    NUL bytes included -- into a corpus document at full coverage, with nothing
    saying so.

    This is how every PDF holding Japanese encodes its text, and how most
    current producers encode a subsetted Latin font. It is not an edge case.
    """
    from musubi.infrastructure.converters.pdf import PdfConverter

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
    assert text_of(converter, scanned()) is None
