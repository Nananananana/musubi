"""Bytes in, text and a map back to them out.

The two nearly-identity converters, which is why they come first: the correct
answer at every offset is obvious, so a wrong tiling is visible rather than
arguable. The interesting part is that "nearly" -- a byte-order mark and a line
ending are both real differences, and the map has to say so.

The source side is measured in **characters of the decoded text**, and the
decoding travels beside it (ADR-0018). A byte offset takes the encoding, the
mark's length and the file, and the command that opens the file is the only
thing that has all three.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from musubi.domain.span import Span
from musubi.domain.text import normalize_line_endings
from musubi.domain.trace import CHARACTERS, OPAQUE, Kind, Segment, TraceMap
from musubi.infrastructure.converters import (
    MarkdownConverter,
    PlainTextConverter,
    converter_for,
    known_converters,
    register_converter,
    registered_media_types,
)
from musubi.ports.converter import Converted, Converter, Unconvertible


def convert(content: bytes, media_type: str = "text/markdown") -> Converted:
    result = MarkdownConverter().convert(content, media_type)
    assert isinstance(result, Converted), result
    return result


def byte_offset(text: str, character: int, *, encoding: str, bom: int) -> int:
    """What `musubi trace` will do, and the only thing that can do it: hold the
    file, and encode the prefix (ADR-0018)."""
    return bom + len(text[:character].encode(encoding))


# -- the easy case ----------------------------------------------------------


def test_a_plain_utf8_note_comes_through_verbatim() -> None:
    result = convert(b"the tent weighs 2.4kg\n")
    assert result.text == "the tent weighs 2.4kg\n"
    assert [s.kind for s in result.trace.segments] == [Kind.VERBATIM]
    assert result.trace.traceable_coverage == 1.0


def test_an_empty_file_converts_to_nothing() -> None:
    result = convert(b"")
    assert result.text == ""
    assert result.trace.segments == ()
    assert result.trace.source_length == 0


def test_the_converter_names_itself_for_the_manifest() -> None:
    assert convert(b"x").converter == "markdown@1"
    result = PlainTextConverter().convert(b"x", "text/plain")
    assert isinstance(result, Converted)
    assert result.converter == "plaintext@1"


# -- the source side, and what it takes to turn it into bytes ---------------


def test_the_source_side_is_measured_in_characters() -> None:
    result = convert("紡ぎ".encode())
    assert result.trace.source_unit == CHARACTERS
    assert result.trace.source_length == 2, "two characters, not six bytes"


def test_the_decoding_travels_beside_the_map() -> None:
    """Everything needed to turn a character offset into a byte offset, and a
    fixed tiny amount of it rather than a per-character index."""
    result = convert(b"\xef\xbb\xbfhello")
    assert result.source_encoding == "utf-8-sig"
    assert result.source_bom_bytes == 3


def test_an_offset_resolves_to_the_characters_it_came_from() -> None:
    source = "見出し\n\nテントは 2.4kg です\n"
    result = convert(source.encode())
    at = result.text.index("2.4kg")

    found = result.trace.source_span_of(Span(at, at + len("2.4kg")))
    assert found.slice(source) == "2.4kg"


def test_and_a_caller_holding_the_file_turns_that_into_bytes() -> None:
    """ADR-0018's whole claim, exercised: the map plus the decoding plus the
    file is enough, and the map alone deliberately is not."""
    source = "見出し\n\nテントは 2.4kg です\n"
    raw = source.encode()
    result = convert(raw)
    at = result.text.index("2.4kg")

    found = result.trace.source_span_of(Span(at, at + len("2.4kg")))
    start = byte_offset(source, found.start, encoding="utf-8", bom=result.source_bom_bytes)
    end = byte_offset(source, found.end, encoding="utf-8", bom=result.source_bom_bytes)
    assert raw[start:end].decode() == "2.4kg"


def test_a_byte_order_mark_is_reported_rather_than_folded_into_the_offsets() -> None:
    """Three bytes on disk and no characters in the string. Producers on
    Windows write one without being asked."""
    plain = convert(b"hello")
    marked = convert(b"\xef\xbb\xbfhello")

    assert plain.text == marked.text == "hello"
    assert plain.trace.segments[0].src == marked.trace.segments[0].src == Span(0, 5)
    assert (plain.source_bom_bytes, marked.source_bom_bytes) == (0, 3)


def test_utf16_is_read_and_says_how() -> None:
    result = convert("ab".encode("utf-16"))
    assert result.text == "ab"
    assert result.source_encoding == "utf-16"
    assert result.source_bom_bytes == 2
    assert result.trace.source_length == 2


# -- line endings -----------------------------------------------------------


def test_crlf_becomes_lf_and_the_map_says_where() -> None:
    result = convert(b"a\r\nb")
    assert result.text == "a\nb"
    assert [s.kind for s in result.trace.segments] == [
        Kind.VERBATIM,
        Kind.TRANSFORMED,
        Kind.VERBATIM,
    ]
    assert result.trace.segments[1].rule == "line_ending"


def test_a_file_already_in_lf_is_one_verbatim_run() -> None:
    """The merge that keeps a passthrough cheap: one segment for a whole file is
    the difference between a map that costs nothing and one that costs more than
    the document."""
    result = convert(b"a\nb\nc\nd\ne\n")
    assert len(result.trace.segments) == 1


def test_a_line_ending_change_still_leaves_what_follows_resolvable() -> None:
    source = "見出し\r\n\r\n2.4kg\r\n"
    result = convert(source.encode())
    at = result.text.index("2.4kg")
    assert result.trace.source_span_of(Span(at, at + 5)).slice(source) == "2.4kg"


# -- what it will not do ----------------------------------------------------


def test_an_encoding_musubi_will_not_guess_at_is_reported_rather_than_mangled() -> None:
    """A value, not an exception: this is a thing the manifest reports with a
    reason, and guessing would write mojibake into a corpus bound for a model
    while looking exactly like a successful read."""
    shift_jis = "これはシフトJISです".encode("shift_jis")
    result = MarkdownConverter().convert(shift_jis, "text/markdown")
    assert isinstance(result, Unconvertible)
    assert result.reason == "undecodable"
    assert result.converter == "markdown@1"
    assert "does not guess" in result.detail


def test_markdown_is_not_rewritten() -> None:
    """Wikilinks, `%%comments%%` and reference links are all transformations of
    somebody's writing, and each needs its own argument. None has been made."""
    source = "see [[design/gear]] and %%this note to self%%\n"
    assert convert(source.encode()).text == source


# -- the registry -----------------------------------------------------------


def test_a_media_type_resolves_to_its_converter() -> None:
    markdown = converter_for("text/markdown")
    plain = converter_for("text/plain")
    assert markdown is not None and markdown.name == "markdown@1"
    assert plain is not None and plain.name == "plaintext@1"


def test_a_media_type_nobody_claims_resolves_to_nothing() -> None:
    """`None` rather than a raise: a folder holds files nobody meant to convert,
    and the caller reports what it skipped."""
    assert converter_for("application/vnd.oasis.opendocument.text") is None


def test_the_registry_lists_what_it_holds() -> None:
    assert registered_media_types() == {
        "application/pdf": "pdf_text@1",
        "application/xhtml+xml": "html@1",
        "text/html": "html@1",
        "text/markdown": "markdown@1",
        "text/plain": "plaintext@1",
    }
    assert [c.name for c in known_converters()] == [
        "html@1",
        "markdown@1",
        "pdf_text@1",
        "plaintext@1",
    ]


class Rival:
    name = "rival@1"
    media_types: tuple[str, ...] = ("text/markdown",)

    def convert(self, content: bytes, media_type: str) -> Converted | Unconvertible:
        return Unconvertible("never")


def test_claiming_a_media_type_somebody_else_holds_is_refused() -> None:
    with pytest.raises(ValueError, match="already claimed"):
        register_converter(Rival())


def test_an_override_is_deliberate_and_gives_back_what_it_displaced() -> None:
    displaced = register_converter(Rival(), replace=True)
    try:
        assert [c.name for c in displaced] == ["markdown@1"]
        held = converter_for("text/markdown")
        assert held is not None and held.name == "rival@1"
    finally:
        register_converter(MarkdownConverter(), replace=True)
    held = converter_for("text/markdown")
    assert held is not None and held.name == "markdown@1"


def test_a_converter_claiming_nothing_is_refused() -> None:
    class Empty:
        name = "empty@1"
        media_types: tuple[str, ...] = ()

        def convert(self, content: bytes, media_type: str) -> Converted | Unconvertible:
            return Unconvertible("never")

    with pytest.raises(ValueError, match="claims no media types"):
        register_converter(Empty())


def test_a_converter_satisfies_the_port() -> None:
    converter: Converter = MarkdownConverter()
    assert converter.media_types == ("text/markdown",)


# -- the unit is recorded, and composition depends on it --------------------


def test_a_map_says_what_its_source_offsets_index() -> None:
    trace = TraceMap.of_rewrite(normalize_line_endings("a\r\nb"))
    assert trace.source_unit == CHARACTERS
    assert trace.merged().source_unit == CHARACTERS
    assert trace.followed_by(trace_over(trace.artefact_length)).source_unit == CHARACTERS


def trace_over(length: int) -> TraceMap:
    return TraceMap(
        artefact_length=length,
        source_length=length,
        segments=(Segment(out=Span(0, length), src=Span(0, length), kind=Kind.VERBATIM),),
    )


def test_composing_a_verbatim_run_whose_source_is_not_characters_is_refused() -> None:
    """The guard is what stops a converter from silently shifting offsets by a
    constant that is not a constant."""
    opaque = TraceMap(
        artefact_length=2,
        source_length=9,
        source_unit=OPAQUE,
        segments=(Segment(out=Span(0, 2), src=Span(0, 9), kind=Kind.VERBATIM),),
    )
    with pytest.raises(ValueError, match="verbatim"):
        opaque.followed_by(trace_over(2))


def test_a_map_with_no_verbatim_run_composes_whatever_it_measures() -> None:
    """ADR-0025. The refusal above is about the arithmetic, not about the unit.

    Shifting an offset inside a verbatim run is the only place composition
    touches the earlier source side; every other kind is taken whole. So a map
    with no verbatim run composes safely however it measures its source -- which
    is what lets a PDF's map, one non-verbatim segment per page, reach the
    cleanser at all.
    """
    pages = TraceMap(
        artefact_length=12,
        source_length=2,
        source_unit=OPAQUE,
        segments=(
            Segment(out=Span(0, 6), src=Span(0, 1), kind=Kind.TRANSFORMED, rule="pdf.page"),
            Segment(out=Span(6, 12), src=Span(1, 2), kind=Kind.TRANSFORMED, rule="pdf.page"),
        ),
    )
    composed = pages.followed_by(trace_over(12))

    assert composed.source_length == 2, "the page count survived the composition"
    assert all(s.kind is not Kind.VERBATIM for s in composed.segments)
    assert composed.source_span_of(Span(0, 3)) == Span(0, 1), "an offset on page one"
    assert composed.source_span_of(Span(7, 9)) == Span(1, 2), "an offset on page two"
    assert composed.source_span_of(Span(3, 9)) == Span(0, 2), "a range crossing both"


def test_the_equal_length_rule_applies_only_while_both_sides_count_characters() -> None:
    with pytest.raises(ValueError, match="same length"):
        trace_over(2).__class__(
            artefact_length=2,
            source_length=9,
            segments=(Segment(out=Span(0, 2), src=Span(0, 9), kind=Kind.VERBATIM),),
        )
    # The same segments, declared as something else, are not the map's business.
    TraceMap(
        artefact_length=2,
        source_length=9,
        source_unit=OPAQUE,
        segments=(Segment(out=Span(0, 2), src=Span(0, 9), kind=Kind.VERBATIM),),
    )


# -- the invariants ---------------------------------------------------------


@given(st.text(max_size=200))
def test_any_text_converts_with_a_tiling_that_holds(source: str) -> None:
    result = convert(source.encode())
    at = 0
    for segment in result.trace.segments:
        assert segment.out.start == at
        at = segment.out.end
    assert at == len(result.text)
    assert result.trace.source_length == len(source)


@given(st.text(max_size=200))
def test_every_verbatim_run_reads_the_same_on_both_sides(source: str) -> None:
    """The round trip. If this fails, `musubi trace` points readers at the wrong
    place in their own files."""
    result = convert(source.encode())
    for segment in result.trace.segments:
        if segment.kind is Kind.VERBATIM:
            assert segment.src.slice(source) == segment.out.slice(result.text)


@given(st.text(max_size=200))
def test_converting_twice_gives_the_same_answer(source: str) -> None:
    raw = source.encode()
    assert convert(raw) == convert(raw)
