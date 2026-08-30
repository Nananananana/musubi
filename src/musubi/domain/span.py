"""A half-open range of integer positions.

Every offset musubi reports -- in a trace map, in a removal record, in the
answer ``musubi trace`` gives -- is one end of one of these.

**What a position indexes is deliberately not decided here.** A span over an
emitted artefact counts characters, because that is what a consumer anchoring
into the document counts. A span over a PDF counts something else entirely. The
holder of a span says what it is over, and the trace map is where that is
recorded; a range type that guessed would be wrong for one of the two.

Half-open, so that ``Span(0, 4)`` and ``Span(4, 9)`` are adjacent with no gap
and no overlap, and a zero-length span is a *point* rather than a mistake. An
insertion has nowhere in the source, which is exactly a zero-length span at the
place it was inserted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

__all__ = ["Span"]


@dataclass(frozen=True, slots=True, order=True)
class Span:
    """``[start, end)``. Ordered by start, then end, so a sort is stable."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0:
            raise ValueError(f"a span cannot start at a negative offset: {self.start}")
        if self.end < self.start:
            raise ValueError(f"span [{self.start}:{self.end}] ends before it starts")

    @classmethod
    def over(cls, text: str) -> Self:
        """The span covering a whole string."""
        return cls(0, len(text))

    @property
    def length(self) -> int:
        return self.end - self.start

    @property
    def is_empty(self) -> bool:
        return self.end == self.start

    def __len__(self) -> int:
        return self.length

    def __str__(self) -> str:
        return f"[{self.start}:{self.end}]"

    def contains(self, offset: int) -> bool:
        """Is this offset inside the range? Half-open: ``end`` is not."""
        return self.start <= offset < self.end

    def covers(self, other: Span) -> bool:
        """Does this range contain the whole of another?"""
        return self.start <= other.start and other.end <= self.end

    def overlaps(self, other: Span) -> bool:
        """Do the two ranges share at least one position?

        Touching is not overlapping, and an empty span overlaps nothing --
        including the run it sits inside. Otherwise a zero-length insertion
        would collide with its own neighbourhood and every legal rewrite would
        fail the tiling checks built on top of this.
        """
        if self.is_empty or other.is_empty:
            return False
        return self.start < other.end and other.start < self.end

    def shift(self, delta: int) -> Span:
        """The same length, moved. Refuses to move below zero."""
        return Span(self.start + delta, self.end + delta)

    def slice(self, text: str) -> str:
        return text[self.start : self.end]
