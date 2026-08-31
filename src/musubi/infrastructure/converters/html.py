"""HTML, where the conversion is lossy for the first time and has to say so.

Markdown and plain text were nearly the identity, which is why they came first
([ADR-0004]): the correct answer at every offset was obvious, so the tiling
machinery could be got right before it was used somewhere the answer is not.

HTML is that somewhere. A page is mostly not the document — navigation, a
cookie banner, a script, a footer of links — and the interesting output is a
minority of the input. So this is the first converter where **traceable
coverage stops being 1.0 by construction and starts being a measurement**.

**Boilerplate is removed as a tiling, not as a gap.** A stripped `<nav>` is a
`removal` segment carrying the rule that removed it, so the account says *what*
was taken and *by which rule* ([ADR-0005]) instead of leaving a hole a reader
would have to guess about. Every character of the source ends up in exactly one
segment: text that survived, text that was taken, or markup that was never text.

**Entities are `transformed`, not `verbatim`.** `&amp;` is five characters of
source and one of output, so a verbatim claim would be a lie the map's own
invariant catches — a verbatim segment must be the same length on both sides.
The correspondence holds at the ends of the run and nowhere inside it, which is
exactly what `transformed` means.

`convert_charrefs` is therefore **off**. With it on, `html.parser` silently
folds entities into the surrounding text and the offsets stop lining up — the
conversion would still produce plausible text, and the map under it would be
wrong. That is the failure this project exists to make impossible, so the
setting is not a preference.

What this does not do is understand a page. There is no readability heuristic,
no boilerplate classifier, no layout model: the rules are a fixed list of
element names, and a `<div class="nav">` is not one of them. ADR-0001's trade
applies — being wrong here produces a worse *selection*, and it cannot produce a
wrong *offset*, because whatever is kept is still reported with where it came
from.
"""

from __future__ import annotations

from html.parser import HTMLParser

from ...domain.span import Span
from ...domain.text import decode, normalize_line_endings
from ...domain.trace import Kind, Segment, TraceMap
from ...ports.converter import Converted, Unconvertible

__all__ = ["BOILERPLATE", "HtmlConverter"]

#: Elements whose text is page furniture rather than the document. Removed with
#: a rule naming the element, so the manifest's account says which one did it.
#: A fixed list and not a classifier: see the module docstring.
#:
#: ``head`` is here because a `<title>` is about the page. musubi does not write
#: a title into an artefact either (`domain/frontmatter.py`): a real note is
#: called 「テント設計メモ」 and a converter that prepended its own guess would be
#: replacing something better with something worse.
BOILERPLATE: frozenset[str] = frozenset(
    {
        "head",  # everything in it is about the page, not the document
        "script", "style", "noscript", "template",
        "nav", "header", "footer", "aside", "form",
    }
)  # fmt: skip

#: Elements after which the text needs a break, or it runs together into one
#: paragraph and every sentence boundary is lost.
BLOCK: frozenset[str] = frozenset(
    {
        "p", "div", "section", "article", "main", "br", "hr",
        "h1", "h2", "h3", "h4", "h5", "h6",
        "ul", "ol", "li", "dl", "dt", "dd",
        "table", "tr", "blockquote", "pre", "figure", "figcaption",
    }
)  # fmt: skip

#: Markdown a heading opens with, so a converted page keeps its structure.
HEADINGS: dict[str, str] = {f"h{n}": "#" * n + " " for n in range(1, 7)}


class _Walk(HTMLParser):
    """Collects one event per construct, each with where it started.

    `HTMLParser` reports position at the *start* of a construct and never its
    end, so an event's source span is taken as running up to the next event's
    start. Every character of the source is therefore inside exactly one event,
    which is what lets the segments account for all of it rather than for the
    parts that happened to be interesting.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.events: list[tuple[int, str, str]] = []
        self._lines: list[int] = []

    def parse(self, text: str) -> list[tuple[int, int, str, str]]:
        """Return ``(start, end, kind, payload)`` covering the whole text."""
        at = 0
        self._lines = [0]
        for line in text.splitlines(keepends=True):
            at += len(line)
            self._lines.append(at)

        self.feed(text)
        self.close()

        spans = []
        for index, (start, kind, payload) in enumerate(self.events):
            end = self.events[index + 1][0] if index + 1 < len(self.events) else len(text)
            spans.append((start, end, kind, payload))
        return spans

    def _at(self) -> int:
        line, column = self.getpos()
        return self._lines[line - 1] + column

    def _record(self, kind: str, payload: str = "") -> None:
        self.events.append((self._at(), kind, payload))

    # -- the constructs ----------------------------------------------------

    def handle_starttag(self, tag: str, attrs: object) -> None:
        self._record("start", tag)

    def handle_startendtag(self, tag: str, attrs: object) -> None:
        self._record("start", tag)
        self._record("end", tag)

    def handle_endtag(self, tag: str) -> None:
        self._record("end", tag)

    def handle_data(self, data: str) -> None:
        self._record("data", data)

    def handle_entityref(self, name: str) -> None:
        self._record("entity", name)

    def handle_charref(self, name: str) -> None:
        self._record("charref", name)

    def handle_comment(self, data: str) -> None:
        self._record("markup")

    def handle_decl(self, decl: str) -> None:
        self._record("markup")

    def handle_pi(self, data: str) -> None:
        self._record("markup")

    def unknown_decl(self, data: str) -> None:
        self._record("markup")


class HtmlConverter:
    """Satisfies :class:`~musubi.ports.converter.Converter`."""

    name = "html@1"
    media_types: tuple[str, ...] = ("text/html", "application/xhtml+xml")

    def convert(self, content: bytes, media_type: str) -> Converted | Unconvertible:
        try:
            decoded = decode(content)
        except ValueError as error:
            return Unconvertible("undecodable", str(error), self.name)

        endings = normalize_line_endings(decoded.text)
        try:
            body, segments = _render(endings.text)
        except (AssertionError, ValueError) as error:  # pragma: no cover - a bug, not an input
            return Unconvertible("unparseable_html", str(error), self.name)

        markup = TraceMap(
            segments=tuple(segments),
            artefact_length=len(body),
            source_length=len(endings.text),
        )
        composed = TraceMap.of_rewrite(endings).followed_by(markup).merged()
        return Converted(
            text=body,
            trace=composed,
            converter=self.name,
            source_encoding=decoded.encoding,
            source_bom_bytes=decoded.bom_length,
        )


def _render(text: str) -> tuple[str, list[Segment]]:
    """The page as text, and one segment per stretch of the source.

    Written as an explicit accumulator rather than by building strings and
    hoping the offsets line up afterwards: every append to the output records
    the source it came from at the same moment, so the two cannot drift.
    """
    out: list[str] = []
    segments: list[Segment] = []
    length = 0
    suppressed: list[str] = []
    between_blocks = True

    def emit(piece: str, src: Span, kind: Kind, rule: str | None = None) -> None:
        nonlocal length
        if not piece and kind is not Kind.REMOVAL:
            kind, rule = Kind.REMOVAL, rule or "markup.dropped"
        out.append(piece)
        segments.append(
            Segment(out=Span(length, length + len(piece)), src=src, kind=kind, rule=rule)
        )
        length += len(piece)

    def synth(piece: str, at: int, rule: str) -> None:
        nonlocal length
        out.append(piece)
        segments.append(
            Segment(
                out=Span(length, length + len(piece)),
                src=Span(at, at),
                kind=Kind.SYNTHETIC,
                rule=rule,
            )
        )
        length += len(piece)

    for start, end, kind, payload in _Walk().parse(text):
        span = Span(start, end)

        if kind == "start":
            if payload in BOILERPLATE:
                suppressed.append(payload)
            emit("", span, Kind.REMOVAL, f"markup.tag.{payload}")
            if not suppressed and payload in HEADINGS:
                synth(HEADINGS[payload], end, f"structure.{payload}")
        elif kind == "end":
            if suppressed and payload == suppressed[-1]:
                suppressed.pop()
            emit("", span, Kind.REMOVAL, f"markup.tag.{payload}")
            if not suppressed and payload in BLOCK:
                synth("\n\n", end, f"structure.{payload}")
                between_blocks = True
        elif kind == "markup":
            emit("", span, Kind.REMOVAL, "markup.dropped")
        elif suppressed:
            emit("", span, Kind.REMOVAL, f"boilerplate.{suppressed[-1]}")
        elif kind == "entity":
            emit(_named(payload, text[start:end]), span, Kind.TRANSFORMED, "entity.reference")
        elif kind == "charref":
            emit(_numeric(payload, text[start:end]), span, Kind.TRANSFORMED, "entity.reference")
        else:
            emit(*_data(payload, span, between_blocks))
            if payload.strip():
                between_blocks = False

    return "".join(out), _collapse(segments)


def _data(payload: str, span: Span, between_blocks: bool) -> tuple[str, Span, Kind, str | None]:
    """Text between tags: kept, dropped as layout, or kept as one space.

    Whitespace is the case that needs the distinction. Between two block
    elements it is in the file to make the markup readable and is not part of
    the document, so it is dropped -- as a removal with a rule rather than a
    gap, so a reader can see it happened.

    **Inside a line it is a word boundary**, and dropping it runs words
    together: `See <a>this</a> &amp; that` became `See this& that` before this
    told the two cases apart. Kept as a single space, which is `verbatim` when
    the source was exactly one and `transformed` when several collapsed.
    """
    if payload.strip():
        return payload, span, Kind.VERBATIM, None
    if between_blocks:
        return "", span, Kind.REMOVAL, "whitespace.between-elements"
    if payload == " ":
        return payload, span, Kind.VERBATIM, None
    return " ", span, Kind.TRANSFORMED, "whitespace.collapsed"


def _named(name: str, written: str) -> str:
    """A named reference as the character it names, or exactly as written.

    Looked up in `html.entities.html5` rather than passed to `html.unescape`,
    and the difference is not cosmetic. `unescape` implements HTML5's
    longest-prefix rule, so `&notarealentity;` comes back as `¬arealentity;` --
    it matches the real entity `&not` and leaves the rest. Applied to a
    reference the parser has already isolated, that **invents a character the
    page does not contain**, which is the one thing the module docstring says
    must not happen.

    An unrecognised name therefore stays as the source wrote it.
    """
    from html.entities import html5

    return html5.get(f"{name};") or html5.get(name) or written


def _numeric(digits: str, written: str) -> str:
    """A numeric reference, or as written when it names nothing.

    Out-of-range and surrogate code points are left alone for the same reason:
    a replacement character here would be musubi's invention sitting in a
    corpus, indistinguishable from one the page really had.
    """
    try:
        point = int(digits[1:], 16) if digits[:1] in "xX" else int(digits)
        return chr(point) if 0 <= point <= 0x10FFFF and not 0xD800 <= point <= 0xDFFF else written
    except ValueError:
        return written


def _collapse(segments: list[Segment]) -> list[Segment]:
    """Drop empty removals that sit inside a longer one.

    `merged()` joins adjacent verbatim runs and deliberately does not touch
    removals, because two removals with different rules answer differently.
    Adjacent removals with the *same* rule answer identically, and a page of
    script produces one per line otherwise.
    """
    collapsed: list[Segment] = []
    for segment in segments:
        last = collapsed[-1] if collapsed else None
        if (
            last is not None
            and last.kind is Kind.REMOVAL
            and segment.kind is Kind.REMOVAL
            and last.rule == segment.rule
            and last.src.end == segment.src.start
        ):
            collapsed[-1] = Segment(
                out=Span(last.out.start, segment.out.end),
                src=Span(last.src.start, segment.src.end),
                kind=Kind.REMOVAL,
                rule=last.rule,
            )
        else:
            collapsed.append(segment)
    return collapsed
