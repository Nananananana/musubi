"""Recovering a map from text that arrived without one.

Two subjects, and the second is the reason for the first:

- **the alignment** — that a run found in the source is verbatim with exact
  offsets, that a stretch producing no output is a `removal` rather than being
  folded into a `transformed` neighbour, and that the scan cannot be made to run
  away;
- **the adapters built on it** — that they are optional, that they are *offered*
  rather than claimed, and that [ADR-0007]'s no-network boundary holds over code
  musubi did not write.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest

from musubi.domain.alignment import MINIMUM_RUN, align
from musubi.domain.trace import Kind
from musubi.infrastructure.converters import (
    claimed_converters,
    converter_for,
    known_converters,
)
from musubi.infrastructure.converters.external import (
    EXTRACTORS,
    PAGE_EXTRACTORS,
    TEXT_EXTRACTORS,
    adapters,
    available,
    unavailable,
)
from musubi.ports.converter import Converted, Converter
from pdf_fixtures import FIRST_LINE, classic, modern, scanned

# -- the alignment ----------------------------------------------------------


def test_a_run_present_in_the_source_is_verbatim_at_the_right_offsets() -> None:
    """The whole claim. A recovered offset is worth nothing unless it is the
    offset, so this asserts the source slice rather than the coverage."""
    source = "<p>A tent that weighs 2.4kg is a tent you carry all day.</p>"
    output = "A tent that weighs 2.4kg is a tent you carry all day.\n"

    aligned = align(source, output)
    (verbatim,) = [s for s in aligned.trace.segments if s.kind is Kind.VERBATIM]
    assert (
        source[verbatim.src.start : verbatim.src.end]
        == output[verbatim.out.start : verbatim.out.end]
    )


def test_a_dropped_stretch_is_a_removal_and_not_a_transformed_newline() -> None:
    """[ADR-0005]'s reading, applied to an extractor's silence.

    Between two matched paragraphs there is a newline in the output and four
    kilobytes of navigation in the source. Calling that one `transformed`
    segment asserts that a newline *is* the navigation.
    """
    boilerplate = "<nav>" + "<a href='/x'>Home</a>" * 200 + "</nav>"
    source = (
        f"<p>The first paragraph, long enough to match.</p>"
        f"{boilerplate}"
        f"<p>And the second paragraph, also long.</p>"
    )
    output = "The first paragraph, long enough to match.\nAnd the second paragraph, also long.\n"

    aligned = align(source, output)
    removals = [s for s in aligned.trace.segments if s.kind is Kind.REMOVAL]
    assert removals, "the navigation was folded into a neighbour instead of being named"
    assert any(len(boilerplate) <= s.src.length for s in removals)
    assert all(s.out.is_empty for s in removals), "a removal occupies no output"


def test_a_line_the_source_does_not_hold_is_transformed_not_verbatim() -> None:
    """An entity resolved on the way out. The ends are right, the interior is
    not, and claiming exactness would be the lie ADR-0004 forbids."""
    source = "<p>Boots &amp; socks matter more than the pack.</p>"
    output = "Boots & socks matter more than the pack.\n"

    aligned = align(source, output)
    assert not [s for s in aligned.trace.segments if s.kind is Kind.VERBATIM]
    assert aligned.unmatched_runs == 1


def test_the_scan_is_forward_only() -> None:
    """A string found *behind* where the extractor already was is not the
    occurrence the extractor emitted. Attributing it there would put a citation
    at a confident wrong place, which is the one failure this project exists to
    prevent."""
    repeated = "the same paragraph twice over"
    source = f"<p>{repeated}</p><p>a middle paragraph here</p><p>{repeated}</p>"
    output = f"a middle paragraph here\n{repeated}\n"

    aligned = align(source, output)
    verbatim = [s for s in aligned.trace.segments if s.kind is Kind.VERBATIM]
    assert [s.src.start for s in verbatim] == sorted(s.src.start for s in verbatim)
    assert source[verbatim[-1].src.start :].startswith(repeated)
    assert verbatim[-1].src.start > source.index(repeated), "matched the earlier occurrence"


def test_a_run_shorter_than_the_minimum_is_not_looked_for() -> None:
    """Short strings occur everywhere by chance, and a chance hit anchors the
    scan to the wrong place and costs every line after it."""
    short = "x" * (MINIMUM_RUN - 1)
    aligned = align(f"nothing to do with it {short} at the end", f"{short}\n")
    assert not [s for s in aligned.trace.segments if s.kind is Kind.VERBATIM]
    assert aligned.unmatched_runs == 0, "too short to be looked for is not a failure to find"


def test_the_window_bounds_the_work_rather_than_the_correctness() -> None:
    """The bound is what makes this linear rather than quadratic.

    A run further ahead than the window is reported as transformed, which is
    true and less precise than it could have been -- the trade the constant
    names.
    """
    run = "a paragraph a long way further down the file"
    source = ("." * 2000) + run
    assert align(source, f"{run}\n", window=100_000).matched_runs == 1
    assert align(source, f"{run}\n", window=100).matched_runs == 0


@pytest.mark.parametrize(
    ("source", "output"),
    [
        ("", ""),
        ("nothing survived this at all", ""),
        ("", "everything here is invented"),
        ("identical on both sides here", "identical on both sides here"),
    ],
)
def test_the_tiling_holds_whatever_the_two_sides_are(source: str, output: str) -> None:
    """`TraceMap` checks the tiling on construction, so this is really asking
    whether `align` can be made to build an illegal one -- which is the way this
    would fail in production rather than in an assertion."""
    aligned = align(source, output)
    assert aligned.trace.artefact_length == len(output)
    assert aligned.trace.source_length == len(source)


# -- the adapters -----------------------------------------------------------


def test_an_optional_adapter_is_offered_and_never_claims_a_media_type() -> None:
    """[ADR-0028]. A dependency that appeared in an environment must not change
    what a folder builds; the settings decide that, not the site-packages."""
    offered = {c.name for c in known_converters()} - {c.name for c in claimed_converters()}
    assert {e.name for e in available()} <= offered
    for extractor in available():
        for media_type in extractor.media_types:
            held = converter_for(media_type)
            assert held is not None
            assert held.name != extractor.name, (
                f"{extractor.name} took {media_type} from {held.name} by being installed"
            )


def test_every_adapter_states_a_permissive_licence() -> None:
    """A licence field nobody checks is a licence field. PyMuPDF is the fastest
    PDF reader in Python and is AGPL-3.0; the rule is what keeps it out."""
    assert EXTRACTORS, "no adapters; this guard would run zero times"
    for extractor in EXTRACTORS:
        assert extractor.licence in {"Apache-2.0", "BSD-3-Clause", "MIT"}, extractor


def test_a_missing_extra_is_a_name_that_is_absent_not_an_import_error() -> None:
    assert set(available()) | set(unavailable()) == set(EXTRACTORS)
    for extractor in unavailable():
        assert extractor.extra.startswith("musubi["), extractor


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make every socket unusable for the duration.

    Not a mock of one library's fetcher: [ADR-0007] is a property of musubi, and
    the point is that it holds over code musubi did not write and cannot read
    every release of.
    """

    def refuse(*_: object, **__: object) -> None:
        raise AssertionError("ADR-0007: something opened a socket during a conversion")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    yield


#: A page with the two structures a tag-scanner cannot tell from content: a
#: cookie banner and a newsletter box, both of which are `<div><p>` and both of
#: which musubi's own `html@1` keeps. The absolute URL is what a fetching
#: extractor would reach for.
PAGE = b"""<!doctype html><html><head><title>t</title></head><body>
<a href="https://example.test/away">Skip to main content</a>
<div id="cookie-banner"><p>We use cookies. Accept all cookies to continue.</p></div>
<nav><a href="/">Home</a><a href="/blog">Blog</a></nav>
<main><article><p>A tent that weighs 2.4kg is a tent you carry all day.</p>
<p>The stove is the part people get wrong, every single time.</p></article></main>
<div class="newsletter"><p>Subscribe to our newsletter for more of this.</p></div>
<footer><p>Copyright 2026 Example Corporation.</p></footer></body></html>"""

#: What is in `PAGE` and should not be in anything built from it.
PLANTED = (
    "Skip to main content",
    "Accept all cookies",
    "Subscribe to our newsletter",
    "Copyright 2026",
)


#: One sample per media type an adapter might claim, so a parametrised test can
#: hand each adapter something it can actually read. A single fixture would have
#: measured `pdfium@1` on a web page.
SAMPLES: dict[str, bytes] = {
    "text/html": PAGE,
    "application/xhtml+xml": PAGE,
    "application/pdf": classic(),
}


def _sample_for(converter: Converter) -> tuple[str, bytes]:
    for media_type in converter.media_types:
        if media_type in SAMPLES:
            return media_type, SAMPLES[media_type]
    raise AssertionError(f"no sample for {converter.media_types}; this would measure nothing")


def _named(name: str) -> Converter:
    return next(c for c in known_converters() if c.name == name)


@pytest.mark.parametrize("name", sorted(c.name for c in adapters()))
def test_an_adapter_opens_no_socket(name: str, no_network: None) -> None:
    """The page holds an absolute URL, which is what a fetching extractor would
    reach for."""
    converter = _named(name)
    media_type, sample = _sample_for(converter)
    result = converter.convert(sample, media_type)
    assert isinstance(result, Converted), getattr(result, "reason", result)


@pytest.mark.parametrize("name", sorted(c.name for c in adapters()))
def test_an_adapter_returns_a_map_that_resolves(name: str) -> None:
    """The thing an extractor cannot give and an adapter has to recover."""
    converter = _named(name)
    media_type, sample = _sample_for(converter)
    result = converter.convert(sample, media_type)
    assert isinstance(result, Converted)
    assert result.trace.traceable_coverage > 0.5, (
        f"{name} produced text nothing could place; a better extraction that "
        f"cannot be traced is not the trade ADR-0028 made"
    )
    assert result.trace.artefact_length == len(result.text)
    for segment in result.trace.segments:
        if segment.kind is Kind.VERBATIM:
            assert segment.out.length == segment.src.length


@pytest.mark.parametrize("name", sorted(c.name for c in adapters()))
def test_an_adapter_refuses_rubbish_rather_than_raising(name: str) -> None:
    """A folder of thousands holds a truncated file, and [ADR-0008] wants a run
    that stops on a credential and keeps going past one of those.

    An exception escaping an adapter takes the whole sync with it, and the code
    it would escape from is not musubi's.
    """
    converter = _named(name)
    media_type, _ = _sample_for(converter)
    result = converter.convert(bytes([0, 1]) + b" not a document " + bytes([255]), media_type)
    assert not isinstance(result, Converted), "read a document out of noise"
    assert result.reason, "refused without saying why"


# -- what each dependency actually buys -------------------------------------


@pytest.mark.skipif(
    not [e for e in TEXT_EXTRACTORS if e.load()], reason="no text extractor installed"
)
def test_the_html_adapter_rejects_boilerplate_the_built_in_one_keeps() -> None:
    """The measurement ADR-0028 rests on, as an assertion rather than a table.

    Not a threshold on a score. `html@1` keeps a cookie banner and a newsletter
    box, because both are a `<div>` with a `<p>` in it and a scan of tags has
    nothing else to go on. If the adapter stops being better at exactly that,
    the reason to carry a dependency has gone and this should say so.
    """
    built_in = converter_for("text/html")
    assert built_in is not None
    mine = built_in.convert(PAGE, "text/html")
    assert isinstance(mine, Converted)

    offered = next(e for e in TEXT_EXTRACTORS if e.load() is not None)
    theirs = _named(offered.name).convert(PAGE, "text/html")
    assert isinstance(theirs, Converted)

    kept_by_mine = {phrase for phrase in PLANTED if phrase in mine.text}
    kept_by_theirs = {phrase for phrase in PLANTED if phrase in theirs.text}

    assert kept_by_mine, "html@1 no longer keeps any of the planted boilerplate"
    assert kept_by_theirs < kept_by_mine, (
        f"{offered.name} keeps {sorted(kept_by_theirs)} and html@1 keeps "
        f"{sorted(kept_by_mine)}; the dependency is not buying what ADR-0028 says it does"
    )


@pytest.mark.skipif(not available(), reason="no optional extractor is installed")
def test_the_content_survives_both_html_converters() -> None:
    """The half that matters more. A dropped paragraph is worse than a kept
    banner: the corpus goes on answering questions without it, and nothing
    anywhere says so."""
    paragraph = "A tent that weighs 2.4kg is a tent you carry all day."
    for converter in known_converters():
        if "text/html" not in converter.media_types:
            continue
        result = converter.convert(PAGE, "text/html")
        assert isinstance(result, Converted), converter.name
        assert paragraph in result.text, converter.name


# -- the PDF half, which is reach rather than quality -----------------------

_PAGED = [e for e in PAGE_EXTRACTORS if e.load()]


@pytest.mark.skipif(not _PAGED, reason="no page extractor installed")
def test_the_pdf_adapter_reads_the_file_every_producer_writes() -> None:
    """`pdf_text@1` scans for `N 0 obj`.

    A PDF 1.5 keeps its catalogue, page tree and page inside a **compressed
    object stream**, where none of them is written that way, so the scan finds
    nothing and reports `no_pages`. That is correct, it is useless, and it is
    the shape of file almost every current producer emits.
    """
    built_in = converter_for("application/pdf")
    assert built_in is not None
    assert isinstance(built_in.convert(classic(), "application/pdf"), Converted), (
        "the built-in converter stopped reading the shape it was written for"
    )

    refused = built_in.convert(modern(), "application/pdf")
    assert not isinstance(refused, Converted)
    assert refused.reason == "no_pages"

    read = _named(_PAGED[0].name).convert(modern(), "application/pdf")
    assert isinstance(read, Converted), getattr(read, "reason", read)
    assert FIRST_LINE in read.text


@pytest.mark.skipif(not _PAGED, reason="no page extractor installed")
def test_a_better_extractor_does_not_change_what_an_offset_means() -> None:
    """A corpus rebuilt with `pdfium@1` still cites *page three*.

    This is what the paged shape is for. Alignment recovers character offsets
    where there is text to align against; a PDF has none, so the locator stays
    a page and both converters agree about it ([ADR-0025]).
    """
    built_in = converter_for("application/pdf")
    assert built_in is not None
    mine = built_in.convert(classic(), "application/pdf")
    theirs = _named(_PAGED[0].name).convert(classic(), "application/pdf")
    assert isinstance(mine, Converted)
    assert isinstance(theirs, Converted)

    assert mine.trace.source_unit == theirs.trace.source_unit == "opaque"
    assert [s.src for s in mine.trace.segments] == [s.src for s in theirs.trace.segments]
    assert mine.source_encoding == theirs.source_encoding == ""


@pytest.mark.skipif(not _PAGED, reason="no page extractor installed")
def test_a_page_with_no_text_is_still_refused_by_both() -> None:
    """OCR belongs to a program the owner runs before musubi ([ADR-0007]), and a
    better reader does not change that. A refusal that quietly became an empty
    document would be the worse outcome."""
    for converter in (converter_for("application/pdf"), _named(_PAGED[0].name)):
        assert converter is not None
        result = converter.convert(scanned(), "application/pdf")
        assert not isinstance(result, Converted)
        assert result.reason == "no_text_layer"
