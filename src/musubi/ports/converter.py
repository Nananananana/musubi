"""Bytes in; text **and a map back to them** out. [ADR-0004] as a signature.

Every document-to-Markdown tool in existence has the same shape: bytes in,
string out. That is the shape musubi cannot use, because the correspondence is
the product. A converter here returns a :class:`~musubi.domain.trace.TraceMap`
alongside the text, or it returns :class:`Unconvertible` and says why.

**There is no third option.** A converter that produced text without a map would
put a hole at the bottom of the evidence chain, which is the hole this project
exists to close, so the type does not allow it.

``Unconvertible`` is a value rather than an exception because it is not an
error: a scanned PDF with no text layer, a file in an encoding musubi will not
guess at, an archive member that is a directory. Each is a thing the manifest
reports with its reason, and a reason that travels as a value cannot be
swallowed by a bare `except`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain.trace import TraceMap

__all__ = ["Converted", "Converter", "Unconvertible"]


@dataclass(frozen=True, slots=True)
class Converted:
    """Text, and where every character of it came from."""

    text: str
    trace: TraceMap
    #: The converter and its version, for the manifest: ``markdown@1``.
    converter: str
    #: How the source was read. With these and the file, a character offset in
    #: the map becomes a byte offset in the original ([ADR-0018]); without the
    #: file, nothing can, which is why the map does not pretend to.
    source_encoding: str = "utf-8"
    source_bom_bytes: int = 0


@dataclass(frozen=True, slots=True)
class Unconvertible:
    """This unit was not turned into text, and this is why.

    ``reason`` is a stable token a reader can count and filter on --
    ``no_text_layer``, ``undecodable`` -- and ``detail`` is the sentence a
    person needs.
    """

    reason: str
    detail: str = ""
    converter: str = ""


class Converter(Protocol):
    """Satisfied by anything that turns bytes into traceable text."""

    #: Named in the manifest, so a corpus says which implementation built it.
    name: str
    #: The media types this claims, as a source reports them.
    media_types: tuple[str, ...]

    def convert(self, content: bytes, media_type: str) -> Converted | Unconvertible:
        """Turn these bytes into text and a map, or say why not."""
        ...
