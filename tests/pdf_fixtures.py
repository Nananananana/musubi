"""PDFs built by hand, so that what is being tested is known exactly.

Not a helper of convenience. A PDF collected from somewhere is a PDF whose
contents nobody can state, and every number measured on one is a number with a
shrug attached. These are written byte by byte, so a test can say *this file
holds two pages and the second has no text layer* and be right.

There are two, and the difference between them is the whole case for
[ADR-0028]'s PDF half:

- `classic()` is PDF 1.4 with the objects at the top level, the shape
  `pdf_text@1` was written against and reads correctly;
- `modern()` is PDF 1.5 with the catalogue, page tree and page inside a
  **compressed object stream**, reached through a cross-reference stream. This
  is what almost every current producer emits, and `pdf_text@1` -- which scans
  for `N 0 obj` -- cannot see an object that is not at the top level. It reports
  `no_pages`, correctly and uselessly.

`tools/pdf_coverage.py` imports these rather than keeping a second copy, because
two fixtures that are supposed to be the same file and are not is a worse
problem than an unusual import.
"""

from __future__ import annotations

import io
import struct
import zlib

__all__ = [
    "COLUMNS",
    "COLUMNS_READ",
    "FIRST_LINE",
    "OUT_OF_ORDER",
    "OUT_OF_ORDER_READ",
    "SECOND_LINE",
    "TABLE",
    "TABLE_READ",
    "a_table",
    "classic",
    "composite",
    "modern",
    "out_of_order",
    "scanned",
    "two_columns",
]

FIRST_LINE = "The gear list"
SECOND_LINE = "A tent that weighs 2.4kg"

_CONTENT = (
    b"BT /F1 12 Tf 72 720 Td (" + FIRST_LINE.encode() + b") Tj "
    b"0 -14 Td (" + SECOND_LINE.encode() + b") Tj ET"
)


def _stream(body: bytes) -> bytes:
    return b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream"


def classic() -> bytes:
    """PDF 1.4, every object at the top level, one page with a text layer."""
    return _assembled(
        {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            3: (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
                b"/Resources << /Font << /F1 5 0 R >> >> >>"
            ),
            4: _stream(_CONTENT),
            5: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        }
    )


def scanned() -> bytes:
    """PDF 1.4 with a page and no text at all: the refusal case."""
    return _assembled(
        {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>",
            4: _stream(b"q 612 0 0 792 0 0 cm /Im0 Do Q"),
        }
    )


def _assembled(objects: dict[int, bytes]) -> bytes:
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number, body in objects.items():
        offsets[number] = out.tell()
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    table = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for number in sorted(objects):
        out.write(b"%010d 00000 n \n" % offsets[number])
    out.write(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, table)
    )
    return out.getvalue()


def modern() -> bytes:
    """PDF 1.5: the page lives inside a compressed object stream.

    An `/ObjStm` holds several objects concatenated, prefixed by a header of
    `number offset` pairs, and the whole thing is Flate-compressed. Nothing in
    it is findable by scanning for `N 0 obj`, because none of it is written that
    way. A cross-reference *stream* -- rows of
    `(type, offset-or-container, generation-or-index)` -- is how a reader is
    meant to find them, and following it needs a parser rather than a scan.
    """
    inside = {
        2: b"<< /Type /Catalog /Pages 3 0 R >>",
        3: b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        4: (
            b"<< /Type /Page /Parent 3 0 R /MediaBox [0 0 612 792] /Contents 5 0 R "
            b"/Resources << /Font << /F1 7 0 R >> >> >>"
        ),
    }
    pairs: list[bytes] = []
    bodies: list[bytes] = []
    at = 0
    for number, body in inside.items():
        pairs.append(b"%d %d" % (number, at))
        bodies.append(body)
        at += len(body) + 1
    header = b" ".join(pairs) + b"\n"
    packed = zlib.compress(header + b"\n".join(bodies) + b"\n")

    out = io.BytesIO()
    out.write(b"%PDF-1.5\n")
    offsets: dict[int, int] = {}

    offsets[1] = out.tell()
    out.write(
        b"1 0 obj\n<< /Type /ObjStm /N %d /First %d /Length %d /Filter /FlateDecode >>\nstream\n"
        % (len(inside), len(header), len(packed))
        + packed
        + b"\nendstream\nendobj\n"
    )
    offsets[5] = out.tell()
    out.write(b"5 0 obj\n" + _stream(_CONTENT) + b"\nendobj\n")
    offsets[7] = out.tell()
    out.write(b"7 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    table = out.tell()
    rows: dict[int, tuple[int, int, int]] = {
        0: (0, 0, 65535),
        1: (1, offsets[1], 0),
        2: (2, 1, 0),
        3: (2, 1, 1),
        4: (2, 1, 2),
        5: (1, offsets[5], 0),
        6: (1, table, 0),
        7: (1, offsets[7], 0),
    }
    data = b"".join(struct.pack(">BIH", *rows[number]) for number in sorted(rows))
    index = b" ".join(b"%d 1" % number for number in sorted(rows))
    packed_rows = zlib.compress(data)
    out.write(
        b"6 0 obj\n<< /Type /XRef /Size %d /Index [%s] /W [1 4 2] /Root 2 0 R "
        b"/Filter /FlateDecode /Length %d >>\nstream\n"
        % (len(rows), index, len(packed_rows))
        + packed_rows
        + b"\nendstream\nendobj\n"
    )
    out.write(b"startxref\n%d\n%%%%EOF\n" % table)
    return out.getvalue()


# -- fixtures whose right answer is written down ----------------------------
#
# Everything above answers *did it read at all*. These answer *did it read the
# document*, which is a different question and the one nothing in this
# repository could ask ([ADR-0039], #85).
#
# Each one states its correct reading as a constant, so a test compares output
# against an answer rather than against whatever the converter did last time.
# A fixture whose right answer nobody can state measures nothing.

#: A two-column page, and the order a person reads it in.
COLUMNS: tuple[tuple[str, ...], tuple[str, ...]] = (
    ("Tents and poles", "weigh two point four", "kilograms in total"),
    ("Stoves and fuel", "weigh one point one", "kilograms in total"),
)

#: What a reader of `two_columns()` gets: the left column, then the right.
COLUMNS_READ = "\n".join((*COLUMNS[0], *COLUMNS[1]))

#: A three-by-two table, as rows.
TABLE: tuple[tuple[str, str], ...] = (
    ("Item", "Mass"),
    ("Tent", "2.4kg"),
    ("Stove", "1.1kg"),
)

#: What a reader of `a_table()` gets: each row, left cell then right.
TABLE_READ = "\n".join(f"{left} {right}" for left, right in TABLE)

#: Three runs on one baseline, whose stream order is not their page order.
#:
#: **This fixture used to state an answer it did not contain.** It was called
#: `VERTICAL` and its answer was the rightmost run first, as 縦書き reads. The
#: text was ASCII on purpose -- real vertical Japanese needs a composite font,
#: which `composite()` below is about and which `pdf_text@1` refuses -- and
#: removing the script removed the only evidence that the columns ran right to
#: left. Three runs side by side are three runs side by side, whichever way the
#: script goes; nothing in those coordinates says which.
#:
#: So it stated a target no correct reader could reach from these bytes. That
#: is the same mistake its own first draft made and recorded one paragraph
#: further down -- an answer the fixture wanted rather than one the fixture
#: gave -- and [ADR-0042] has the whole of it. The real 縦書き case is filed
#: rather than faked.
#:
#: What is left is a case worth having: page order is left to right, stream
#: order is not, so a reader that takes the strings as it meets them gets this
#: wrong and geometry gets it right.
OUT_OF_ORDER: tuple[str, ...] = ("left", "middle", "right")

#: What a reader of `out_of_order()` gets: left to right across the page,
#: and **one line**, because one baseline is one line. Three runs sharing a
#: baseline are three parts of the same line of text, whatever order the
#: stream showed them in.
OUT_OF_ORDER_READ = " ".join(OUT_OF_ORDER)


def _shown(text: str) -> bytes:
    """One string, as a PDF literal, in the encoding a simple font uses."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return b"(" + escaped.encode("utf-8") + b") Tj"


def two_columns() -> bytes:
    """Two columns, written **across the page** the way a typesetter lays them.

    The content stream places the left cell of a line, then the right cell of
    the same line, then moves down. That is what a producer emitting by
    baseline writes, and it is why reading order is not stream order: a scanner
    that takes the strings in the order it meets them interleaves the columns
    and produces prose that is not in the document.

    The coordinates say which column each run is in, and that is the whole of
    the information a correct reader needs. `COLUMNS_READ` is the answer.
    """
    lines = [b"BT /F1 12 Tf 72 720 Td"]
    for row, (left, right) in enumerate(zip(*COLUMNS, strict=True)):
        if row:
            lines.append(b"-260 -16 Td")
        lines.append(_shown(left))
        lines.append(b"260 0 Td")
        lines.append(_shown(right))
    lines.append(b"ET")
    return _paged(b" ".join(lines))


def a_table() -> bytes:
    """A table written **column by column**, which is the other way round.

    A producer that emits a table cell by cell down each column writes every
    `Item`, then every `Mass`. Reading order is by row, so a scanner that takes
    stream order pairs the wrong cells: `TABLE_READ` is the answer, and stream
    order gives the headers of one column followed by the headers of the next.
    """
    lines = [b"BT /F1 12 Tf 72 720 Td"]
    for column, cells in enumerate(zip(*TABLE, strict=True)):
        if column:
            # Back to the **top** row, which is `len(TABLE) - 1` steps up and
            # not `len(TABLE)`. It was the latter, so every cell of the second
            # column sat one row above the cell it was meant to be beside:
            # `Mass` over `Item` rather than next to it, and `2.4kg` level with
            # `Item`. Read by baseline that gives `Mass / Item 2.4kg / Tent
            # 1.1kg / Stove`, so `TABLE_READ` was an answer this grid could not
            # produce however well a reader read it ([ADR-0042]).
            lines.append(b"200 %d Td" % (16 * (len(TABLE) - 1)))
        for row, cell in enumerate(cells):
            if row:
                lines.append(b"0 -16 Td")
            lines.append(_shown(cell))
    lines.append(b"ET")
    return _paged(b" ".join(lines))


#: Where each run sits, and the order the stream shows them in. Written out
#: rather than derived, so that the two orders are visibly not the same.
_OUT_OF_ORDER_AT: tuple[tuple[str, int], ...] = (("middle", 300), ("right", 400), ("left", 200))


def out_of_order() -> bytes:
    """Three runs on one baseline, shown in an order that is not their order.

    Nothing stops a producer emitting the middle of a line first, and the
    coordinates are the only thing that says otherwise. `OUT_OF_ORDER_READ` is
    the answer and it is **reachable**: left to right by x, which is what any
    of the geometric strategies gives and what stream order does not.
    """
    lines = [b"BT /F1 12 Tf"]
    for text, x in _OUT_OF_ORDER_AT:
        lines.append(b"1 0 0 1 %d 720 Tm" % x)
        lines.append(_shown(text))
    lines.append(b"ET")
    return _paged(b" ".join(lines))


def composite() -> bytes:
    """A page whose font is `Type0` / `Identity-H`: the CJK and subset-font case.

    **There is no right answer to state, and that is the point.** Under a
    composite font a shown string holds *glyph indices*, and the map from those
    to characters is in the font's `ToUnicode` CMap. A reader without the CMap
    has no way to know what the page says -- so the only correct behaviour is
    to say so.

    `pdf_text@1` did not. It read the indices as characters and produced
    `NUL $ NUL % NUL & NUL '` -- the font's internal numbering, with NUL bytes,
    written into a corpus document at full coverage ([ADR-0039]). This fixture
    is what found that.
    """
    return _assembled(
        {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            3: (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
                b"/Resources << /Font << /F1 5 0 R >> >> >>"
            ),
            4: _stream(b"BT /F1 12 Tf 72 720 Td <0024002500260027> Tj ET"),
            5: (
                b"<< /Type /Font /Subtype /Type0 /BaseFont /KozMinPr6N-Regular "
                b"/Encoding /Identity-H /DescendantFonts [6 0 R] /ToUnicode 7 0 R >>"
            ),
            6: b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /KozMinPr6N-Regular >>",
            7: _stream(b"(a ToUnicode CMap no scanner reads)"),
        }
    )


def _paged(content: bytes) -> bytes:
    """One PDF 1.4 page holding this content stream."""
    return _assembled(
        {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            3: (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
                b"/Resources << /Font << /F1 5 0 R >> >> >>"
            ),
            4: _stream(content),
            5: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        }
    )
