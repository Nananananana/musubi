"""One suite every converter must pass, whoever wrote it.

Until this file, each converter had its own tests and nothing held them to a
common standard. A converter registered tomorrow -- by musubi, by an adapter, or
by a third party calling `register_converter` -- could ship with a map that does
not tile, offsets outside its source, or a crash on a truncated file, and every
test in the repository would stay green. Each one only sees its own half.

Requested in review as a **conformance suite**, and the argument for it is the
same one `docs/contracts.md` makes about schemas: a promise that only its author
checks is a promise about its author.

## What is asserted, and what deliberately is not

Everything here is a property of [ADR-0004]'s bargain that holds for **any**
converter over **any** input:

```text
the tiling covers the output exactly, with no gap and no overlap
a verbatim run reads the same on both sides
no segment points outside the source it claims
the same bytes twice give the same answer     (ADR-0003)
rubbish is refused with a reason, never raised (ADR-0008 keeps the run going)
the locator is one musubi knows, and the encoding agrees with it
```

**Not quality.** Whether the text is *good* is a per-format question with a
per-format fixture, and `tools/html_coverage.py` and `tools/pdf_coverage.py`
answer it with numbers. This file answers the question those cannot: is the map
**structurally honest**, whatever the text turned out to be.

The distinction is the review's: *「変換できた」と「正しく変換された」を分離評価する*.
This is the first half. The second needs fixtures with known answers, which
v0.4 owes.

## Verified potent, and verified automatic

A converter deliberately violating the bargain -- a verbatim run whose sides are
different lengths, and a `src` reaching 99 characters past the end of its source
-- was registered through the ordinary `offer_converter` path with **no change
to this file**. It failed **nine of the nine** properties that apply to it.

That is the point rather than a footnote: a third party who registers a
converter is held to the same standard as musubi's own, and nobody has to
remember to add them here.
"""

from __future__ import annotations

import pytest

from musubi.domain.trace import CHARACTERS, OPAQUE, Kind
from musubi.infrastructure.converters import known_converters
from musubi.ports.converter import Converted, Converter, Unconvertible
from pdf_fixtures import classic

#: One readable sample per media type any converter might claim.
#:
#: Keyed by media type rather than by converter, so that **adding a converter
#: needs no change here** unless it claims a format nothing else does -- and if
#: it does, the coverage guard below turns red and says so.
SAMPLES: dict[str, bytes] = {
    "text/markdown": "# ギア設計\n\nテントは 2.4kg。ブーツのほうが効く。\n".encode(),
    "text/plain": b"Some ordinary prose, and a second line after it.\n",
    "text/html": (
        b"<!doctype html><html><body><nav><a href='/'>Home</a></nav>"
        b"<article><p>A tent that weighs 2.4kg is a tent you carry all day.</p>"
        b"<p>The stove is the part people get wrong, every time.</p></article>"
        b"<footer>Copyright 2026</footer></body></html>"
    ),
    "application/xhtml+xml": (
        b"<?xml version='1.0'?><html xmlns='http://www.w3.org/1999/xhtml'><body>"
        b"<article><p>A tent that weighs 2.4kg is a tent you carry all day.</p>"
        b"</article></body></html>"
    ),
    "application/pdf": classic(),
    "text/csv": b"item,mass\ntent,2.4\nboots,1.1\n",
}


def _pairs() -> list[tuple[str, str]]:
    """Every (converter, media type) a sample exists for."""
    found = [
        (converter.name, media_type)
        for converter in known_converters()
        for media_type in converter.media_types
        if media_type in SAMPLES
    ]
    assert found, "no converters have samples; every test below would run zero times"
    return sorted(found)


def _named(name: str) -> Converter:
    return next(converter for converter in known_converters() if converter.name == name)


def convert(name: str, media_type: str) -> Converted:
    result = _named(name).convert(SAMPLES[media_type], media_type)
    if not isinstance(result, Converted):
        pytest.skip(f"{name} refuses this sample: {result.reason}")
    return result


PAIRS = _pairs()
IDS = [f"{name}:{media}" for name, media in PAIRS]


# -- the population itself --------------------------------------------------


def test_every_registered_converter_is_covered_by_this_suite() -> None:
    """The guard that makes the rest of the file mean something.

    A parametrised suite is only as good as its parameters, and a converter that
    claims a media type nothing here has a sample for would be **silently
    exempt** from every property below. This is the failure that
    `tests/test_what_is_read_and_written.py` exists to prevent one layer up, and
    it belongs here too.
    """
    claimed = {media for converter in known_converters() for media in converter.media_types}
    unsampled = sorted(claimed - set(SAMPLES))

    assert not unsampled, (
        f"{unsampled} is claimed by a converter and has no sample in this file, so that "
        f"converter passes conformance by not being tested. Add a sample."
    )

    covered = {name for name, _ in PAIRS}
    assert covered == {converter.name for converter in known_converters()}


# -- the tiling, which is the whole bargain ---------------------------------


@pytest.mark.parametrize(("name", "media_type"), PAIRS, ids=IDS)
def test_the_map_tiles_the_output_exactly(name: str, media_type: str) -> None:
    """No gap and no overlap. A map with a gap answers a query with silence and
    one with an overlap answers it twice."""
    result = convert(name, media_type)

    at = 0
    for segment in result.trace.segments:
        assert segment.out.start == at, f"gap or overlap at {at}: {segment.out}"
        at = segment.out.end
    assert at == result.trace.artefact_length == len(result.text)


@pytest.mark.parametrize(("name", "media_type"), PAIRS, ids=IDS)
def test_no_segment_points_outside_the_source_it_claims(name: str, media_type: str) -> None:
    """An offset past the end of the source is an offset that resolves to
    nothing, and a reader following it opens a file and finds the wrong place --
    or no place at all."""
    result = convert(name, media_type)

    for segment in result.trace.segments:
        assert 0 <= segment.src.start <= segment.src.end <= result.trace.source_length, (
            f"{segment.kind.value} segment claims {segment.src} of a source that is "
            f"[0:{result.trace.source_length}]"
        )


@pytest.mark.parametrize(("name", "media_type"), PAIRS, ids=IDS)
def test_a_verbatim_run_is_the_same_length_on_both_sides(name: str, media_type: str) -> None:
    """Verbatim claims the correspondence holds at **every interior offset**, and
    an offset is shifted by a constant to get there. Two different lengths mean
    the constant is wrong somewhere inside, silently."""
    result = convert(name, media_type)
    if result.trace.source_unit != CHARACTERS:
        pytest.skip("a source counted in pages has no character-for-character run")

    for segment in result.trace.segments:
        if segment.kind is Kind.VERBATIM:
            assert segment.out.length == segment.src.length, segment


@pytest.mark.parametrize(("name", "media_type"), PAIRS, ids=IDS)
def test_a_removal_occupies_no_output(name: str, media_type: str) -> None:
    """[ADR-0005]. A removal that occupied output would be a subtraction that
    also added something, which is not a subtraction."""
    result = convert(name, media_type)

    for segment in result.trace.segments:
        if segment.kind is Kind.REMOVAL:
            assert segment.out.is_empty, segment
            assert segment.rule, "a removal with no rule cannot be appealed"


# -- what the map says about itself -----------------------------------------


@pytest.mark.parametrize(("name", "media_type"), PAIRS, ids=IDS)
def test_the_locator_is_one_musubi_knows_and_the_encoding_agrees(
    name: str, media_type: str
) -> None:
    """`[2:3]` is one character or one page and the numbers look identical, so
    the unit has to be stated -- and a source counted in pages has no encoding
    to offer, because nothing was decoded ([ADR-0025])."""
    result = convert(name, media_type)

    assert result.trace.source_unit in {CHARACTERS, OPAQUE}
    if result.trace.source_unit == OPAQUE:
        assert result.source_encoding == "", (
            "an opaque source claims an encoding, which invites a caller to compute a "
            "byte offset that does not exist"
        )
    else:
        assert result.source_encoding, "a character-counted source states no encoding"


@pytest.mark.parametrize(("name", "media_type"), PAIRS, ids=IDS)
def test_the_converter_names_itself_for_the_manifest(name: str, media_type: str) -> None:
    """A corpus says which implementation built each artefact, so a rebuild with
    a different converter is visible rather than inferred."""
    result = convert(name, media_type)

    assert result.converter == name
    assert "@" in name, f"{name} carries no version; a converter changing is a data change"


# -- the promises that are not about the map --------------------------------


@pytest.mark.parametrize(("name", "media_type"), PAIRS, ids=IDS)
def test_the_same_bytes_twice_give_the_same_answer(name: str, media_type: str) -> None:
    """[ADR-0003]. A converter that is not deterministic makes `run_id`
    meaningless and `verify` unable to verify anything."""
    first = convert(name, media_type)
    second = convert(name, media_type)

    assert first.text == second.text
    assert first.trace.segments == second.trace.segments
    assert (first.converter, first.source_encoding) == (second.converter, second.source_encoding)


@pytest.mark.parametrize(("name", "media_type"), PAIRS, ids=IDS)
def test_rubbish_is_refused_with_a_reason_rather_than_raised(name: str, media_type: str) -> None:
    """A folder of thousands holds a truncated file, and [ADR-0008] wants a run
    that stops on a credential and **keeps going** past one of those.

    An exception escaping a converter takes the whole sync with it -- and for an
    adapter, the code that would raise is not musubi's.
    """
    noise = bytes([0, 1, 2]) + b" not a document at all " + bytes([250, 251, 255])
    result = _named(name).convert(noise, media_type)

    if isinstance(result, Converted):
        pytest.skip(f"{name} read something out of it; that is allowed, and it did not raise")
    assert isinstance(result, Unconvertible)
    assert result.reason, "refused without a reason a manifest can report"
    assert result.converter == name


@pytest.mark.parametrize(("name", "media_type"), PAIRS, ids=IDS)
def test_an_empty_file_is_answered_rather_than_crashed_on(name: str, media_type: str) -> None:
    """Empty files exist. A converter that raises on one turns a folder holding
    a stray zero-byte file into a folder that cannot be synced."""
    result = _named(name).convert(b"", media_type)

    if isinstance(result, Converted):
        assert result.text == "" or result.trace.artefact_length == len(result.text)
    else:
        assert result.reason
