"""What a source will read, and whether anything can convert it.

These are **set equalities, not loops**, and that is the point. A `for` over a
derived collection passes when the collection is empty, and a `parametrize` over
one was *skipped* when it was empty until `empty_parameter_set_mark` made it an
error. **An empty set is not equal to a non-empty set**, so writing the
expectation out closes the hole in the one place `pytest` cannot see into: a
plain assertion inside a single test, which is not a parameter set at all.

The shape is `iriguchi`'s, through `manager`. What it protects here is the
agreement between two lists kept in different files with no reason to stay in
step on their own — **a suffix a source will read, and a media type some
converter has claimed.** A source offering a suffix nothing can convert produces
a corpus quietly smaller than the folder; a converter claiming a media type no
source offers is a claim nothing feeds real input to.
"""

from __future__ import annotations

from musubi.infrastructure.converters import registered_media_types
from musubi.infrastructure.sources.filesystem import MEDIA_TYPES

#: Written out rather than derived from the thing under test. A derived
#: expectation passes whatever that thing says, and an empty dictionary would
#: satisfy one -- which is the failure this file exists to prevent.
READ_FROM_A_FOLDER = {
    ".md",
    ".markdown",
    ".mdown",
    ".mkd",
    ".txt",
    ".text",
    ".html",
    ".htm",
    ".xhtml",
}


def test_a_folder_source_reads_exactly_these_suffixes() -> None:
    """A suffix disappearing is a format that silently stops being ingested; one
    appearing is a format nobody has decided about."""
    assert MEDIA_TYPES.keys() == READ_FROM_A_FOLDER


def test_every_media_type_a_source_offers_is_one_a_converter_claims() -> None:
    """The half that produces a quietly smaller corpus.

    A source offering a suffix with no converter behind it discovers every such
    file, converts none, and reports each as `no_converter`. That is honest and
    it is still a corpus missing a whole format, so the disagreement belongs
    here rather than in a manifest somebody reads later.
    """
    unconvertible = set(MEDIA_TYPES.values()) - set(registered_media_types())
    assert not unconvertible, (
        f"a source offers {sorted(unconvertible)} and nothing converts it; the corpus "
        f"will be quietly smaller than the folder"
    )


def test_every_converter_is_reachable_from_some_source() -> None:
    """The other half. A converter no source can feed is a claim nothing tests
    against real input, however thorough its own unit tests are."""
    unreachable = set(registered_media_types()) - set(MEDIA_TYPES.values())
    assert not unreachable, f"{sorted(unreachable)} is claimed by a converter no source offers"


def test_the_expectations_themselves_have_content() -> None:
    """The guard on the guards.

    Every assertion above is an equality or a set difference, and both are
    satisfied vacuously by empty operands -- `set() - set()` is empty, and
    `{}.keys() == set()` is true. So the operands are checked for having
    something in them, which is the same move as asserting a collection is
    non-empty where it is built.
    """
    assert READ_FROM_A_FOLDER
    assert MEDIA_TYPES
    assert registered_media_types()
