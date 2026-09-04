"""Converters built on somebody else's extractor, with the map recovered.

## Why these exist

musubi's own converters are written rather than borrowed because [ADR-0004]
needs a map and every library in the world returns a string. That decision was
right and it has a cost, and the cost is measurable in two different ways.

**Quality.** Main-content extraction is a research area with published
benchmarks, and a hand-written scan of tags does not win it. `html@1` keeps half
the planted boilerplate on a page `trafilatura` clears entirely.

**Reach.** `pdf_text@1` scans for `N 0 obj`, which cannot find an object that
lives inside a *compressed object stream* -- and that is what a PDF 1.5 file is,
which is what almost every modern producer writes. On one it reports `no_pages`:
correct, and useless.

[ADR-0028] takes the dependency, outside the domain, optional, and pays for it
by recovering the map instead of being handed one.

## Two shapes, because there are two kinds of source

| | Source | Locator | How the map is built |
|---|---|---|---|
| `AlignedConverter` | text | characters | the output is **found in** the source ([ADR-0004]) |
| `PagedConverter` | opaque | pages | one segment per page ([ADR-0025]) |

**Alignment is not a universal bridge, and this is its boundary.** It needs a
source that *is* text. A PDF has no decoded text to point at, so there is
nothing to align against and the honest map is the coarse one -- exactly what
`pdf_text@1` already concluded, and the reason a better extractor changes the
quality of the text without changing what an offset means.

## What an adapter must not do

**No network.** [ADR-0007] is the boundary that makes everything else
checkable, and it does not become negotiable because the code doing the
fetching belongs to somebody else. `tests/test_alignment.py` runs every adapter
with the socket module broken.

**No import at import time.** A missing extra is a converter that is not
registered, never an `ImportError` from `import musubi`. `unavailable()` says
which are missing and what to install, and `musubi config` prints it.

## What is here

| Adapter | Extra | Licence | What it is for |
|---|---|---|---|
| `trafilatura@1` | `musubi[html]` | Apache-2.0 | main-content extraction that wins its benchmarks |
| `pdfium@1` | `musubi[pdf]` | BSD-3-Clause | Chrome's PDF engine: object streams, real fonts |

Only permissively licensed extractors are adapted. `PyMuPDF` is the fastest PDF
reader in Python and is AGPL-3.0; a library whose users vendor it into their own
products cannot hand them that, and an extra is still a dependency the user
ends up shipping.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ...domain.alignment import align
from ...domain.span import Span
from ...domain.text import decode
from ...domain.trace import OPAQUE, Kind, Segment, TraceMap
from ...ports.converter import Converted, Converter, Unconvertible

__all__ = [
    "PAGE_EXTRACTORS",
    "TEXT_EXTRACTORS",
    "AlignedConverter",
    "Extractor",
    "PageExtractor",
    "PagedConverter",
    "TextExtractor",
    "adapters",
    "available",
    "unavailable",
]


@dataclass(frozen=True, slots=True)
class TextExtractor:
    """Somebody else's `str -> str`, for a format whose source *is* text.

    `load` returns the extraction function or ``None`` when the dependency is
    absent. Called at registration and again whenever `musubi config` is asked,
    so installing an extra takes effect without anything being re-imported.
    """

    name: str
    media_types: tuple[str, ...]
    extra: str
    licence: str
    load: Callable[[], Callable[[str], str | None] | None]


@dataclass(frozen=True, slots=True)
class PageExtractor:
    """Somebody else's `bytes -> pages of text`, for a format that is not text.

    There is nothing to align against, so the locator is a page ([ADR-0025]) and
    the map is the same one `pdf_text@1` builds. What a better extractor buys
    here is the text inside the segment, never the meaning of the offsets.
    """

    name: str
    media_types: tuple[str, ...]
    extra: str
    licence: str
    load: Callable[[], Callable[[bytes], list[str]] | None]


#: Either kind. A union rather than a protocol: the two differ only in what
#: their `load` returns, and a protocol would have to leave that field out to
#: cover both -- which is the one field a caller listing them wants to call.
type Extractor = TextExtractor | PageExtractor


class AlignedConverter:
    """Satisfies :class:`~musubi.ports.converter.Converter` by aligning.

    The source is decoded by musubi ([ADR-0018]: the map's offsets are
    characters of *this* decoding, and the encoding is recorded beside it), the
    extractor is handed the decoded text, and the result is aligned back against
    it. An extractor that returns nothing is a refusal with a reason, exactly as
    a scanned PDF is.
    """

    def __init__(self, extractor: TextExtractor) -> None:
        self._extractor = extractor
        self.name = extractor.name
        self.media_types = extractor.media_types

    def convert(self, content: bytes, media_type: str) -> Converted | Unconvertible:
        extract = self._extractor.load()
        if extract is None:  # pragma: no cover - unregistered when absent
            return Unconvertible("extractor_missing", f"install {self._extractor.extra}", self.name)
        try:
            decoded = decode(content)
        except ValueError as error:
            return Unconvertible("undecodable", str(error), self.name)

        try:
            text = extract(decoded.text)
        except Exception as error:
            return Unconvertible("unreadable", _blame(error), self.name)

        if not text or not text.strip():
            return Unconvertible(
                "no_main_content",
                f"{self._extractor.name} found nothing it would call content",
                self.name,
            )

        body = text if text.endswith("\n") else text + "\n"
        aligned = align(decoded.text, body)
        return Converted(
            text=body,
            trace=aligned.trace,
            converter=self.name,
            source_encoding=decoded.codec,
            source_bom_bytes=decoded.bom_length,
        )


class PagedConverter:
    """Satisfies :class:`~musubi.ports.converter.Converter`, page by page.

    The same map `pdf_text@1` produces and for the same reasons: one
    `transformed` segment per page, `src` a half-open range of page indices, and
    `source_unit` `opaque` ([ADR-0025]). So a corpus can be rebuilt with a better
    extractor and every citation still says *page three*.
    """

    def __init__(self, extractor: PageExtractor) -> None:
        self._extractor = extractor
        self.name = extractor.name
        self.media_types = extractor.media_types

    def convert(self, content: bytes, media_type: str) -> Converted | Unconvertible:
        read = self._extractor.load()
        if read is None:  # pragma: no cover - unregistered when absent
            return Unconvertible("extractor_missing", f"install {self._extractor.extra}", self.name)

        try:
            pages = read(content)
        except Exception as error:
            return Unconvertible("unreadable", _blame(error), self.name)

        body: list[str] = []
        segments: list[Segment] = []
        at = 0
        for index, text in enumerate(pages):
            # LF, whatever the extractor returned: `pdfium` reports CRLF, and a
            # corpus whose line endings depend on which library built it is a
            # corpus whose hashes do ([ADR-0003]).
            page = text.replace("\r\n", "\n").replace("\r", "\n").strip()
            if not page:
                continue
            piece = page + "\n"
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

        if not pages:
            return Unconvertible("no_pages", "no pages were found in the file", self.name)
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
            # No decoding happened on the way in, so there is no character
            # offset for a caller to turn into a byte offset, and claiming an
            # encoding would invite one to try.
            source_encoding="",
            source_bom_bytes=0,
        )


def _blame(error: Exception) -> str:
    """Name the failure without letting it out.

    Broad catching is deliberate. A third-party parser handed an arbitrary file
    raises whatever it likes -- and [ADR-0008] wants a run that stops on a
    credential and *keeps going* past a file it cannot read. A refusal carrying
    a reason is the value that does that; an exception escaping an adapter would
    take the whole sync with it, over one bad file in a folder of thousands.
    """
    return f"{type(error).__name__}: {error}"


def _trafilatura() -> Callable[[str], str | None] | None:
    try:
        import trafilatura
    except ImportError:
        return None

    def extract(html: str) -> str | None:
        # `favor_precision` because a corpus is read by a model: a paragraph of
        # navigation that got through is a paragraph the model will answer from.
        #
        # No `url=`. Passing one lets the library reason about the site, and
        # musubi has no url to pass -- it read a file (ADR-0007).
        result: str | None = trafilatura.extract(
            html,
            favor_precision=True,
            include_comments=False,
            include_tables=True,
            output_format="txt",
        )
        return result

    return extract


def _pdfium() -> Callable[[bytes], list[str]] | None:
    try:
        import pypdfium2  # type: ignore[import-untyped]
    except ImportError:
        return None

    def pages(content: bytes) -> list[str]:
        document = pypdfium2.PdfDocument(content)
        try:
            found: list[str] = [page.get_textpage().get_text_range() for page in document]
        finally:
            document.close()
        return found

    return pages


TEXT_EXTRACTORS: tuple[TextExtractor, ...] = (
    TextExtractor(
        name="trafilatura@1",
        media_types=("text/html", "application/xhtml+xml"),
        extra="musubi[html]",
        licence="Apache-2.0",
        load=_trafilatura,
    ),
)

PAGE_EXTRACTORS: tuple[PageExtractor, ...] = (
    PageExtractor(
        name="pdfium@1",
        media_types=("application/pdf",),
        extra="musubi[pdf]",
        licence="BSD-3-Clause",
        load=_pdfium,
    ),
)

EXTRACTORS: tuple[Extractor, ...] = (*TEXT_EXTRACTORS, *PAGE_EXTRACTORS)


def adapters() -> tuple[Converter, ...]:
    """One converter per installed extractor, of whichever shape it needs."""
    made: list[Converter] = [AlignedConverter(e) for e in TEXT_EXTRACTORS if e.load() is not None]
    made += [PagedConverter(e) for e in PAGE_EXTRACTORS if e.load() is not None]
    return tuple(sorted(made, key=lambda c: c.name))


def available() -> tuple[Extractor, ...]:
    """The adapters whose dependency is installed, in a stable order."""
    return tuple(sorted((e for e in EXTRACTORS if e.load() is not None), key=lambda e: e.name))


def unavailable() -> tuple[Extractor, ...]:
    """The adapters whose dependency is not, so a report can say what to do."""
    return tuple(sorted((e for e in EXTRACTORS if e.load() is None), key=lambda e: e.name))
