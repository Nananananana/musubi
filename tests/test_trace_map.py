"""The tiling, and the composition that makes a two-stage pipeline resolvable.

ADR-0004 in code. A converter produces a map from its output back to the source;
the cleanser produces a second map over that output; the two compose into one
map from the artefact the owner will read back to the bytes they actually have.

The property that everything rests on is that the segments tile the artefact
exactly. The property that makes composition worth having is that a run which
was verbatim through both stages is still verbatim at the end -- and that a run
which was verbatim through one and rewritten through the other is honestly
reported as rewritten, rather than being claimed at the stronger of the two.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from musubi.domain.span import Span
from musubi.domain.text import Replacement, normalize_line_endings, rewrite
from musubi.domain.trace import Kind, Segment, TraceMap

# -- building one from a rewrite -------------------------------------------


def test_an_untouched_rewrite_is_one_verbatim_segment() -> None:
    trace = TraceMap.of_rewrite(rewrite("hello", []))
    assert trace.segments == (Segment(out=Span(0, 5), src=Span(0, 5), kind=Kind.VERBATIM),)
    assert trace.traceable_coverage == 1.0


def test_a_deletion_becomes_a_removal_segment_with_no_output() -> None:
    trace = TraceMap.of_rewrite(rewrite("ab?c", [Replacement(Span(2, 3), "", "tracking.utm")]))
    removal = trace.segments[1]
    assert removal.kind is Kind.REMOVAL
    assert removal.out == Span(2, 2), "a removal occupies no output"
    assert removal.src == Span(2, 3)
    assert removal.rule == "tracking.utm"


def test_a_rewrite_of_the_same_content_is_transformed() -> None:
    trace = TraceMap.of_rewrite(normalize_line_endings("a\r\nb"))
    assert [s.kind for s in trace.segments] == [Kind.VERBATIM, Kind.TRANSFORMED, Kind.VERBATIM]
    assert trace.segments[1].rule == "line_ending"


def test_an_insertion_is_synthetic_and_points_at_a_place_rather_than_a_range() -> None:
    trace = TraceMap.of_rewrite(rewrite("ab", [Replacement(Span(1, 1), "XY", "front_matter")]))
    inserted = trace.segments[1]
    assert inserted.kind is Kind.SYNTHETIC
    assert inserted.out == Span(1, 3)
    assert inserted.src == Span(1, 1), "musubi wrote it; the source has a point, not a range"
    assert inserted.rule == "front_matter"


# -- what the map says ------------------------------------------------------


def test_traceable_coverage_counts_verbatim_and_transformed() -> None:
    trace = TraceMap.of_rewrite(
        rewrite("abcd", [Replacement(Span(2, 2), "XY", "front_matter")]),
    )
    assert trace.characters == 6
    assert trace.traceable_characters == 4
    assert trace.traceable_coverage == pytest.approx(4 / 6)


def test_a_removal_does_not_change_coverage_because_it_occupies_no_output() -> None:
    trace = TraceMap.of_rewrite(rewrite("ab?c", [Replacement(Span(2, 3), "", "noise")]))
    assert trace.traceable_coverage == 1.0


def test_an_empty_artefact_is_not_reported_as_untraceable() -> None:
    """0/0. Reporting 0% would read as a failure of the guarantee, when in fact
    there is no character that fails it. The counts are published beside it so
    a caller aggregating over a corpus uses the right denominator."""
    trace = TraceMap.of_rewrite(rewrite("", []))
    assert trace.characters == 0
    assert trace.traceable_coverage == 1.0


def test_a_range_resolves_to_the_source_it_came_from() -> None:
    trace = TraceMap.of_rewrite(normalize_line_endings("a\r\nbcd"))
    assert trace.source_span_of(Span(0, 1)) == Span(0, 1)
    assert trace.source_span_of(Span(2, 5)) == Span(3, 6)


def test_the_segment_at_an_output_offset() -> None:
    trace = TraceMap.of_rewrite(normalize_line_endings("a\r\nb"))
    assert trace.segment_at(1).kind is Kind.TRANSFORMED


# -- merging ----------------------------------------------------------------


def test_adjacent_verbatim_runs_with_the_same_delta_merge() -> None:
    """This is what keeps a passthrough at one segment for a whole file, which
    is the difference between a map that costs nothing and a map that costs
    more than the document (ADR-0004's price)."""
    trace = TraceMap(
        artefact_length=4,
        source_length=4,
        segments=(
            Segment(out=Span(0, 2), src=Span(0, 2), kind=Kind.VERBATIM),
            Segment(out=Span(2, 4), src=Span(2, 4), kind=Kind.VERBATIM),
        ),
    ).merged()
    assert trace.segments == (Segment(out=Span(0, 4), src=Span(0, 4), kind=Kind.VERBATIM),)


def test_verbatim_runs_that_jump_in_the_source_do_not_merge() -> None:
    """A reflow. The jump is the information, and merging would erase it."""
    trace = TraceMap(
        artefact_length=4,
        source_length=40,
        segments=(
            Segment(out=Span(0, 2), src=Span(30, 32), kind=Kind.VERBATIM),
            Segment(out=Span(2, 4), src=Span(0, 2), kind=Kind.VERBATIM),
        ),
    ).merged()
    assert len(trace.segments) == 2


def test_runs_of_different_kinds_do_not_merge() -> None:
    trace = TraceMap.of_rewrite(normalize_line_endings("a\r\nb")).merged()
    assert [s.kind for s in trace.segments] == [Kind.VERBATIM, Kind.TRANSFORMED, Kind.VERBATIM]


def test_transformed_runs_never_merge_even_when_they_look_adjacent() -> None:
    """Only verbatim merges. Two transformed runs would answer a query with the
    union of what they replaced -- a different and worse answer than either gave
    alone -- and a merged pair could name only one of the two rules."""
    before = TraceMap(
        artefact_length=2,
        source_length=6,
        segments=(
            Segment(out=Span(0, 1), src=Span(0, 3), kind=Kind.TRANSFORMED, rule="a"),
            Segment(out=Span(1, 2), src=Span(3, 6), kind=Kind.TRANSFORMED, rule="b"),
        ),
    )
    assert before.merged().segments == before.segments
    assert before.source_span_of(Span(0, 1)) == Span(0, 3), "not the union of both"


def test_merging_never_swallows_a_removal() -> None:
    """A removal is a zero-length segment between two verbatim runs whose deltas
    differ by exactly what it took. Merging across it would erase the record
    that anything was removed at all (ADR-0005)."""
    trace = TraceMap.of_rewrite(rewrite("ab?cd", [Replacement(Span(2, 3), "", "noise")])).merged()
    assert [s.kind for s in trace.segments] == [Kind.VERBATIM, Kind.REMOVAL, Kind.VERBATIM]


# -- composition ------------------------------------------------------------


def test_verbatim_through_both_stages_stays_verbatim() -> None:
    convert = TraceMap.of_rewrite(rewrite("hello world", []))
    cleanse = TraceMap.of_rewrite(rewrite("hello world", []))
    composed = convert.followed_by(cleanse)
    assert composed.segments == (Segment(out=Span(0, 11), src=Span(0, 11), kind=Kind.VERBATIM),)


def test_a_run_rewritten_in_either_stage_is_reported_as_rewritten() -> None:
    """The weaker of the two wins. A run that was verbatim through the cleanser
    but transformed by the converter did not survive untouched, and claiming
    verbatim would be claiming an exactness the pipeline does not have."""
    convert = TraceMap.of_rewrite(normalize_line_endings("a\r\nb"))  # "a\nb"
    cleanse = TraceMap.of_rewrite(rewrite("a\nb", []))  # untouched
    composed = convert.followed_by(cleanse)
    assert [s.kind for s in composed.segments] == [
        Kind.VERBATIM,
        Kind.TRANSFORMED,
        Kind.VERBATIM,
    ]


def test_a_verbatim_run_is_split_where_the_earlier_stage_changed_kind() -> None:
    """The later stage sees one uninterrupted run; the earlier stage knows it
    was three different things. Splitting keeps the precision instead of
    degrading the whole run to the weakest part of it."""
    convert = TraceMap.of_rewrite(normalize_line_endings("ab\r\ncd"))  # "ab\ncd"
    cleanse = TraceMap.of_rewrite(rewrite("ab\ncd", []))
    composed = convert.followed_by(cleanse)
    assert [(s.out, s.src, s.kind) for s in composed.segments] == [
        (Span(0, 2), Span(0, 2), Kind.VERBATIM),
        (Span(2, 3), Span(2, 4), Kind.TRANSFORMED),
        (Span(3, 5), Span(4, 6), Kind.VERBATIM),
    ]


def test_composition_resolves_a_citation_all_the_way_back() -> None:
    """The point of the whole design: an offset in the artefact, resolved
    through two transformations, to a range in the file the owner has."""
    source = "title\r\n\r\nthe tent weighs 2.4kg\r\n"
    convert = TraceMap.of_rewrite(normalize_line_endings(source))
    converted = normalize_line_endings(source).text

    at = converted.index("2.4kg")
    cleanse = TraceMap.of_rewrite(rewrite(converted, []))
    composed = convert.followed_by(cleanse)

    found = composed.source_span_of(Span(at, at + len("2.4kg")))
    assert found.slice(source) == "2.4kg"


def test_a_removal_in_the_later_stage_keeps_its_rule_through_composition() -> None:
    convert = TraceMap.of_rewrite(rewrite("ab?c", []))
    cleanse = TraceMap.of_rewrite(rewrite("ab?c", [Replacement(Span(2, 3), "", "tracking.utm")]))
    composed = convert.followed_by(cleanse)
    removal = next(s for s in composed.segments if s.kind is Kind.REMOVAL)
    assert removal.rule == "tracking.utm"
    assert removal.src == Span(2, 3), "resolved into the original source, not the intermediate"


def test_a_removal_in_the_earlier_stage_survives_composition() -> None:
    """ADR-0005 again: the subtraction happened, and a map that forgets it makes
    every offset after it look like an unexplained jump."""
    convert = TraceMap.of_rewrite(rewrite("ab?cd", [Replacement(Span(2, 3), "", "noise")]))
    cleanse = TraceMap.of_rewrite(rewrite("abcd", []))
    composed = convert.followed_by(cleanse)
    assert [s.kind for s in composed.segments] == [Kind.VERBATIM, Kind.REMOVAL, Kind.VERBATIM]
    assert next(s for s in composed.segments if s.kind is Kind.REMOVAL).src == Span(2, 3)


def test_something_musubi_inserted_stays_synthetic_through_composition() -> None:
    convert = TraceMap.of_rewrite(rewrite("body", []))
    inserted = [Replacement(Span(0, 0), "---\n", "front_matter")]
    cleanse = TraceMap.of_rewrite(rewrite("body", inserted))
    composed = convert.followed_by(cleanse)
    assert composed.segments[0].kind is Kind.SYNTHETIC
    assert composed.segments[0].rule == "front_matter"
    assert composed.traceable_characters == 4


def test_composing_maps_that_do_not_meet_is_refused() -> None:
    convert = TraceMap.of_rewrite(rewrite("abc", []))
    cleanse = TraceMap.of_rewrite(rewrite("abcdefgh", []))
    with pytest.raises(ValueError, match="does not describe"):
        convert.followed_by(cleanse)


# -- the refusals -----------------------------------------------------------


def test_a_tiling_with_a_gap_is_refused() -> None:
    with pytest.raises(ValueError, match="gap or an overlap"):
        TraceMap(
            artefact_length=4,
            source_length=4,
            segments=(Segment(out=Span(1, 4), src=Span(1, 4), kind=Kind.VERBATIM),),
        )


def test_a_tiling_that_stops_short_of_the_artefact_is_refused() -> None:
    with pytest.raises(ValueError, match="the artefact is"):
        TraceMap(
            artefact_length=9,
            source_length=4,
            segments=(Segment(out=Span(0, 4), src=Span(0, 4), kind=Kind.VERBATIM),),
        )


def test_a_verbatim_segment_of_unequal_lengths_is_refused() -> None:
    """Checked by the map rather than by the segment, because it holds only
    while both sides count the same thing. A map measured in bytes has verbatim
    runs of five characters and fifteen bytes."""
    with pytest.raises(ValueError, match="same length"):
        TraceMap(
            artefact_length=4,
            source_length=9,
            segments=(Segment(out=Span(0, 4), src=Span(0, 9), kind=Kind.VERBATIM),),
        )


def test_a_verbatim_segment_may_not_name_a_rule() -> None:
    with pytest.raises(ValueError, match="no rule"):
        Segment(out=Span(0, 4), src=Span(0, 4), kind=Kind.VERBATIM, rule="tracking.utm")


def test_anything_that_is_not_verbatim_must_say_why() -> None:
    with pytest.raises(ValueError, match="must name"):
        Segment(out=Span(0, 0), src=Span(0, 4), kind=Kind.REMOVAL)


def test_a_removal_that_occupies_output_is_refused() -> None:
    with pytest.raises(ValueError, match="no output"):
        Segment(out=Span(0, 2), src=Span(0, 4), kind=Kind.REMOVAL, rule="noise")


def test_an_offset_outside_the_artefact_has_no_segment() -> None:
    trace = TraceMap.of_rewrite(rewrite("abc", []))
    with pytest.raises(ValueError, match="outside"):
        trace.segment_at(3)


# -- the invariants ---------------------------------------------------------


@st.composite
def a_two_stage_pipeline(draw: st.DrawFn) -> tuple[str, TraceMap]:
    source = draw(st.text(alphabet="ab\r\n?", min_size=0, max_size=40))
    convert = normalize_line_endings(source)

    cuts = sorted(draw(st.sets(st.integers(min_value=0, max_value=len(convert.text)), max_size=4)))
    replacements = [
        Replacement(Span(start, end), draw(st.text(alphabet="xy", max_size=2)), "cleansed")
        for start, end in zip(cuts[::2], cuts[1::2], strict=False)
    ]
    cleanse = rewrite(convert.text, replacements)
    composed = TraceMap.of_rewrite(convert).followed_by(TraceMap.of_rewrite(cleanse))
    return source, composed


@given(a_two_stage_pipeline())
def test_the_segments_tile_the_artefact(case: tuple[str, TraceMap]) -> None:
    _, composed = case
    at = 0
    for segment in composed.segments:
        assert segment.out.start == at
        at = segment.out.end
    assert at == composed.artefact_length


@given(a_two_stage_pipeline())
def test_a_verbatim_segment_reads_the_same_in_the_source(case: tuple[str, TraceMap]) -> None:
    """The round trip. If this ever fails, `musubi trace` is pointing readers at
    the wrong place in their own files."""
    source, composed = case
    for segment in composed.segments:
        if segment.kind is Kind.VERBATIM:
            assert segment.src.length == segment.out.length
            assert segment.src.end <= len(source)


@given(a_two_stage_pipeline())
def test_merging_changes_no_offset_anyone_can_observe(case: tuple[str, TraceMap]) -> None:
    _, composed = case
    merged = composed.merged()
    assert merged.artefact_length == composed.artefact_length
    assert merged.traceable_characters == composed.traceable_characters
    for offset in range(composed.artefact_length):
        assert merged.source_span_of(Span(offset, offset + 1)) == composed.source_span_of(
            Span(offset, offset + 1)
        )


@given(a_two_stage_pipeline())
def test_merging_is_idempotent(case: tuple[str, TraceMap]) -> None:
    _, composed = case
    once = composed.merged()
    assert once.merged().segments == once.segments


def test_an_empty_artefact_resolves_to_a_point() -> None:
    """No segments at all, which happens only when the source was empty too."""
    trace = TraceMap.of_rewrite(rewrite("", []))
    assert trace.segments == ()
    assert trace.source_span_of(Span(0, 0)) == Span(0, 0)


def test_a_range_past_the_end_of_the_artefact_is_refused() -> None:
    with pytest.raises(ValueError, match="outside"):
        TraceMap.of_rewrite(rewrite("abc", [])).source_span_of(Span(0, 9))


def test_a_point_query_skips_the_segments_it_does_not_touch() -> None:
    """A removal at one end of the artefact must not be reported for a point at
    the other end -- the empty-query branch takes every segment the point
    touches, and only those."""
    trace = TraceMap.of_rewrite(rewrite("a?bc", [Replacement(Span(1, 2), "", "noise")]))
    assert trace.source_span_of(Span(1, 1)) == Span(1, 2), "the removal is at this point"
    assert trace.source_span_of(Span(3, 3)) == Span(4, 4), "and not at this one"
