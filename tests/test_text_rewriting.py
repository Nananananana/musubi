"""Rewriting that keeps its offsets, and decoding that refuses to guess.

This is the primitive every later stage is built out of: the cleanser deletes
by rewriting with an empty string, a converter transforms by rewriting, and the
tiling in ADR-0004 is assembled from the pieces a rewrite reports.

The invariant under all of it is that the pieces tile **both** sides -- the
output and the source -- with no gap and no overlap. A rewrite that loses a
character of the source is a rewrite whose map has quietly started lying.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from musubi.domain.span import Span
from musubi.domain.text import (
    KEPT,
    Decoded,
    Piece,
    Replacement,
    Rewritten,
    decode,
    normalize_line_endings,
    rewrite,
)

# -- rewriting --------------------------------------------------------------


def test_no_replacements_is_one_kept_piece() -> None:
    result = rewrite("hello", [])
    assert result.text == "hello"
    assert result.pieces == (Piece(out=Span(0, 5), src=Span(0, 5), kind=KEPT),)


def test_an_empty_source_is_an_empty_rewrite() -> None:
    result = rewrite("", [])
    assert result.text == ""
    assert result.pieces == ()
    assert result.source_length == 0


def test_a_deletion_shortens_the_output_and_keeps_the_source_accounted_for() -> None:
    #                0123456789
    result = rewrite("ab?cd?ef", [Replacement(Span(2, 3), "", "noise")])
    assert result.text == "abcd?ef"

    kinds = [piece.kind for piece in result.pieces]
    assert kinds == [KEPT, "noise", KEPT]

    deleted = result.pieces[1]
    assert deleted.out == Span(2, 2), "a deletion occupies no output"
    assert deleted.src == Span(2, 3), "and exactly its own source"


def test_a_replacement_of_a_different_length_shifts_what_follows() -> None:
    result = rewrite("a\r\nb", [Replacement(Span(1, 3), "\n", "line_ending")])
    assert result.text == "a\nb"
    assert [(p.out, p.src, p.kind) for p in result.pieces] == [
        (Span(0, 1), Span(0, 1), KEPT),
        (Span(1, 2), Span(1, 3), "line_ending"),
        (Span(2, 3), Span(3, 4), KEPT),
    ]


def test_an_insertion_has_a_zero_length_source() -> None:
    result = rewrite("ab", [Replacement(Span(1, 1), "XY", "inserted")])
    assert result.text == "aXYb"
    assert [(p.out, p.src, p.kind) for p in result.pieces] == [
        (Span(0, 1), Span(0, 1), KEPT),
        (Span(1, 3), Span(1, 1), "inserted"),
        (Span(3, 4), Span(1, 2), KEPT),
    ]


def test_replacements_are_applied_in_source_order_whatever_order_they_arrive_in() -> None:
    given_out_of_order = [
        Replacement(Span(4, 5), "", "second"),
        Replacement(Span(1, 2), "", "first"),
    ]
    result = rewrite("abcdef", given_out_of_order)
    assert result.text == "acdf"
    assert [p.kind for p in result.pieces] == [KEPT, "first", KEPT, "second", KEPT]


def test_overlapping_replacements_are_refused() -> None:
    with pytest.raises(ValueError, match="overlap"):
        rewrite("abcdef", [Replacement(Span(1, 4), "", "a"), Replacement(Span(3, 5), "", "b")])


def test_a_replacement_past_the_end_of_the_source_is_refused() -> None:
    with pytest.raises(ValueError, match="outside"):
        rewrite("abc", [Replacement(Span(2, 9), "", "a")])


def test_a_replacement_that_changes_nothing_leaves_no_piece() -> None:
    """Empty in, empty out: nothing happened, so there is nothing to account
    for. This is the one case a piece is not emitted, and it is not a discard
    -- no source and no output are involved."""
    result = rewrite("abc", [Replacement(Span(1, 1), "", "nothing")])
    assert result.text == "abc"
    assert [p.kind for p in result.pieces] == [KEPT]


def test_two_insertions_at_the_same_point_keep_the_order_they_were_given() -> None:
    result = rewrite(
        "ab",
        [Replacement(Span(1, 1), "X", "first"), Replacement(Span(1, 1), "Y", "second")],
    )
    assert result.text == "aXYb"
    assert [p.kind for p in result.pieces] == [KEPT, "first", "second", KEPT]


# -- reading the map back ---------------------------------------------------


def test_the_piece_at_an_output_offset() -> None:
    result = rewrite("a\r\nb", [Replacement(Span(1, 3), "\n", "line_ending")])
    assert result.piece_at(0).kind == KEPT
    assert result.piece_at(1).kind == "line_ending"
    assert result.piece_at(2).kind == KEPT


def test_an_offset_past_the_output_has_no_piece() -> None:
    result = rewrite("abc", [])
    with pytest.raises(ValueError, match="outside"):
        result.piece_at(3)


def test_an_offset_in_a_kept_run_resolves_exactly() -> None:
    result = rewrite("a\r\nbcd", [Replacement(Span(1, 3), "\n", "line_ending")])
    assert result.source_offset(0) == 0
    assert result.source_offset(2) == 3
    assert result.source_offset(4) == 5


def test_an_offset_in_a_rewritten_run_has_no_exact_source_offset() -> None:
    """It is answerable as a *range* and not as a point. Inventing a character
    correspondence inside a transformation is the thing this project exists to
    stop, so the point query says it does not know."""
    result = rewrite("a\r\nb", [Replacement(Span(1, 3), "\n", "line_ending")])
    assert result.source_offset(1) is None


def test_a_range_resolves_to_the_source_it_came_from() -> None:
    result = rewrite("a\r\nbcd", [Replacement(Span(1, 3), "\n", "line_ending")])
    assert result.source_span_of(Span(0, 1)) == Span(0, 1)
    assert result.source_span_of(Span(0, 3)) == Span(0, 4)
    assert result.source_span_of(Span(2, 5)) == Span(3, 6)


def test_a_range_covering_the_whole_output_covers_the_whole_source() -> None:
    source = "a\r\nb\r\nc"
    result = normalize_line_endings(source)
    assert result.source_span_of(Span.over(result.text)) == Span.over(source)


# -- line endings -----------------------------------------------------------


def test_crlf_becomes_lf_and_says_so() -> None:
    result = normalize_line_endings("a\r\nb")
    assert result.text == "a\nb"
    assert [p.kind for p in result.pieces if p.kind != KEPT] == ["line_ending"]


def test_a_lone_cr_becomes_lf() -> None:
    assert normalize_line_endings("a\rb").text == "a\nb"


def test_text_that_is_already_lf_is_left_alone() -> None:
    result = normalize_line_endings("a\nb\nc")
    assert result.text == "a\nb\nc"
    assert [p.kind for p in result.pieces] == [KEPT]


def test_a_lone_lf_after_a_cr_is_not_eaten_twice() -> None:
    assert normalize_line_endings("a\r\n\nb").text == "a\n\nb"


# -- decoding ---------------------------------------------------------------


def test_plain_utf8() -> None:
    assert decode("紡ぎ".encode()) == Decoded(text="紡ぎ", encoding="utf-8", bom_length=0)


def test_a_utf8_byte_order_mark_is_consumed_and_reported() -> None:
    """Producers on Windows write one without being asked, and it is a real
    offset difference: every source offset in the file is three bytes further
    along than the character index suggests."""
    result = decode(b"\xef\xbb\xbf" + b"hello")
    assert result.text == "hello"
    assert result.encoding == "utf-8-sig"
    assert result.bom_length == 3


def test_utf16_with_a_byte_order_mark() -> None:
    result = decode("紡ぎ".encode("utf-16"))
    assert result.text == "紡ぎ"
    assert result.encoding == "utf-16"
    assert result.bom_length == 2


def test_an_encoding_musubi_cannot_identify_is_refused_rather_than_guessed() -> None:
    """ADR-0003 and ADR-0008 in the same breath: a guessed encoding writes
    mojibake into a corpus that will be sent to a model, and it looks like
    successful ingestion."""
    with pytest.raises(ValueError, match="not decodable"):
        decode("これはシフトJISです".encode("shift_jis"))


def test_empty_bytes_decode_to_empty_text() -> None:
    assert decode(b"") == Decoded(text="", encoding="utf-8", bom_length=0)


# -- the invariants ---------------------------------------------------------


@st.composite
def a_source_and_disjoint_replacements(draw: st.DrawFn) -> tuple[str, list[Replacement]]:
    source = draw(st.text(max_size=60))
    cuts = sorted(draw(st.sets(st.integers(min_value=0, max_value=len(source)), max_size=6)))
    replacements = []
    for start, end in zip(cuts[::2], cuts[1::2], strict=False):
        replacements.append(Replacement(Span(start, end), draw(st.text(max_size=4)), "rewrote"))
    return source, replacements


def assert_tiles(spans: list[Span], total: int) -> None:
    at = 0
    for span in spans:
        assert span.start == at, f"gap or overlap at {at}: {span}"
        at = span.end
    assert at == total, f"the tiling ends at {at}, not {total}"


@given(a_source_and_disjoint_replacements())
def test_the_pieces_tile_both_sides(case: tuple[str, list[Replacement]]) -> None:
    source, replacements = case
    result = rewrite(source, replacements)
    assert_tiles([p.out for p in result.pieces], len(result.text))
    assert_tiles([p.src for p in result.pieces], len(source))


@given(a_source_and_disjoint_replacements())
def test_a_kept_piece_reads_the_same_on_both_sides(case: tuple[str, list[Replacement]]) -> None:
    source, replacements = case
    result = rewrite(source, replacements)
    for piece in result.pieces:
        if piece.kind == KEPT:
            assert piece.out.slice(result.text) == piece.src.slice(source)


@given(st.text(max_size=80))
def test_normalizing_line_endings_is_idempotent(text: str) -> None:
    once = normalize_line_endings(text).text
    assert normalize_line_endings(once).text == once
    assert "\r" not in once


@given(st.text(max_size=80))
def test_normalizing_line_endings_keeps_every_other_character(text: str) -> None:
    result = normalize_line_endings(text)
    assert result.text.replace("\n", "") == text.replace("\r\n", "").replace("\r", "").replace(
        "\n", ""
    )


@given(a_source_and_disjoint_replacements())
def test_every_output_offset_lands_in_exactly_one_piece(
    case: tuple[str, list[Replacement]],
) -> None:
    source, replacements = case
    result: Rewritten = rewrite(source, replacements)
    for offset in range(len(result.text)):
        piece = result.piece_at(offset)
        assert piece.out.contains(offset)


# -- the refusals -----------------------------------------------------------


def test_a_replacement_must_say_why_it_happened() -> None:
    with pytest.raises(ValueError, match="no kind"):
        Replacement(Span(0, 1), "", "")


def test_a_replacement_may_not_claim_to_be_untouched() -> None:
    with pytest.raises(ValueError, match="reserved"):
        Replacement(Span(0, 1), "x", KEPT)


def test_a_range_past_the_end_of_the_output_is_refused() -> None:
    with pytest.raises(ValueError, match="outside"):
        rewrite("abc", []).source_span_of(Span(0, 9))


def test_an_empty_range_resolves_to_a_point() -> None:
    result = rewrite("abc", [])
    assert result.source_span_of(Span(0, 0)) == Span(0, 0)
    assert result.source_span_of(Span(3, 3)) == Span(3, 3)


def test_an_empty_output_resolves_to_a_point() -> None:
    result = rewrite("abc", [Replacement(Span(0, 3), "", "all_of_it")])
    assert result.text == ""
    assert result.source_span_of(Span(0, 0)) == Span(0, 3)


def test_a_tiling_with_a_gap_is_refused() -> None:
    """Constructed directly, because no rewrite can produce one -- which is the
    point. The guard is what makes that a fact rather than a belief."""
    with pytest.raises(ValueError, match="gap or an overlap"):
        Rewritten(
            text="abc",
            pieces=(Piece(out=Span(1, 3), src=Span(0, 3), kind=KEPT),),
            source_length=3,
        )


def test_a_tiling_that_loses_the_end_of_the_source_is_refused() -> None:
    with pytest.raises(ValueError, match="the source is"):
        Rewritten(
            text="ab",
            pieces=(Piece(out=Span(0, 2), src=Span(0, 2), kind=KEPT),),
            source_length=5,
        )


def test_an_empty_source_resolves_to_a_point() -> None:
    """No pieces at all, which happens only here."""
    assert rewrite("", []).source_span_of(Span(0, 0)) == Span(0, 0)
