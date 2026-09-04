"""Recovering a tiling from a converter that only returned text.

## The problem this exists for

Every document-to-text library in the world has the signature `bytes -> str`.
That is the shape [ADR-0004] cannot use, because the correspondence is the
product, and it is why musubi's own converters were written rather than
borrowed.

It is also why musubi's own converters are worse than the good ones. Boilerplate
removal is a research area with published benchmarks; a hand-written scan of
tags is not competitive with `trafilatura`, and pretending otherwise makes the
guarantee true of text nobody wants.

**Alignment is the bridge.** Hand an external extractor the bytes, take back its
text, and then *find* that text in the source. Where a run of the output occurs
verbatim in the source, the correspondence is recovered exactly and can be
claimed as `verbatim`. Where it does not, it is `transformed` — the ends are
right and the interior is not — or, when the output contributed nothing at all
for a stretch of source, `removal`.

What this buys is not a promise. It is a **measurement**: traceable coverage
comes out of the alignment, so the trade a third-party extractor makes is a
number in the manifest rather than an argument.

## Why not a diff

`difflib.SequenceMatcher` over characters is the obvious tool and is quadratic
in the worst case. Musubi is pointed at folders nobody has audited, and
[ADR-0016] already refuses regular expressions on exactly this ground: a scan
that runs unattended over arbitrary documents must not be able to hang.

Extraction is **order-preserving and local** — an extractor emits a document's
paragraphs in the order the document has them, near where the document has
them — so a forward scan with a bounded window is not an approximation of a
diff, it is the right algorithm for this input. `str.find` is a C-speed
substring search, the window bounds the work per line, and the whole alignment
is linear in the output with a constant that is stated below rather than
discovered.

## What it does not do

It does not reorder. If an extractor emits a page's second column before its
first, the second column aligns and the first does not, and the coverage number
falls. That is the correct outcome: [ADR-0004]'s map is allowed to be
non-monotonic in the source, but *inferring* a reordering from a text match is
guessing, and a wrong guess here points a citation at a confident wrong place.

It does not align below a line. A paragraph containing one resolved entity is
`transformed` whole rather than three segments with the entity in the middle.
Character-level alignment inside a line would recover a few percent of coverage
and is the quadratic thing again.
"""

from __future__ import annotations

from dataclasses import dataclass

from .span import Span
from .trace import Kind, Segment, TraceMap

__all__ = ["MINIMUM_RUN", "WINDOW", "Alignment", "align"]

#: A run shorter than this is not looked for. Short strings occur everywhere by
#: chance -- `and`, a date, a closing bracket -- and a chance hit anchors the
#: scan to the wrong place and costs every line after it. Twelve characters is
#: about two words: long enough that a coincidence is unlikely, short enough
#: that a heading still counts.
MINIMUM_RUN = 12

#: How far ahead of the last match a run is looked for, in characters.
#:
#: The bound is what makes this linear. Without it a line that is *not* in the
#: source costs a scan to the end of the file, and a document whose extraction
#: shares nothing with its source costs the product of the two lengths.
#:
#: 64 kB is far more than any stretch of boilerplate between two paragraphs, and
#: a run that really is further ahead than that is reported as transformed --
#: which is true, just less precise than it could have been.
WINDOW = 64 * 1024


@dataclass(frozen=True, slots=True)
class Alignment:
    """The map, and what the alignment itself had to give up.

    `unmatched_runs` is the number of output lines that were looked for and not
    found. It is not a defect count: entity resolution and whitespace collapsing
    both produce lines that are genuinely not in the source. It is here because
    a coverage number with no denominator behind it invites the reading that the
    extractor was wrong, and usually it was not.
    """

    trace: TraceMap
    matched_runs: int
    unmatched_runs: int


def align(
    source: str,
    output: str,
    *,
    minimum_run: int = MINIMUM_RUN,
    window: int = WINDOW,
) -> Alignment:
    """Find `output`'s lines in `source`, in order, and tile what is left.

    The scan is forward-only: each line is looked for at or after the end of the
    previous match. That is what makes a match evidence rather than a
    coincidence — a string found *behind* where the extractor already was is not
    the occurrence the extractor emitted.
    """
    segments: list[Segment] = []
    at_out = 0
    at_src = 0
    matched = 0
    unmatched = 0

    for start, end in _lines(output):
        line = output[start:end]
        found = -1
        if len(line) >= minimum_run:
            edge = min(len(source), at_src + window)
            found = source.find(line, at_src, edge)
        if found == -1:
            if len(line) >= minimum_run:
                unmatched += 1
            continue

        segments.extend(_between(Span(at_out, start), Span(at_src, found), output))
        # No rule on a verbatim segment: `Segment` refuses one, because nothing
        # happened to it. That is the point of recovering the correspondence
        # rather than describing it -- these characters *are* the source's.
        segments.append(
            Segment(
                out=Span(start, end),
                src=Span(found, found + len(line)),
                kind=Kind.VERBATIM,
            )
        )
        matched += 1
        at_out = end
        at_src = found + len(line)

    segments.extend(_between(Span(at_out, len(output)), Span(at_src, len(source)), output))

    return Alignment(
        trace=TraceMap(
            segments=tuple(segments),
            artefact_length=len(output),
            source_length=len(source),
        ),
        matched_runs=matched,
        unmatched_runs=unmatched,
    )


def _between(out: Span, src: Span, output: str) -> list[Segment]:
    """The segments for a stretch neither side matched.

    Four cases, and telling them apart is the whole value of doing this rather
    than calling everything `transformed`:

    ```text
    output empty, source not   removal      boilerplate. It was there and is gone
    output not, source empty   synthetic    the extractor wrote it
    both                       transformed  the same content, different characters
    neither                    nothing
    ```

    Separating the first two matters most. A paragraph break between two matched
    runs, with four kilobytes of navigation between them in the source, is
    otherwise one `transformed` segment claiming that a newline *is* the
    navigation — which is the reading [ADR-0005] exists to prevent.
    """
    if out.is_empty and src.is_empty:
        return []
    if out.is_empty:
        return [Segment(out=out, src=src, kind=Kind.REMOVAL, rule="align.dropped")]
    if src.is_empty:
        return [Segment(out=out, src=src, kind=Kind.SYNTHETIC, rule="align.inserted")]
    if not out.slice(output).strip():
        return [
            Segment(
                out=Span(out.start, out.start), src=src, kind=Kind.REMOVAL, rule="align.dropped"
            ),
            Segment(
                out=out,
                src=Span(src.end, src.end),
                kind=Kind.SYNTHETIC,
                rule="align.separator",
            ),
        ]
    return [Segment(out=out, src=src, kind=Kind.TRANSFORMED, rule="align.gap")]


def _lines(text: str) -> list[tuple[int, int]]:
    """Every line's span, without its terminator, skipping empty ones.

    Lines rather than paragraphs: a paragraph in the output is one line in every
    extractor musubi has met, and a terminator is exactly the character that is
    *not* in the source, since the source's own break is markup.
    """
    spans: list[tuple[int, int]] = []
    at = 0
    for piece in text.split("\n"):
        end = at + len(piece)
        if piece.strip():
            spans.append((at, end))
        at = end + 1
    return spans
