"""PDF: the first converter whose map does not count characters at all.

Every fixture here is a real PDF, assembled byte by byte in `a_pdf()` — objects,
a cross-reference table, a trailer. Not a mock and not a recorded blob: a mock
would let the parser be wrong in exactly the way the mock was wrong, and a
recorded blob would be somebody's document.

What is asserted is mostly the *locator*. A converter that produced beautiful
text and pointed at page four would be worse than one that produced clumsy text
and pointed at page three, because the clumsy text is visible and the wrong page
is not.
"""

from __future__ import annotations

import zlib

import pytest

from musubi.domain.trace import CHARACTERS, OPAQUE, Kind
from musubi.infrastructure.converters.pdf import PdfConverter
from musubi.ports.converter import Converted, Unconvertible


def a_pdf(pages: list[bytes | None], *, compress: bool = True) -> bytes:
    """A real PDF with one object per page. `None` is a page with no text layer."""
    objects: list[tuple[int, bytes]] = []
    kids: list[bytes] = []
    stream_number = 3 + len(pages)
    for index, stream in enumerate(pages):
        number = 3 + index
        kids.append(f"{number} 0 R".encode())
        if stream is None:
            objects.append((number, b"<< /Type /Page /Parent 2 0 R >>"))
            continue
        body = zlib.compress(stream) if compress else stream
        filters = b" /Filter /FlateDecode" if compress else b""
        objects.append(
            (number, f"<< /Type /Page /Parent 2 0 R /Contents {stream_number} 0 R >>".encode())
        )
        objects.append(
            (
                stream_number,
                b"<< /Length "
                + str(len(body)).encode()
                + filters
                + b" >>\nstream\n"
                + body
                + b"\nendstream",
            )
        )
        stream_number += 1

    head = [
        (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        (
            2,
            b"<< /Type /Pages /Kids ["
            + b" ".join(kids)
            + b"] /Count "
            + str(len(pages)).encode()
            + b" >>",
        ),
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number, body in head + sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    start = len(out)
    top = max(offsets) + 1
    out += f"xref\n0 {top}\n0000000000 65535 f \n".encode()
    for number in range(1, top):
        out += f"{offsets.get(number, 0):010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {top} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    return bytes(out)


def shows(text: str) -> bytes:
    """A content stream that shows one line."""
    return b"BT /F1 12 Tf 72 720 Td (" + text.encode("latin-1") + b") Tj ET"


def convert(pdf: bytes) -> Converted:
    result = PdfConverter().convert(pdf, "application/pdf")
    assert isinstance(result, Converted), result
    return result


# -- the locator ------------------------------------------------------------


def test_the_source_is_measured_in_pages_and_says_so() -> None:
    """The whole reason this converter needed a decision. A PDF's words live in
    compressed streams, so there is no byte range in the file holding them and no
    decoded text for a character offset to index into."""
    result = convert(a_pdf([shows("one"), shows("two")]))
    assert result.trace.source_unit == OPAQUE
    assert result.trace.source_unit != CHARACTERS
    assert result.trace.source_length == 2, "two pages, not two characters"


def test_each_page_is_one_segment_pointing_at_that_page() -> None:
    result = convert(a_pdf([shows("first"), shows("second"), shows("third")]))
    assert [(s.src.start, s.src.end) for s in result.trace.segments] == [(0, 1), (1, 2), (2, 3)]


def test_a_page_with_no_text_does_not_renumber_the_pages_after_it() -> None:
    """The failure worth guarding: skipping a scanned page and then reporting
    the next one as page two would send a reader to the wrong page with full
    confidence, which is the one thing a locator must not do."""
    result = convert(a_pdf([shows("one"), None, shows("three")]))

    assert result.text == "one\nthree\n"
    assert [(s.src.start, s.src.end) for s in result.trace.segments] == [(0, 1), (2, 3)]
    assert result.trace.source_length == 3, "the empty page still counts toward the total"


def test_nothing_is_verbatim() -> None:
    """A verbatim claim says the correspondence holds at every interior offset.
    Inside a page it holds nowhere: the text was assembled from operators, not
    sliced out of a string."""
    result = convert(a_pdf([shows("some words")]))
    assert all(s.kind is Kind.TRANSFORMED for s in result.trace.segments)
    assert all(s.rule == "pdf.page" for s in result.trace.segments)


def test_the_map_composes_because_nothing_in_it_is_verbatim() -> None:
    """ADR-0025 in the place it was written for. Before it, this map could not
    reach the cleanser at all -- composition refused any non-character source,
    which was stricter than the arithmetic it was protecting."""
    from musubi.domain.text import normalize_line_endings
    from musubi.domain.trace import TraceMap

    result = convert(a_pdf([shows("page one"), shows("page two")]))
    composed = result.trace.followed_by(TraceMap.of_rewrite(normalize_line_endings(result.text)))

    assert composed.source_unit == OPAQUE, "composition kept the unit it was given"
    assert composed.source_length == 2, "and the page count with it"


# -- the text ---------------------------------------------------------------


def test_a_kerned_array_becomes_spaced_words() -> None:
    """`TJ` takes an array whose numbers are kerning adjustments. A large one is
    how most producers write a space, and dropping them welds words together."""
    stream = b"BT /F1 12 Tf 72 720 Td [(Tent) -250 (design) -250 (memo)] TJ ET"
    assert "Tent design memo" in convert(a_pdf([stream])).text


def test_a_hex_string_is_read_as_a_string() -> None:
    assert "Hello" in convert(a_pdf([b"BT /F1 12 Tf 72 720 Td <48656C6C6F> Tj ET"])).text


def test_octal_and_escaped_parentheses_survive() -> None:
    stream = rb"BT /F1 12 Tf 72 720 Td (\(a\) and \251) Tj ET"
    text = convert(a_pdf([stream])).text
    assert "(a)" in text
    assert "©" in text, "the octal escape named a copyright sign"


def test_an_uncompressed_stream_is_read_too() -> None:
    """Flate is what every producer uses and it is not the only thing that is
    legal, so the path that does no inflating has to work."""
    assert "plain" in convert(a_pdf([shows("plain stream")], compress=False)).text


def test_utf16_text_is_decoded_by_its_mark() -> None:
    body = "ギア".encode("utf-16-be").hex().upper()
    stream = b"BT /F1 12 Tf 72 720 Td <FEFF" + body.encode() + b"> Tj ET"
    assert "ギア" in convert(a_pdf([stream])).text


# -- what it refuses --------------------------------------------------------


def test_a_document_with_no_text_layer_anywhere_is_refused() -> None:
    """Not an error. A scanned page is a page this converter cannot read, and
    the manifest reports it with a reason so the owner can run OCR first."""
    result = PdfConverter().convert(a_pdf([None, None]), "application/pdf")
    assert isinstance(result, Unconvertible)
    assert result.reason == "no_text_layer"
    assert "2 page" in result.detail


def test_something_that_is_not_a_pdf_is_refused_by_its_header() -> None:
    result = PdfConverter().convert(b"# not a pdf\n", "application/pdf")
    assert isinstance(result, Unconvertible)
    assert result.reason == "not_a_pdf"


def test_a_pdf_with_no_pages_is_refused() -> None:
    result = PdfConverter().convert(a_pdf([]), "application/pdf")
    assert isinstance(result, Unconvertible)
    assert result.reason == "no_pages"


def test_a_stream_that_will_not_inflate_is_a_page_without_text() -> None:
    """A stream in a filter this does not implement, or a corrupt one. It is a
    page with no text rather than a crash, and the coverage says so."""
    pdf = a_pdf([shows("readable"), None])
    broken = pdf.replace(b"/FlateDecode", b"/LZWDecode  ", 1)
    result = PdfConverter().convert(broken, "application/pdf")
    assert isinstance(result, Unconvertible)
    assert result.reason == "no_text_layer"


@pytest.mark.parametrize(
    "junk",
    [b"%PDF-1.4\n", b"%PDF-1.4\ngarbage", b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\n"],
)
def test_a_malformed_pdf_is_refused_rather_than_crashing(junk: bytes) -> None:
    result = PdfConverter().convert(junk, "application/pdf")
    assert isinstance(result, Unconvertible), "a broken file is a value, not an exception"


# -- the whole thing --------------------------------------------------------


def test_the_map_holds_over_every_fixture_here() -> None:
    """`TraceMap`'s constructor is the assertion: the segments must tile the
    artefact exactly, with no gap and no overlap, whatever the pages held."""
    fixtures: list[list[bytes | None]] = [
        [shows("a")],
        [shows("a"), shows("b")],
        [None, shows("a"), None, shows("b"), None],
        [b"BT [(x) -400 (y)] TJ ET", shows("z")],
    ]
    for pages in fixtures:
        result = convert(a_pdf(pages))
        assert result.trace.artefact_length == len(result.text)
        covered = 0
        for segment in result.trace.segments:
            assert segment.out.start == covered
            covered = segment.out.end
        assert covered == result.trace.artefact_length
