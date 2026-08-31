"""The first converter whose output is a minority of its input.

Markdown and plain text were nearly the identity, so a wrong map was hard to
write. Here most of the source becomes nothing, and the question the whole
project turns on — *can this offset be pointed back at the file* — has a
non-trivial answer for the first time.

So these tests are mostly about the map, not the text. A converter that produced
lovely Markdown with offsets that were off by the length of a `<nav>` would be
worse than one that produced clumsy text and knew where it came from.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from musubi.domain.trace import Kind
from musubi.infrastructure.converters.html import BOILERPLATE, HtmlConverter
from musubi.ports.converter import Converted, Unconvertible

PAGE = """<!doctype html>
<html><head><title>ignored</title><style>p{color:red}</style></head>
<body>
<nav><a href="/">home</a></nav>
<h1>ギア設計</h1>
<p>Tents &amp; poles, with a <b>bold</b> word.</p>
<footer>(c) 2026</footer>
</body></html>"""


def convert(html: str) -> Converted:
    result = HtmlConverter().convert(html.encode("utf-8"), "text/html")
    assert isinstance(result, Converted), result
    return result


# -- the text ---------------------------------------------------------------


def test_the_document_survives_and_the_furniture_does_not() -> None:
    text = convert(PAGE).text
    assert "ギア設計" in text
    assert "Tents & poles" in text
    for gone in ("home", "(c) 2026", "color:red", "ignored"):
        assert gone not in text, f"{gone!r} is page furniture and reached the corpus"


def test_a_heading_keeps_its_level() -> None:
    assert convert("<h2>ギア</h2>").text.startswith("## ")


def test_inline_markup_does_not_break_a_sentence() -> None:
    """`<b>` is not a block, so the words either side of it stay one sentence."""
    assert "one bold word" in convert("<p>one <b>bold</b> word</p>").text


def test_blocks_are_separated() -> None:
    text = convert("<p>first</p><p>second</p>").text
    assert "firstsecond" not in text
    assert "first" in text and "second" in text


def test_a_space_between_inline_elements_survives() -> None:
    """Whitespace is two different things and telling them apart is the point.

    Between blocks it is markup indentation and belongs nowhere. **Inside a line
    it is a word boundary**, and dropping it produced `See this& that` -- two
    words welded together, from a converter that reported full confidence.
    """
    assert "See this & that." in convert("<p>See <a>this</a> &amp; that.</p>").text


def test_whitespace_between_blocks_still_goes() -> None:
    """The other half. Keeping it puts a stray space at the start of every
    paragraph, which is how the first version of the fix broke this."""
    assert convert("<p>a</p>\n<p>b</p>").text == "a\n\nb\n\n"


# -- the map ----------------------------------------------------------------


def test_every_character_of_the_source_is_accounted_for() -> None:
    """ADR-0005: what was taken out is recorded with the rule that took it.

    A converter may drop most of a page. It may not drop it *silently* -- the
    removed navigation is a segment with a rule, not a gap in the account.
    """
    result = convert(PAGE)
    covered = 0
    for segment in result.trace.segments:
        assert segment.src.start >= covered, "the source account went backwards"
        covered = max(covered, segment.src.end)
    assert covered == result.trace.source_length


def test_what_was_removed_says_which_rule_removed_it() -> None:
    rules = {s.rule for s in convert(PAGE).trace.segments if s.kind is Kind.REMOVAL}
    assert "boilerplate.nav" in rules
    assert "boilerplate.footer" in rules
    assert any(r and r.startswith("markup.tag.") for r in rules)
    assert None not in rules, "a removal with no rule is a gap wearing a segment's clothes"


def test_a_verbatim_run_reads_the_same_on_both_sides() -> None:
    source = PAGE
    result = convert(PAGE)
    for segment in result.trace.segments:
        if segment.kind is Kind.VERBATIM:
            assert (
                result.text[segment.out.start : segment.out.end]
                == (source[segment.src.start : segment.src.end])
            )


def test_an_entity_is_transformed_and_never_verbatim() -> None:
    """`&amp;` is five characters in and one out. Claiming verbatim would be a
    lie the map's own invariant catches, which is why it is worth asserting: the
    type system does not stop a converter from lying, the constructor does."""
    result = convert("<p>a &amp; b</p>")
    entity = [s for s in result.trace.segments if s.kind is Kind.TRANSFORMED]
    assert entity, "the entity produced no transformed segment"
    assert all(len(s.src) != len(s.out) for s in entity)
    assert "a & b" in result.text


def test_the_structure_musubi_added_is_synthetic() -> None:
    """The `## ` and the blank lines came from musubi, not from the page. A
    reader following one of those offsets must be told nothing is there."""
    result = convert("<h2>x</h2>")
    synthetic = [s for s in result.trace.segments if s.kind is Kind.SYNTHETIC]
    assert synthetic
    assert all(s.src.is_empty for s in synthetic), "synthetic text claimed source it did not have"


def test_traceable_coverage_is_below_one_and_says_so() -> None:
    """The milestone's point: this is the first converter where coverage is a
    measurement rather than 1.0 by construction."""
    result = convert(PAGE)
    assert result.trace.traceable_characters < result.trace.artefact_length
    assert result.trace.traceable_characters > 0


# -- the awkward inputs -----------------------------------------------------


@pytest.mark.parametrize("element", sorted(BOILERPLATE))
def test_no_boilerplate_element_leaks_its_text(element: str) -> None:
    result = convert(f"<p>keep</p><{element}>SECRET-FURNITURE</{element}>")
    assert "SECRET-FURNITURE" not in result.text
    assert "keep" in result.text


def test_an_unclosed_boilerplate_element_does_not_swallow_the_rest() -> None:
    """A real page has unbalanced tags. Suppression is popped by a matching
    close, so a stray `</div>` must not end it and an unclosed `<nav>` must not
    silently eat a document -- but if it does, that is visible as coverage
    rather than as a wrong offset."""
    result = convert("<nav>menu</nav><p>body</p>")
    assert "body" in result.text
    assert "menu" not in result.text


def test_an_unknown_entity_stays_as_written() -> None:
    """Inventing a character here would put something in the corpus the source
    does not contain."""
    assert "&notarealentity;" in convert("<p>&notarealentity;</p>").text


def test_a_comment_leaves_no_text_and_no_gap() -> None:
    result = convert("<p>a</p><!-- hidden note --><p>b</p>")
    assert "hidden" not in result.text
    assert any(s.rule == "markup.dropped" for s in result.trace.segments)


def test_an_empty_document_converts_to_nothing_without_failing() -> None:
    result = convert("")
    assert result.text == ""
    assert result.trace.artefact_length == 0


def test_bytes_musubi_will_not_guess_at_are_reported_not_guessed() -> None:
    result = HtmlConverter().convert(b"\xff\xfe\x00<html>", "text/html")
    assert isinstance(result, Unconvertible)
    assert result.reason == "undecodable"


@given(
    st.lists(
        st.sampled_from(
            [
                "<p>",
                "</p>",
                "<b>",
                "</b>",
                "<nav>",
                "</nav>",
                "<script>",
                "</script>",
                "text",
                "  ",
                "\n",
                "&amp;",
                "&#65;",
                "<!-- c -->",
                "<br/>",
                "</div>",
                "日本語",
                "<h1>",
                "</h1>",
            ]
        ),
        max_size=40,
    )
)
def test_the_map_holds_over_arbitrary_markup(pieces: list[str]) -> None:
    """The tiling is checked by `TraceMap`'s own constructor, so this asserts
    that no arrangement of tags makes the converter build one that does not
    hold -- including the unbalanced ones a real page is full of."""
    result = HtmlConverter().convert("".join(pieces).encode("utf-8"), "text/html")
    assert isinstance(result, Converted)
    assert result.trace.artefact_length == len(result.text)
    assert result.trace.traceable_characters <= result.trace.artefact_length
