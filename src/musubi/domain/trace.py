"""The tiling: what ADR-0004 actually is, in code.

A converter produces text *and* a map from that text back to the source. The
cleanser produces a second map over that text. The two **compose** into one map
from the artefact somebody will read back to the bytes they actually have, and
that composition is what closes the hole at the bottom of the evidence chain:
a citation into a synced document resolves through every transformation to a
place in the owner's own file.

Two properties are load-bearing.

**The segments tile the artefact exactly.** Every character belongs to exactly
one segment, checked on construction. A map with a gap is a map that will answer
a query with silence, and a map with an overlap is one that will answer twice.

**Composition never claims the stronger of two kinds.** A run that was verbatim
through the cleanser but transformed by the converter did not survive untouched,
and reporting it as verbatim would assert an exactness the pipeline does not
have. Where the earlier stage changed kind in the middle of a run, the run is
*split* rather than degraded whole -- precision is kept where it exists and
given up only where it does not.

Segments are ordered by output offset. Their source ranges need **not** be
monotonic: a two-column page read in reading order produces a map whose source
ranges jump, and the jump is information rather than a defect.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .span import Span, resolve
from .text import KEPT, Rewritten

__all__ = ["CHARACTERS", "OPAQUE", "TRACEABLE", "Kind", "Segment", "TraceMap"]


class Kind(Enum):
    """What a run of the artefact is, with respect to the source."""

    #: The source's own characters, decoded and otherwise untouched. The
    #: correspondence is exact, character for character.
    VERBATIM = "verbatim"
    #: The same content in different characters -- normalized, an entity
    #: resolved, a line ending changed. The correspondence holds at the ends of
    #: the run and nowhere inside it.
    TRANSFORMED = "transformed"
    #: musubi wrote it. Front matter, an inserted heading, a separator. It came
    #: from nothing in the source, and its ``src`` is where it was put rather
    #: than where it came from.
    SYNTHETIC = "synthetic"
    #: Something was taken out here. Occupies no output and a real stretch of
    #: source, which is how a subtraction stays visible in a map whose whole job
    #: is to be continuous (ADR-0005).
    REMOVAL = "removal"


#: The kinds that count towards traceable coverage: an offset inside one
#: resolves to a place in the source. ``SYNTHETIC`` does not, because there is
#: no such place. ``REMOVAL`` occupies no output, so it neither counts nor
#: could.
TRACEABLE = frozenset({Kind.VERBATIM, Kind.TRANSFORMED})


@dataclass(frozen=True, slots=True)
class Segment:
    """One run of the artefact, and the run of the source it accounts for."""

    out: Span
    src: Span
    kind: Kind
    #: Why this is not verbatim: the cleansing rule id, the converter's reason,
    #: the name of what musubi inserted. Required for everything except
    #: ``VERBATIM``, which needs no excuse, and refused for it, which is what
    #: stops a rule id from being attached to a run nothing happened to.
    rule: str | None = None

    def __post_init__(self) -> None:
        # The equal-length rule for a verbatim run belongs to the map, not to
        # the segment: it holds only while both sides count the same thing, and
        # a map whose source side is measured in bytes has verbatim runs of
        # five characters and fifteen bytes. TraceMap checks it, knowing its
        # own unit.
        if self.kind is Kind.VERBATIM:
            if self.rule is not None:
                raise ValueError("a verbatim segment names no rule; nothing happened to it")
        elif self.rule is None:
            raise ValueError(f"a {self.kind.value} segment must name what did it")
        if self.kind is Kind.REMOVAL and not self.out.is_empty:
            raise ValueError(f"a removal occupies no output, but {self.out} is not empty")

    @property
    def is_traceable(self) -> bool:
        return self.kind in TRACEABLE


#: A source side measured in characters of the decoded text. Both sides count
#: the same thing, so a verbatim run is the same length on each.
CHARACTERS = "characters"

#: A source side measured in something else. No converter produces one yet; a
#: PDF's locator will be a page and an offset within it, and the field exists so
#: that an old reader can *see* it is not looking at a character map rather than
#: reading one field as another ([ADR-0018]).
OPAQUE = "opaque"


@dataclass(frozen=True, slots=True)
class TraceMap:
    """Where every character of an artefact came from."""

    segments: tuple[Segment, ...]
    artefact_length: int
    source_length: int
    #: What a source offset indexes: characters of the decoded text
    #: ([ADR-0018]). ``span.py`` deliberately refuses to decide this, and here is
    #: where it gets decided -- the holder of a span says what it is over, and
    #: the map is the holder.
    #:
    #: **Not bytes**, and the reason is worth knowing: ``source_span_of`` answers
    #: an interior query by shifting an offset by a constant inside a verbatim
    #: run, and that constant is a count of characters. On a byte-measured map
    #: the arithmetic is silently wrong by however many multi-byte characters
    #: came before -- which in a Japanese corpus is all of them. The decoding is
    #: recorded beside the map instead, and the command that opens the file
    #: converts.
    source_unit: str = CHARACTERS

    def __post_init__(self) -> None:
        at = 0
        for segment in self.segments:
            if segment.out.start != at:
                raise ValueError(
                    f"the tiling has a gap or an overlap at {at}: the next segment is {segment.out}"
                )
            at = segment.out.end
            if (
                self.source_unit == CHARACTERS
                and segment.kind is Kind.VERBATIM
                and segment.out.length != segment.src.length
            ):
                raise ValueError(
                    f"a verbatim segment is the same length on both sides while both count "
                    f"characters, but {segment.out} and {segment.src} are not"
                )
        if at != self.artefact_length:
            raise ValueError(
                f"the tiling covers [0:{at}] but the artefact is [0:{self.artefact_length}]"
            )

    # -- building -----------------------------------------------------------

    @classmethod
    def of_rewrite(cls, rewritten: Rewritten) -> TraceMap:
        """Read one rewrite as a map.

        The kind is derived rather than declared, which is what stops a
        converter from labelling its own work generously. Nothing came out: a
        removal. Nothing went in: musubi wrote it. Both: the same content in
        different characters. Neither: it was not touched.
        """
        segments = []
        for piece in rewritten.pieces:
            if piece.kind == KEPT:
                segments.append(Segment(out=piece.out, src=piece.src, kind=Kind.VERBATIM))
                continue
            if piece.out.is_empty:
                kind = Kind.REMOVAL
            elif piece.src.is_empty:
                kind = Kind.SYNTHETIC
            else:
                kind = Kind.TRANSFORMED
            segments.append(Segment(out=piece.out, src=piece.src, kind=kind, rule=piece.kind))
        return cls(
            segments=tuple(segments),
            artefact_length=len(rewritten.text),
            source_length=rewritten.source_length,
        )

    # -- reading ------------------------------------------------------------

    @property
    def characters(self) -> int:
        return self.artefact_length

    @property
    def traceable_characters(self) -> int:
        return sum(segment.out.length for segment in self.segments if segment.is_traceable)

    @property
    def traceable_coverage(self) -> float:
        """The share of the artefact that resolves to a place in the source.

        The number ADR-0004 lives or dies by. An empty artefact reports ``1.0``:
        there is no character that fails the guarantee, and reporting ``0.0``
        would read as a failure of it. The counts are published beside this so
        that a caller aggregating over a corpus uses the right denominator
        rather than averaging ratios.
        """
        if not self.artefact_length:
            return 1.0
        return self.traceable_characters / self.artefact_length

    @property
    def answer_width(self) -> float:
        """Ask about one character: how much source comes back?

        **The number that stops `traceable_coverage` being read as a quality
        score, because it can move the wrong way.** A map with a single
        `transformed` segment covering the whole document is 100% traceable and
        says nothing: every offset resolves, to the entire file. Measured on a
        real alignment, `tools/sensitivity.py`:

        ```text
        window     coverage   matched   answer_width
            64      100.0%          0          166.0     nothing aligned
         65536       98.1%          1            1.3     aligned correctly
        ```

        **The failure reports the higher coverage.** So this is published beside
        it: 1.0 is a map that answers a character with a character, and a large
        number is a map that answers a character with a paragraph. Verbatim runs
        answer exactly, so they count 1; a transformed run answers with the whole
        of what it replaced, so it counts its source length.

        Threshold-free on purpose. There is no *good* value written down here --
        the number is smaller or larger, and a reader compares it against the
        same corpus yesterday. A cut-off would be one more constant nobody
        measured.

        Counted in whatever `source_unit` says, so on a PDF this is **pages per
        character**, and the reports label it.
        """
        if not self.traceable_characters:
            return 1.0
        total = sum(
            (1 if segment.kind is Kind.VERBATIM else segment.src.length) * segment.out.length
            for segment in self.segments
            if segment.is_traceable
        )
        return total / self.traceable_characters

    def segment_at(self, offset: int) -> Segment:
        """The segment covering this artefact offset.

        Zero-length segments -- removals -- cover nothing and are skipped.
        """
        for segment in self.segments:
            if segment.out.contains(offset):
                return segment
        raise ValueError(f"offset {offset} is outside the artefact [0:{self.artefact_length}]")

    def source_span_of(self, out: Span) -> Span:
        """What this range of the artefact came from. The `musubi trace` answer.

        Clipped inside verbatim runs, where the correspondence is exact, and
        taken whole for every other kind, where it is not.
        """
        if out.end > self.artefact_length:
            raise ValueError(f"{out} is outside the artefact [0:{self.artefact_length}]")
        runs = [(s.out, s.src, s.kind is Kind.VERBATIM) for s in self.segments]
        found = resolve(runs, out)
        return Span(0, 0) if found is None else found

    # -- combining ----------------------------------------------------------

    def merged(self) -> TraceMap:
        """Collapse adjacent verbatim runs that continue each other.

        This is what keeps a passthrough at one segment for a whole file, which
        is the difference between a map that costs nothing and a map that costs
        more than the document (ADR-0004's price).

        **Only verbatim runs merge.** Two transformed runs would answer a query
        with the union of what they replaced, which is a different and worse
        answer than either gave alone; and a verbatim run either side of a
        removal must stay apart, because merging across it would erase the
        record that anything was taken.
        """
        merged: list[Segment] = []
        for segment in self.segments:
            previous = merged[-1] if merged else None
            if (
                previous is not None
                and previous.kind is Kind.VERBATIM
                and segment.kind is Kind.VERBATIM
                and previous.out.end == segment.out.start
                and previous.src.end == segment.src.start
            ):
                merged[-1] = Segment(
                    out=Span(previous.out.start, segment.out.end),
                    src=Span(previous.src.start, segment.src.end),
                    kind=Kind.VERBATIM,
                )
            else:
                merged.append(segment)
        return TraceMap(
            segments=tuple(merged),
            artefact_length=self.artefact_length,
            source_length=self.source_length,
            source_unit=self.source_unit,
        )

    def followed_by(self, later: TraceMap) -> TraceMap:
        """Compose two stages: ``self`` ran first, ``later`` ran on its output.

        ``self`` maps an intermediate text back to the source; ``later`` maps
        the final artefact back to that intermediate. The result maps the
        artefact back to the source, which is the whole point of ADR-0004 --
        two transformations, one answer, no hop the reader has to make
        themselves.
        """
        if self.source_unit != CHARACTERS and any(
            segment.kind is Kind.VERBATIM for segment in self.segments
        ):
            # Shifting an offset by a constant is the *only* arithmetic this
            # composition does on the earlier source side, and it happens for
            # verbatim runs alone -- every other kind is taken whole. So the
            # constraint is not "both sides must count characters", it is "a
            # verbatim run must", and a map with no verbatim run composes
            # safely whatever it measures ([ADR-0025]). A PDF's map is that
            # case: one segment per page, none of them verbatim, because there
            # is no character-level correspondence inside a page.
            raise ValueError(
                f"composition shifts offsets inside a verbatim run, which needs both "
                f"sides counting the same thing; this map has verbatim runs and its "
                f"source is measured in {self.source_unit}"
            )
        if later.source_length != self.artefact_length:
            raise ValueError(
                f"the later map describes a source of {later.source_length} characters, "
                f"which does not describe this map's artefact of {self.artefact_length}"
            )

        composed: list[Segment] = []
        carried: set[int] = set()
        for segment in later.segments:
            if segment.kind is Kind.VERBATIM:
                composed.extend(self._project(segment, carried))
            else:
                composed.append(
                    Segment(
                        out=segment.out,
                        src=self.source_span_of(segment.src),
                        kind=segment.kind,
                        rule=segment.rule,
                    )
                )
        return TraceMap(
            segments=tuple(composed),
            artefact_length=later.artefact_length,
            source_length=self.source_length,
            # The source side is still this map's source, so it is still
            # measured in this map's unit. Omitting it defaulted a composed PDF
            # map to `characters` and published page indices under a label that
            # said they were character offsets -- unreachable until ADR-0025
            # let a non-character map compose at all.
            source_unit=self.source_unit,
        )

    def _project(self, run: Segment, carried: set[int]) -> list[Segment]:
        """Carry one verbatim run of the later stage back through this one.

        Split where this map changes kind, so that the part that really is
        verbatim stays verbatim and only the part that is not gives that up.
        Removals this stage made inside the run are carried through as they are:
        the subtraction happened, and a map that forgets it turns every offset
        after it into an unexplained jump (ADR-0005).
        """
        delta = run.out.start - run.src.start
        projected: list[Segment] = []
        for index, earlier in enumerate(self.segments):
            if earlier.out.is_empty:
                point = earlier.out.start
                if index not in carried and run.src.start <= point <= run.src.end:
                    carried.add(index)
                    projected.append(
                        Segment(
                            out=Span(point + delta, point + delta),
                            src=earlier.src,
                            kind=earlier.kind,
                            rule=earlier.rule,
                        )
                    )
                continue
            if not earlier.out.overlaps(run.src):
                continue
            shared = Span(
                max(earlier.out.start, run.src.start),
                min(earlier.out.end, run.src.end),
            )
            if earlier.kind is Kind.VERBATIM:
                source = shared.shift(earlier.src.start - earlier.out.start)
            else:
                # No correspondence inside; the run gives up its exactness for
                # the part that overlaps, and takes the whole of what it covers.
                source = earlier.src
            projected.append(
                Segment(
                    out=shared.shift(delta),
                    src=source,
                    kind=earlier.kind,
                    rule=earlier.rule,
                )
            )
        return sorted(projected, key=lambda s: (s.out.start, s.out.end))
