"""PDF, where there is no decoded text to point at and the locator has to change.

Every other converter's map counts characters on both sides, because a Markdown
file *is* text and an HTML file is text with markup in it. A PDF is neither. Its
words live inside content streams that are usually Flate-compressed, so **there
is no byte range in the file containing the sentence you are reading** — and a
`src` offset counted in characters of "the decoded text" would be counted in
something that does not exist.

So the locator is a **page**, and `source_unit` says `opaque` rather than
`characters` ([ADR-0018] anticipated this; [ADR-0025] is what makes it composable).
`src` is a half-open range of page indices: `[2:3]` is page three, and a range
that crosses a page break is `[2:4]`.

**Page, and not page-plus-offset.** Musubi could report a character offset within
its own extraction of a page, and it would be reproducible only by musubi — a
reader holding the PDF cannot count to character 47 of a page, because what
"character 47" means depends on the order this file chose to walk the text
operators. *Page three* is a claim a person can check by opening the PDF. That is
the whole difference, and it is why the coarser answer is the honest one.

**Every segment is `transformed`, never `verbatim`.** A verbatim claim means the
correspondence holds at every interior offset, and inside a page it does not
hold anywhere: the text was assembled from operators, not sliced out of a
string. `transformed` says the correspondence holds at the ends of the run and
nowhere inside, which is exactly true here.

**A page with no text layer contributes nothing, and a document with no text
layer at all is refused** — `no_text_layer`, a value the manifest reports rather
than an exception somebody catches. A scanned page is not an error; it is a page
this converter cannot read, and saying so is the whole of ADR-0004's bargain.
OCR belongs to a program the owner runs *before* musubi (ADR-0007).

What this does not do is understand a page. No layout model, no column
detection, no font-encoding tables beyond the standard ones: a two-column paper
comes out interleaved, and ligature substitutions come out as whatever the
document's encoding said. ADR-0001 chose this trade deliberately — being wrong
here produces worse *text*, and it cannot produce a wrong *offset*, because the
page a run came from is recorded whatever the text turned out to be.
"""

from __future__ import annotations

import re
import zlib

from ...domain.span import Span
from ...domain.trace import OPAQUE, Kind, Segment, TraceMap
from ...ports.converter import Converted, Unconvertible

__all__ = ["PdfConverter"]

#: `N G obj … endobj`. Scanned for rather than reached through the cross-reference
#: table: a real shelf of PDFs contains files whose xref offsets are wrong, and a
#: scan reads those anyway. The table is an index, and this needs the contents.
_OBJECT = re.compile(rb"(\d+)\s+(\d+)\s+obj\b(.*?)\bendobj", re.S)

#: The stream payload of an object, if it has one.
_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)

#: `/Type /Page` but not `/Type /Pages`, which is the tree node above it.
_PAGE = re.compile(rb"/Type\s*/Page(?![a-zA-Z])")

#: `/Contents 4 0 R`, or `/Contents [4 0 R 5 0 R]`.
_CONTENTS = re.compile(rb"/Contents\s*(\[[^\]]*\]|\d+\s+\d+\s+R)")
_REFERENCE = re.compile(rb"(\d+)\s+\d+\s+R")

#: A string operand: `(literal)` with balanced parens and backslash escapes, or
#: `<48656c6c6f>` in hex.
_LITERAL = re.compile(rb"\((?:\\.|[^()\\]|\((?:\\.|[^()\\])*\))*\)", re.S)
_HEX = re.compile(rb"<([0-9A-Fa-f\s]*)>")

#: The text-showing operators. `TJ` takes an array whose numbers are kerning
#: adjustments and whose strings are the text; `'` and `"` show a string and move
#: to the next line first.
_SHOW = re.compile(
    rb"(?P<array>\[(?:[^\[\]]|\\.)*\])\s*TJ"
    rb"|(?P<literal>\((?:\\.|[^()\\]|\((?:\\.|[^()\\])*\))*\))\s*(?:Tj|'|\")"
    rb"|(?P<hex><[0-9A-Fa-f\s]*>)\s*(?:Tj|'|\")",
    re.S,
)

#: Operators that end a line of text, so the extraction keeps line structure.
_BREAK = re.compile(rb"\b(?:T\*|TD|Td|TL)\b|(?:'|\")")

_ESCAPES = {
    ord("n"): "\n", ord("r"): "\r", ord("t"): "\t", ord("b"): "\b",
    ord("f"): "\f", ord("("): "(", ord(")"): ")", ord("\\"): "\\",
}  # fmt: skip


class PdfConverter:
    """Satisfies :class:`~musubi.ports.converter.Converter`."""

    name = "pdf_text@1"
    media_types: tuple[str, ...] = ("application/pdf",)

    def convert(self, content: bytes, media_type: str) -> Converted | Unconvertible:
        if not content.startswith(b"%PDF-"):
            return Unconvertible(
                "not_a_pdf", "the file does not begin with a PDF header", self.name
            )

        pages = _pages(content)
        if not pages:
            return Unconvertible("no_pages", "no page objects were found in the file", self.name)

        body: list[str] = []
        segments: list[Segment] = []
        at = 0
        for index, page in enumerate(pages):
            text = _text_of(page)
            if not text:
                # A scanned page. It contributes nothing and is not an error;
                # what makes that honest is that the coverage says so.
                continue
            piece = text if text.endswith("\n") else text + "\n"
            segments.append(
                Segment(
                    out=Span(at, at + len(piece)),
                    src=Span(index, index + 1),
                    kind=Kind.TRANSFORMED,
                    rule="pdf.page",
                )
            )
            body.append(piece)
            at += len(piece)

        if not segments:
            return Unconvertible(
                "no_text_layer",
                f"{len(pages)} page(s), none with an extractable text layer",
                self.name,
            )

        return Converted(
            text="".join(body),
            trace=TraceMap(
                segments=tuple(segments),
                artefact_length=at,
                source_length=len(pages),
                source_unit=OPAQUE,
            ),
            converter=self.name,
            # There is no decoding on the way in: the map's source side counts
            # pages, so there is no character offset for a caller to turn into a
            # byte offset, and claiming an encoding would invite one to try.
            source_encoding="",
            source_bom_bytes=0,
        )


def _objects(content: bytes) -> dict[int, bytes]:
    """Every `N 0 obj` in the file, by number, last definition winning.

    Last wins because an incrementally-updated PDF appends new versions of an
    object after the old one, and the later definition is the live one.
    """
    return {int(number): body for number, _, body in _OBJECT.findall(content)}


def _pages(content: bytes) -> list[bytes]:
    """Every page's content, in the order the file puts them.

    Walked through `/Type /Page` in object order rather than through the page
    tree. The tree gives the *reading* order and this gives the *file* order,
    and they agree in every PDF a writer produced normally. Following the tree
    is the better answer and needs a parser for nested dictionaries; ADR-0001
    takes the incomplete one and reports what it did.
    """
    objects = _objects(content)
    pages = []
    for number in sorted(objects):
        body = objects[number]
        if _PAGE.search(body):
            pages.append(_content_of(body, objects))
    return pages


def _content_of(page: bytes, objects: dict[int, bytes]) -> bytes:
    """The decompressed content streams a page points at, joined."""
    found = _CONTENTS.search(page)
    if not found:
        return b""
    streams = []
    for number in _REFERENCE.findall(found.group(1)):
        body = objects.get(int(number))
        if body is None:
            continue
        stream = _STREAM.search(body)
        if stream is None:
            continue
        streams.append(_inflate(stream.group(1), body))
    return b"\n".join(streams)


def _inflate(payload: bytes, header: bytes) -> bytes:
    """Undo `FlateDecode`, or hand back what was there.

    Only Flate. It is what every producer uses, it is in the standard library,
    and a stream in `LZWDecode` or a JBIG2 image is a page this converter
    reports as having no text rather than one it decodes badly.
    """
    if b"/FlateDecode" not in header:
        return payload
    try:
        return zlib.decompress(payload)
    except zlib.error:
        try:
            return zlib.decompressobj().decompress(payload)
        except zlib.error:
            return b""


def _text_of(stream: bytes) -> str:
    """The text a page's content stream shows, with its line breaks kept."""
    if not stream:
        return ""
    out: list[str] = []
    for match in _SHOW.finditer(stream):
        before = stream[: match.start()]
        if out and _BREAK.search(before[-40:]):
            out.append("\n")
        if (array := match.group("array")) is not None:
            out.append(_array(array))
        elif (literal := match.group("literal")) is not None:
            out.append(_literal(literal))
        else:
            out.append(_hex(match.group("hex")))
    return "".join(out).strip()


def _array(body: bytes) -> str:
    """A `TJ` array: its strings joined, its kerning numbers dropped.

    A large negative adjustment is a word space in many producers' output, so a
    threshold turns one into a space. The number is PDF's own convention rather
    than a guess: text-space units are thousandths of the font size, and the
    space PDF writers emit is comfortably past this.
    """
    out: list[str] = []
    for piece in re.finditer(rb"\((?:\\.|[^()\\])*\)|<[0-9A-Fa-f\s]*>|-?\d+(?:\.\d+)?", body):
        token = piece.group()
        if token.startswith(b"("):
            out.append(_literal(token))
        elif token.startswith(b"<"):
            out.append(_hex(token))
        else:
            try:
                if float(token) <= -180 and out and not out[-1].endswith(" "):
                    out.append(" ")
            except ValueError:  # pragma: no cover - the regex admits only numbers
                pass
    return "".join(out)


def _literal(token: bytes) -> str:
    """`(text)` with PDF's backslash escapes, including `\\ddd` octal."""
    raw = token[1:-1]
    out: list[str] = []
    index = 0
    while index < len(raw):
        byte = raw[index]
        if byte != 0x5C:  # backslash
            out.append(chr(byte))
            index += 1
            continue
        index += 1
        if index >= len(raw):
            break
        following = raw[index]
        if following in _ESCAPES:
            out.append(_ESCAPES[following])
            index += 1
        elif 0x30 <= following <= 0x37:  # \ddd, one to three octal digits
            digits = raw[index : index + 3]
            octal = bytes(d for d in digits if 0x30 <= d <= 0x37)
            out.append(chr(int(octal, 8) & 0xFF))
            index += len(octal)
        elif following in (0x0A, 0x0D):  # a line continuation inside a string
            index += 1
        else:
            out.append(chr(following))
            index += 1
    return _decode("".join(out))


def _hex(token: bytes) -> str:
    """`<48656c6c6f>`, and `<48656C6C6F0>` where the last nibble is an implied 0."""
    digits = re.sub(rb"\s", b"", token[1:-1])
    if len(digits) % 2:
        digits += b"0"
    try:
        raw = bytes.fromhex(digits.decode("ascii"))
    except ValueError:  # pragma: no cover - the regex admits only hex
        return ""
    if raw[:2] == b"\xfe\xff":
        return raw[2:].decode("utf-16-be", errors="replace")
    return _decode("".join(chr(b) for b in raw))


def _decode(text: str) -> str:
    """PDFDocEncoding, close enough for the range that differs from Latin-1.

    A font with a custom encoding will produce nonsense here, and that is the
    trade ADR-0001 names: the *text* is worse and the *page* it came from is
    still right, because the page is what the map records.
    """
    return text.translate(_PDFDOC)


#: The eight positions where PDFDocEncoding differs from Latin-1 in a way a real
#: document hits: the quotation marks and dashes producers emit constantly.
_PDFDOC = {
    0x18: "˘", 0x19: "ˇ", 0x1A: "ˆ", 0x1B: "˙",
    0x1C: "˝", 0x1D: "˛", 0x1E: "˚", 0x1F: "˜",
    0x80: "•", 0x81: "†", 0x82: "‡", 0x83: "…",
    0x84: "—", 0x85: "–", 0x86: "ƒ", 0x87: "⁄",
    0x88: "‹", 0x89: "›", 0x8A: "−", 0x8B: "‰",
    0x8C: "„", 0x8D: "“", 0x8E: "”", 0x8F: "‘",
    0x90: "’", 0x91: "‚", 0x92: "™", 0x93: "ﬁ",
    0x94: "ﬂ", 0x95: "Ł", 0x96: "Œ", 0x97: "Š",
    0x98: "Ÿ", 0x99: "Ž", 0x9A: "ı", 0x9B: "ł",
    0x9C: "œ", 0x9D: "š", 0x9E: "ž", 0xA0: "€",
}  # fmt: skip
