"""A half-open range, and the arithmetic every layer above depends on.

Every offset musubi ever reports is one end of one of these. The tests are
about the boundaries, because that is where a range type is wrong.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from musubi.domain.span import Span

offsets = st.integers(min_value=0, max_value=500)
spans = st.builds(lambda a, b: Span(min(a, b), max(a, b)), offsets, offsets)


def test_a_span_knows_its_length() -> None:
    assert Span(4, 9).length == 5
    assert len(Span(4, 9)) == 5


def test_an_empty_span_is_legal_and_says_so() -> None:
    """An insertion has nowhere in the source, and that is a zero-length span
    at the point it was inserted -- not a missing one."""
    empty = Span(7, 7)
    assert empty.is_empty
    assert empty.length == 0
    assert not Span(7, 8).is_empty


def test_a_span_may_not_run_backwards() -> None:
    with pytest.raises(ValueError, match="ends before it starts"):
        Span(9, 4)


def test_a_span_may_not_start_before_the_beginning() -> None:
    with pytest.raises(ValueError, match="negative"):
        Span(-1, 4)


def test_containment_is_half_open() -> None:
    span = Span(4, 9)
    assert not span.contains(3)
    assert span.contains(4)
    assert span.contains(8)
    assert not span.contains(9), "the end offset is outside; the range is [start, end)"


def test_an_empty_span_contains_nothing() -> None:
    assert not Span(7, 7).contains(7)


def test_a_span_contains_another() -> None:
    assert Span(4, 9).covers(Span(5, 8))
    assert Span(4, 9).covers(Span(4, 9))
    assert not Span(4, 9).covers(Span(4, 10))


def test_overlap_does_not_count_touching() -> None:
    assert Span(4, 9).overlaps(Span(8, 12))
    assert not Span(4, 9).overlaps(Span(9, 12)), "adjacent is not overlapping"
    assert not Span(4, 9).overlaps(Span(9, 9))


def test_an_empty_span_overlaps_nothing() -> None:
    """Otherwise a zero-length insertion would collide with the run it sits in,
    and the tiling checks above this would reject every legal rewrite."""
    assert not Span(7, 7).overlaps(Span(4, 9))
    assert not Span(4, 9).overlaps(Span(7, 7))


def test_shifting_moves_both_ends() -> None:
    assert Span(4, 9).shift(3) == Span(7, 12)
    assert Span(4, 9).shift(-4) == Span(0, 5)


def test_shifting_below_zero_is_refused() -> None:
    with pytest.raises(ValueError, match="negative"):
        Span(4, 9).shift(-5)


def test_slicing_a_string() -> None:
    assert Span(4, 9).slice("0123456789") == "45678"


def test_a_span_over_a_whole_string() -> None:
    assert Span.over("abcd") == Span(0, 4)
    assert Span.over("") == Span(0, 0)


def test_spans_sort_by_start_then_end() -> None:
    unsorted = [Span(4, 9), Span(0, 12), Span(4, 5)]
    assert sorted(unsorted) == [Span(0, 12), Span(4, 5), Span(4, 9)]


def test_a_span_reads_the_way_an_offset_range_is_written() -> None:
    assert str(Span(4, 9)) == "[4:9]"


@given(spans)
def test_a_span_covers_itself(span: Span) -> None:
    assert span.covers(span)


@given(spans, st.integers(min_value=0, max_value=100))
def test_shifting_preserves_length(span: Span, delta: int) -> None:
    assert span.shift(delta).length == span.length


@given(spans, spans)
def test_overlap_is_symmetric(left: Span, right: Span) -> None:
    assert left.overlaps(right) == right.overlaps(left)


def test_a_span_is_always_truthy() -> None:
    """``__len__`` would otherwise make an empty span falsy, and empty spans are
    everywhere here: an insertion's source, a removal's output, a point query.
    ``resolve(...) or Span(0, 0)`` silently replaced a correct [3:3] with [0:0]
    before this existed."""
    assert bool(Span(3, 3))
    assert Span(3, 3) or False
