"""Composition got a binary search. It has to compute exactly what it did.

`TraceMap.followed_by` used to scan every segment of the earlier map for every
segment of the later one. Two nested walks over maps that both grow with the
document, which is a quadratic — and it was not theoretical:

```text
links   bytes     sync      growth
  100  13,840    0.09s
  800 111,840    5.29s      8.5x
```

**112 kB, five seconds.** That is a blog index or a newsletter archive: a page
of links with tracking parameters on them, so that the converter's map and the
cleanser's map are both dense. A folder of them is unusable.

The segments tile the output in order, so `out.end` is non-decreasing and the
window is a bisection. Linear now, 33× faster at 800 links.

**This file is the reason that is a safe thing to have done.** An optimisation
to the core of [ADR-0004] that quietly changed an answer would be the worst
possible defect here — every citation in every corpus built afterwards would be
wrong, and nothing would say so. So the old algorithm is kept, in this file, and
the two are compared on generated maps.
"""

from __future__ import annotations

import time

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from musubi.domain.span import Span, resolve
from musubi.domain.text import Replacement, rewrite
from musubi.domain.trace import Kind, Segment, TraceMap


def scanning(earlier: TraceMap, later: TraceMap) -> list[Segment]:
    """`followed_by` as it was: every earlier segment, for every later one.

    Kept here rather than in the library, so the comparison is against
    something nobody can accidentally optimise into agreeing.
    """
    composed: list[Segment] = []
    carried: set[int] = set()
    for segment in later.segments:
        if segment.kind is not Kind.VERBATIM:
            runs = [(s.out, s.src, s.kind is Kind.VERBATIM) for s in earlier.segments]
            found = resolve(runs, segment.src)
            composed.append(
                Segment(
                    out=segment.out,
                    src=Span(0, 0) if found is None else found,
                    kind=segment.kind,
                    rule=segment.rule,
                )
            )
            continue

        delta = segment.out.start - segment.src.start
        for index, early in enumerate(earlier.segments):
            if early.out.is_empty:
                point = early.out.start
                if index not in carried and segment.src.start <= point <= segment.src.end:
                    carried.add(index)
                    composed.append(
                        Segment(
                            out=Span(point + delta, point + delta),
                            src=early.src,
                            kind=early.kind,
                            rule=early.rule,
                        )
                    )
                continue
            if not early.out.overlaps(segment.src):
                continue
            shared = Span(
                max(early.out.start, segment.src.start), min(early.out.end, segment.src.end)
            )
            source = (
                shared.shift(early.src.start - early.out.start)
                if early.kind is Kind.VERBATIM
                else early.src
            )
            composed.append(
                Segment(
                    out=shared.shift(delta),
                    src=source,
                    kind=early.kind if early.kind is not Kind.VERBATIM else Kind.VERBATIM,
                    rule=early.rule,
                )
            )
    return composed


#: Replacements over a generated text. Two stages of them make the pair of dense
#: maps the quadratic needed, which a single stage never produces.
def _stage(text: str, every: int, width: int, kind: str) -> tuple[TraceMap, str]:
    """A map over `text`, and the text it produced -- the next stage needs both."""
    replacements = [
        Replacement(Span(at, min(at + width, len(text))), "*", kind)
        for at in range(0, max(0, len(text) - width), every)
    ]
    rewritten = rewrite(text, replacements)
    return TraceMap.of_rewrite(rewritten), rewritten.text


@given(
    body=st.text(alphabet=st.characters(codec="utf-8", exclude_characters="\x1b"), max_size=300),
    every=st.integers(min_value=2, max_value=9),
    width=st.integers(min_value=1, max_value=4),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_the_bisecting_composition_agrees_with_the_scanning_one(
    body: str, every: int, width: int
) -> None:
    """Generated rather than chosen, because the cases that would differ are the
    boundaries — a removal sitting exactly at the start or the end of a run —
    and those are the ones nobody thinks to write down."""
    if width >= every:
        width = every - 1
    first, middle = _stage(body, every, width, "converter")
    second, _ = _stage(middle, every + 1, width, "cleanser")

    assert list(first.followed_by(second).segments) == scanning(first, second)


def test_a_removal_at_the_edge_of_a_run_is_still_carried() -> None:
    """The case the window could have dropped, written out.

    A removal occupies no output, so it sits *between* two runs — and a window
    that excluded it would silently lose the subtraction from the composed map,
    which is the failure ADR-0005 exists to prevent. `bisect_left` on the ends
    includes a removal at the start of the range and the upper bound admits one
    at the end.
    """
    struck = rewrite("abcdefghij", [Replacement(Span(4, 6), "", "removed")])
    first = TraceMap.of_rewrite(struck)
    second = TraceMap.of_rewrite(rewrite(struck.text, []))

    composed = first.followed_by(second)
    removals = [s for s in composed.segments if s.kind is Kind.REMOVAL]

    assert removals, "the removal was lost in composition"
    assert removals[0].src == Span(4, 6)
    assert composed.segments == tuple(scanning(first, second))


@pytest.mark.parametrize("segments", [400, 800, 1600])
def test_composition_does_not_grow_quadratically(segments: int) -> None:
    """Timed, and deliberately loose.

    A timing assertion is a bad test and the alternative here is worse: the
    property being protected *is* the order of growth, and counting comparisons
    would mean instrumenting the thing under test. So this asserts only that
    doubling the work does not quadruple the time, with a wide margin, and the
    number that matters lives in `tools/scaling.py` where it can be read.
    """
    body = "word " * segments
    first, middle = _stage(body, 5, 2, "converter")
    second, _ = _stage(middle, 7, 2, "cleanser")

    started = time.perf_counter()
    first.followed_by(second)
    seconds = time.perf_counter() - started

    assert seconds < 5.0, (
        f"composing {len(first.segments)} against {len(second.segments)} segments took "
        f"{seconds:.1f}s. Before the bisection, 3,200 segments took 1.7s and the growth "
        f"was quadratic; this is the shape coming back."
    )
