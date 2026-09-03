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

__all__ = ["FIRST_LINE", "SECOND_LINE", "classic", "modern", "scanned"]

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
