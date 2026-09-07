"""The floors, checked, and the register checked against the converters.

`tools/html_coverage.py` and its siblings measured quality per converter and
printed. **Nothing failed when a number fell** — a change dropping
`trafilatura@1` from 99.7% traceable to 70% passed every test here (#84).

The register in `tests/converter_floors.py` is the numbers and the reasons.
This is the gate. `tools/floors.py` prints the same measurements
from the same function, so the report and the gate cannot disagree about what
a number is.

The most important test in this file is the last one. A floor register is only
worth what its population is: a converter added tomorrow with no floor is not
measured, and nothing would say so.
"""

from __future__ import annotations

import pytest

from converter_floors import BOUNDS, FLOORS, HTML, NOT_FLOORED, PDF, Floor, claiming, measured

MEASURED = measured()


def named(floor: Floor) -> str:
    return f"{floor.converter}:{floor.measure}"


# -- the floors themselves --------------------------------------------------


@pytest.mark.parametrize("floor", FLOORS, ids=named)
def test_a_converter_has_not_fallen_below_its_floor(floor: Floor) -> None:
    now = MEASURED.get((floor.converter, floor.measure))
    assert now is not None, f"nothing measures {named(floor)} any more"
    assert now >= floor.floor, (
        f"{named(floor)} is {now:.3f} and its floor is {floor.floor:.3f}, set "
        f"{floor.when} when it measured {floor.measured:.3f}. Either this is a "
        f"regression, or the floor is wrong and moving it is a commit with a "
        f"reason in it."
    )


@pytest.mark.parametrize("floor", FLOORS, ids=named)
def test_every_floor_sits_below_what_it_was_measured_at(floor: Floor) -> None:
    """Floors, not targets. A floor set *at* the measurement makes every honest
    experiment a build failure, which is what `docs/proposals/0001-the-design.md`
    §9 warns against by name.

    The exception is a measure that is a **bound** — `reads a PDF 1.5` is one
    or zero, and headroom in it would mean accepting half of it.
    """
    assert floor.floor <= floor.measured
    if floor.measure not in BOUNDS and floor.measured not in (0.0, 1.0):
        assert floor.headroom > 0, (
            f"{named(floor)} has no headroom. A floor at today's number turns "
            f"an experiment into a failure."
        )


@pytest.mark.parametrize("floor", FLOORS, ids=named)
def test_every_floor_says_what_put_it_there(floor: Floor) -> None:
    """A number with no reason is a number nobody can move. ADR-0033's rule for
    the constant register, applied to this one."""
    assert len(floor.why) > 60, f"{named(floor)} has no real reason written down"
    assert floor.when


def test_the_measurements_are_the_ones_recorded(request: pytest.FixtureRequest) -> None:
    """Not exact equality: a measurement drifting a little is the reason floors
    have headroom. What this catches is a *register* that has come loose from
    reality -- an entry claiming it measured 0.99 where it now reads 0.4, which
    would mean the headroom is not what somebody thought it was.
    """
    adrift = [
        (named(floor), floor.measured, MEASURED[floor.converter, floor.measure])
        for floor in FLOORS
        if (floor.converter, floor.measure) in MEASURED
        and abs(MEASURED[floor.converter, floor.measure] - floor.measured) > 0.1
    ]
    assert not adrift, f"the register's recorded measurements no longer hold: {adrift}"


# -- the bounds, which have no headroom on purpose --------------------------


@pytest.mark.parametrize("converter", claiming(HTML), ids=lambda c: c.name)
def test_every_planted_paragraph_survives(converter: object) -> None:
    """Losing one is not a score getting worse. It is a corpus answering
    questions without something the page said, and nothing saying so."""
    name = converter.name  # type: ignore[attr-defined]
    assert MEASURED[name, "content kept"] == 1.0, BOUNDS["content kept"]


@pytest.mark.parametrize("converter", claiming(PDF), ids=lambda c: c.name)
def test_a_page_with_no_text_layer_is_still_refused(converter: object) -> None:
    name = converter.name  # type: ignore[attr-defined]
    assert MEASURED[name, "refuses a scan"] == 1.0, BOUNDS["refuses a scan"]


@pytest.mark.parametrize("converter", claiming(PDF), ids=lambda c: c.name)
def test_every_pdf_reader_still_reads_the_shape_it_was_written_against(
    converter: object,
) -> None:
    name = converter.name  # type: ignore[attr-defined]
    assert MEASURED[name, "reads a PDF 1.4"] == 1.0, BOUNDS["reads a PDF 1.4"]


# -- and the population, which is what makes the rest worth anything --------


def test_every_measured_converter_has_a_floor_or_a_reason_it_has_none() -> None:
    """The guard this register exists to have.

    A converter registered tomorrow that claims HTML or PDF is measured by
    nothing unless somebody remembers to add a floor. So the population is read
    out of the registry rather than listed here, and a converter with neither a
    floor nor a named reason turns this red.
    """
    floored = {floor.converter for floor in FLOORS}
    claim = {c.name for c in (*claiming(HTML), *claiming(PDF))}  # type: ignore[attr-defined]

    assert claim, "no converter claims HTML or PDF; this suite is measuring nothing"
    missing = sorted(claim - floored - set(NOT_FLOORED))
    assert not missing, (
        f"{missing} claim a media type these measures cover and have no floor. "
        f"Add one, or name the converter in NOT_FLOORED with the reason."
    )


def test_no_floor_names_a_converter_that_is_not_here() -> None:
    """The register checked in the other direction: an entry for a converter
    nobody registers is a floor that passes by never being measured."""
    claim = {c.name for c in (*claiming(HTML), *claiming(PDF))}  # type: ignore[attr-defined]
    stale = sorted({floor.converter for floor in FLOORS} - claim)
    # `pdfium@1` is an optional extra, so its absence is a smaller measurement
    # rather than a stale entry -- and saying which is which is the point.
    from musubi.infrastructure.converters.external import available

    optional = {extractor.name for extractor in available()} | {"pdfium@1", "trafilatura@1"}
    assert not [name for name in stale if name not in optional], stale
