"""The tiling, written down and read back, and the ways that can go wrong.

`trace_format` is the one place a segment becomes bytes and the one place bytes
become a segment. That is deliberate -- a writer and a reader that are supposed
to agree and do not is a corpus whose maps point somewhere else, and it would
show up as offsets landing in the wrong place rather than as anything failing.

So the important test here is the round trip, over generated tilings rather
than over an example somebody chose.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from musubi.domain.span import Span
from musubi.domain.trace import Kind, Segment, TraceMap
from musubi.errors import ContractError
from musubi.infrastructure.trace_format import SEGMENT_FIELDS, packed, unpacked

RULES = ["boilerplate.nav", "markup.tag.p", "line_ending", "front_matter"]


@st.composite
def a_tiling(draw: st.DrawFn) -> tuple[Segment, ...]:
    """A run of segments that actually tiles: contiguous, in order, from zero.

    Generated rather than written out, because the round trip has to hold for
    the shapes nobody thought of. A removal has no output and a real stretch of
    source; everything else has both.
    """
    count = draw(st.integers(min_value=0, max_value=30))
    segments: list[Segment] = []
    at = 0
    source_at = 0
    for _ in range(count):
        kind = draw(st.sampled_from(list(Kind)))
        length = 0 if kind is Kind.REMOVAL else draw(st.integers(min_value=0, max_value=40))
        width = draw(st.integers(min_value=1 if kind is Kind.REMOVAL else 0, max_value=40))
        rule = None if kind is Kind.VERBATIM else draw(st.sampled_from(RULES))
        segments.append(
            Segment(
                out=Span(at, at + length),
                src=Span(source_at, source_at + width),
                kind=kind,
                rule=rule,
            )
        )
        at += length
        source_at += width
    return tuple(segments)


# -- the round trip, which is what the module is for ------------------------


@given(a_tiling())
def test_a_tiling_survives_being_written_and_read(segments: tuple[Segment, ...]) -> None:
    """Every field of every segment, not just the ones an example happened to
    have. A writer and a reader that disagree do not fail: they point a
    citation at the wrong place in somebody's own file."""
    assert unpacked(packed(segments), "a generated map") == segments


@given(a_tiling())
def test_what_is_written_is_json_a_reader_outside_python_can_read(
    segments: tuple[Segment, ...],
) -> None:
    """The map is a contract, so it has to survive a round trip through JSON
    and not merely through this process's own objects."""
    body = json.loads(json.dumps(packed(segments)))
    assert unpacked(body, "a generated map") == segments


def test_the_output_start_is_derived_rather_than_stored() -> None:
    """The invariant made structural ([ADR-0004] is what allows it).

    The segments tile the artefact exactly once in order, so each one starts
    where the last ended. A row therefore carries a length, and a file has
    nowhere to put a gap or an overlap.
    """
    segments = (
        Segment(out=Span(0, 3), src=Span(0, 3), kind=Kind.VERBATIM),
        Segment(out=Span(3, 4), src=Span(3, 5), kind=Kind.TRANSFORMED, rule="line_ending"),
    )
    body = packed(segments)
    assert body["segment_fields"][0] == "out_length"
    assert [row[0] for row in body["segments"]] == [3, 1]
    assert unpacked(body, "x") == segments


# -- what it costs, which is the reason it exists ---------------------------


def test_a_row_is_far_smaller_than_the_object_it_replaces() -> None:
    """#76: the map was 10.7x the corpus, and after minifying it was still 4.9x
    with the segments within 3% of their own minified size. The bytes were the
    same five key names and the same rule strings, once per segment.

    A floor rather than an exact number, because the ratio moves with how many
    distinct rules a document uses. What it catches is somebody going back to
    objects, or the rule table quietly not being used.
    """
    segments = tuple(
        Segment(
            out=Span(at, at),
            src=Span(at, at + 4),
            kind=Kind.REMOVAL,
            rule="whitespace.between-elements",
        )
        for at in range(0, 200, 4)
    )
    rows = len(json.dumps(packed(segments), separators=(",", ":")))
    objects = len(
        json.dumps(
            [
                {
                    "out": [s.out.start, s.out.end],
                    "src": [s.src.start, s.src.end],
                    "kind": s.kind.value,
                    "rule": s.rule,
                }
                for s in segments
            ],
            separators=(",", ":"),
        )
    )
    assert rows * 3 < objects, f"rows are {objects / rows:.1f}x smaller, and were 3.8x"


# -- the tables travel in the file, which is the point of them --------------


def test_a_reader_uses_the_file_s_own_kind_table_and_not_a_remembered_order() -> None:
    """[ADR-0024]'s rule, applied before it costs anything.

    If the order lived only in the code, a kind added to the enum later would
    reinterpret every map already written: yesterday's `removal` becomes
    today's something-else, silently, at every offset.
    """
    body = packed((Segment(out=Span(0, 0), src=Span(0, 4), kind=Kind.REMOVAL, rule="a.rule"),))
    assert body["kinds"] == ["removal"]

    # The same rows, with the table saying something else. The reader must
    # follow the file.
    body["kinds"] = ["synthetic"]
    (segment,) = unpacked(body, "x")
    assert segment.kind is Kind.SYNTHETIC


def test_a_kind_the_contract_does_not_have_is_refused_rather_than_guessed() -> None:
    body = packed((Segment(out=Span(0, 3), src=Span(0, 3), kind=Kind.VERBATIM),))
    body["kinds"] = ["guessed"]
    with pytest.raises(ContractError, match="cannot read"):
        unpacked(body, "x")


def test_a_row_pointing_past_its_own_tables_is_refused() -> None:
    body = packed((Segment(out=Span(0, 0), src=Span(0, 4), kind=Kind.REMOVAL, rule="a.rule"),))
    body["rules"] = []
    with pytest.raises(ContractError, match="cannot read"):
        unpacked(body, "x")


def test_a_different_column_order_is_refused_rather_than_rearranged() -> None:
    """Resolving an offset against a guessed column order is the confident
    wrong answer this project exists to avoid. A file that lays its rows out
    differently is a file this cannot read, and saying so is the answer."""
    body = packed((Segment(out=Span(0, 3), src=Span(0, 3), kind=Kind.VERBATIM),))
    body["segment_fields"] = ["src_start", "src_end", "out_length", "kind", "rule"]
    with pytest.raises(ContractError, match="column order"):
        unpacked(body, "x")


def test_the_rule_table_holds_each_rule_once() -> None:
    """The whole saving. A rule repeated per row is the object form with extra
    steps."""
    segments = tuple(
        Segment(out=Span(0, 0), src=Span(at, at + 2), kind=Kind.REMOVAL, rule="boilerplate.nav")
        for at in range(0, 40, 2)
    )
    body = packed(segments)
    assert body["rules"] == ["boilerplate.nav"]
    assert {row[4] for row in body["segments"]} == {0}


# -- and the maps written before this ---------------------------------------


def test_a_map_written_as_objects_is_still_read() -> None:
    """Corpora written before this exist and are synced against for months.
    A reader that required the new shape would stop resolving every one of
    them, which is the mistake [ADR-0041] caught the last time a field moved.
    """
    body = {
        "segments": [
            {"out": [0, 3], "src": [0, 3], "kind": "verbatim"},
            {"out": [3, 4], "src": [3, 5], "kind": "transformed", "rule": "line_ending"},
        ]
    }
    found = unpacked(body, "an older map")
    assert found == (
        Segment(out=Span(0, 3), src=Span(0, 3), kind=Kind.VERBATIM),
        Segment(out=Span(3, 4), src=Span(3, 5), kind=Kind.TRANSFORMED, rule="line_ending"),
    )


def test_an_older_map_with_a_gap_in_it_is_still_caught() -> None:
    """The half of the tiling invariant that the row form makes structural is
    still a real check for the object form, and `TraceMap` is where it lives.
    A map read from an old corpus goes through the same constructor."""
    body = {
        "segments": [
            {"out": [0, 3], "src": [0, 3], "kind": "verbatim"},
            {"out": [4, 6], "src": [4, 6], "kind": "verbatim"},
        ]
    }
    segments = unpacked(body, "an older map")
    with pytest.raises(ValueError, match="gap or an overlap"):
        TraceMap(segments=segments, artefact_length=6, source_length=6)


def test_an_empty_map_is_empty_in_either_shape() -> None:
    assert unpacked({"segments": []}, "x") == ()
    assert unpacked({}, "x") == ()
    assert packed(())["segments"] == []


def test_the_fields_are_the_ones_the_contract_names() -> None:
    """A guard on the constant itself: renaming a column without changing the
    schema is a file this reads and nothing else does."""
    assert SEGMENT_FIELDS == ("out_length", "src_start", "src_end", "kind", "rule")
