"""Converters, and the registry that picks one.

Adding a format is registering a converter. Nothing else in the library
changes, and the converter does not have to import the port it satisfies -- it
only has to have the right shape (`kiseki`'s ADR-0004).

A media type belongs to one converter. Registering over an existing claim is
allowed and returns what it displaced, so an override is deliberate and
reversible rather than a silent last-write-wins.

**Claiming and being known are two different things.** `offer_converter` makes a
converter selectable by name without giving it a media type, which is what an
optional adapter needs ([ADR-0028]): installing `musubi[html]` must not silently
change what every existing corpus is built with. The adapter is there, `musubi
config` lists it, and `[converters]` in a settings file is how it starts being
used.
"""

from __future__ import annotations

from collections.abc import Mapping

from ...ports.converter import Converter
from .external import adapters
from .html import HtmlConverter
from .pdf import PdfConverter
from .text import MarkdownConverter, PlainTextConverter, TextConverter

__all__ = [
    "HtmlConverter",
    "MarkdownConverter",
    "PdfConverter",
    "PlainTextConverter",
    "TextConverter",
    "claimed_converters",
    "converter_for",
    "known_converters",
    "offer_converter",
    "register_converter",
    "registered_media_types",
]

_by_media_type: dict[str, Converter] = {}
_by_name: dict[str, Converter] = {}


def register_converter(converter: Converter, *, replace: bool = False) -> tuple[Converter, ...]:
    """Claim this converter's media types. Returns whatever it displaced."""
    if not converter.media_types:
        raise ValueError(f"converter {converter.name!r} claims no media types")

    displaced: list[Converter] = []
    for media_type in converter.media_types:
        held = _by_media_type.get(media_type)
        if held is not None and held.name != converter.name:
            if not replace:
                raise ValueError(
                    f"{media_type!r} is already claimed by {held.name!r}; pass "
                    f"replace=True to override it deliberately"
                )
            displaced.append(held)

    for media_type in converter.media_types:
        _by_media_type[media_type] = converter
    _by_name[converter.name] = converter
    return tuple(dict.fromkeys(displaced))


def offer_converter(converter: Converter) -> None:
    """Make this selectable by name without claiming anything.

    An optional adapter is *offered* rather than registered. A dependency that
    appeared in an environment must not change what a sync produces; the corpus
    a folder builds is decided by its settings, not by what happens to be
    installed next to it.
    """
    _by_name[converter.name] = converter


def converter_for(media_type: str) -> Converter | None:
    """The converter claiming this media type, or ``None``.

    ``None`` rather than a raise: a folder holds files nobody meant to convert,
    and the caller reports what it skipped ([ADR-0005]).
    """
    return _by_media_type.get(media_type)


def known_converters() -> tuple[Converter, ...]:
    """Every converter that can be named, claimed or merely offered."""
    return tuple(sorted(_by_name.values(), key=lambda c: c.name))


def claimed_converters() -> tuple[Converter, ...]:
    """Only the ones a media type currently resolves to without being asked."""
    seen = {c.name: c for c in _by_media_type.values()}
    return tuple(sorted(seen.values(), key=lambda c: c.name))


def registered_media_types() -> Mapping[str, str]:
    """Every claimed media type and the converter holding it."""
    return {media: converter.name for media, converter in sorted(_by_media_type.items())}


for _builtin in (MarkdownConverter(), PlainTextConverter(), HtmlConverter(), PdfConverter()):
    register_converter(_builtin)

# Offered, never claimed. Installing an extra adds a name a settings file can
# use; it does not change what any folder already builds.
for _adapter in adapters():
    offer_converter(_adapter)
