"""What a source can hand over, and what a converter can read, are two lists.

Nothing checked that they agree. They do today — measured, not assumed — and
that is the reason to write this now rather than after the first report of a
converter that never runs.

Two ways it can go wrong, and neither is loud:

- **A source lists a suffix no converter claims.** Every file of that format is
  read, opened, and skipped as `no_converter`. The corpus is missing a format
  and the report says so per file, which is honest and easy to scroll past.
- **A converter claims a media type no source produces.** The converter is
  registered, `musubi config` lists it, and no sync can ever reach it: a
  capability that exists and cannot be used, which is worse than one that does
  not exist because it reads as available.

This is the same family as the five findings before it ([ADR-0047] through
[ADR-0050]): a list beside a thing has no reason to change when the thing does.
So the population here is walked out of the sources package and the converter
registry, and an exemption has to be named with its reason.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

import pytest

import musubi.infrastructure.sources as sources
from musubi.infrastructure.converters import known_converters, registered_media_types

#: Media types a source hands over that **no converter claims**, each with the
#: reason. Listed rather than omitted, the way `NOT_FLOORED` and `NOT_PRINTED`
#: are: an exemption nobody wrote down cannot be told from an oversight.
UNCONVERTED: dict[str, str] = {
    "text/csv": (
        "a Notion export writes a `.csv` beside every database view. It is "
        "listed by the source so that discovery **reports** it rather than "
        "passing over it in silence, and skipped for want of a converter like "
        "any other format. A table is not prose and musubi has no converter "
        "that could carry a map back through one."
    ),
}


def tables() -> dict[str, dict[str, str]]:
    """Every `MEDIA_TYPES` table in the sources package, by module.

    Walked rather than imported by name. A source added tomorrow with its own
    suffix table is covered here without anybody editing this file, which is
    the whole point of the exercise.
    """
    found: dict[str, dict[str, str]] = {}
    for module in pkgutil.walk_packages(sources.__path__, prefix=f"{sources.__name__}."):
        table: Any = getattr(importlib.import_module(module.name), "MEDIA_TYPES", None)
        if isinstance(table, dict):
            found[module.name.rsplit(".", 1)[-1]] = table
    return found


def produced() -> set[str]:
    return {media for table in tables().values() for media in table.values()}


# -- the populations, before anything is asserted about them ----------------


def test_there_are_tables_to_compare() -> None:
    """A walk that finds nothing leaves every test below iterating over an
    empty set and passing."""
    assert len(tables()) >= 2, f"found only {sorted(tables())}"
    assert produced()
    assert registered_media_types()


# -- the two directions ------------------------------------------------------


@pytest.mark.parametrize("media", sorted(produced()), ids=lambda m: m)
def test_every_format_a_source_offers_has_a_converter_or_a_named_reason(media: str) -> None:
    """A source lists a suffix so that a file of that kind is *reported*. If
    nothing can convert it, that is a decision and it should be written down
    where somebody adding a converter will see it."""
    if media in registered_media_types():
        return
    assert media in UNCONVERTED, (
        f"{media!r} is offered by a source and no converter claims it. Either "
        f"register one, or name it in UNCONVERTED with the reason."
    )
    assert len(UNCONVERTED[media]) > 80, f"{media!r} is excused without a real reason"


@pytest.mark.parametrize("media", sorted(registered_media_types()), ids=lambda m: m)
def test_every_format_a_converter_claims_can_reach_it(media: str) -> None:
    """The direction that fails silently.

    A converter claiming a media type nothing produces is registered, listed by
    `musubi config`, and unreachable by any sync -- which reads as a capability
    rather than as an absence. `musubi.convert(path)` cannot reach it either:
    the API resolves a suffix through `FilesystemSource.MEDIA_TYPES`, the same
    table walked here.
    """
    assert media in produced(), (
        f"{registered_media_types()[media]} claims {media!r} and no source hands "
        f"one over. It is registered and no sync can reach it."
    )


def test_the_exemptions_still_describe_something() -> None:
    """The register checked backwards. An entry for a format no source offers
    any more is an exemption outliving its reason."""
    stale = sorted(set(UNCONVERTED) - produced())
    assert not stale, f"{stale} are excused and no source offers them"


# -- and the suffixes themselves --------------------------------------------


@pytest.mark.parametrize("module", sorted(tables()), ids=lambda m: m)
def test_every_suffix_is_one_a_path_can_actually_have(module: str) -> None:
    """`Path.suffix` keeps the dot and musubi lowercases before the lookup, so
    a key without a dot or with a capital in it is an entry that never matches:
    a format listed as readable and silently unread."""
    for suffix in tables()[module]:
        assert suffix.startswith("."), f"{suffix!r} is not a suffix"
        assert suffix == suffix.lower(), f"{suffix!r} can never match a lowercased suffix"
        assert suffix.count(".") == 1, f"{suffix!r} is not what `Path.suffix` returns"


def test_the_api_reads_the_same_table_a_sync_walks() -> None:
    """Stated in `media_type_of`'s docstring -- *the same table
    `FilesystemSource` walks a folder with* -- and worth holding, because two
    tables would mean `musubi.convert` reading a file a sync skips."""
    from musubi.api import media_type_of

    for suffix, media in tables()["filesystem"].items():
        assert media_type_of(f"note{suffix}") == media
        assert media_type_of(f"note{suffix.upper()}") == media, "a shouting filename"
    assert media_type_of("note.unknown") is None


def test_every_converter_in_the_registry_claims_something() -> None:
    """A converter claiming no media type is registered, listed, and reachable
    only by being named in a settings file -- which is a real thing to be
    ([ADR-0028]) and worth telling apart from an empty tuple by accident."""
    for converter in known_converters():
        claims = getattr(converter, "media_types", ())
        assert claims, f"{converter.name} claims no media type at all"
