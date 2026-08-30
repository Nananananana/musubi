"""Where a converted, cleansed unit goes, and what it becomes.

[ADR-0013] musubi publishes **one** output family -- documents, a manifest and
a trace map -- and ships no consumer-specific emitter. This port exists so that
a third party can write their own, out of tree, without a musubi release.

[ADR-0008] The gate depends on staging. A run writes into a staging area and
promotes when everything has passed; a credential means nothing is promoted, and
that is a property of the *decision* rather than of any one write.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain.manifest import Artefact
from ..domain.record import Unit
from ..domain.trace import TraceMap

__all__ = ["Artefact", "Document", "Emitter", "Rendered"]


@dataclass(frozen=True, slots=True)
class Document:
    """A unit that has been converted and cleansed, ready to be written."""

    unit: Unit
    text: str
    trace: TraceMap
    converter: str
    #: How the source was read, so a character offset can become a byte offset
    #: for whoever holds the file ([ADR-0018]).
    source_encoding: str = "utf-8"
    source_bom_bytes: int = 0
    layer: str = "fact"


@dataclass(frozen=True, slots=True)
class Rendered:
    """A document as it will be written, before anything has been written.

    ``plan`` needs every number a ``sync`` would produce -- the artefact's path,
    its hash, its traceable coverage -- and needs them without touching the
    destination ([ADR-0012]). So rendering is separated from writing, and the
    only thing ``stage`` adds is the disk.
    """

    text: str
    trace: TraceMap
    artefact: Artefact


class Emitter(Protocol):
    """Satisfied by anything that can stage documents and promote them."""

    name: str

    def render(self, document: Document) -> Rendered:
        """What this document would become. Touches nothing."""
        ...

    def stage(self, document: Document) -> Artefact:
        """Write one document where it will wait, and say what it became."""
        ...

    def promote(self) -> tuple[str, ...]:
        """Move everything staged into place. Returns what moved."""
        ...

    def discard(self) -> None:
        """Throw the staging area away. Nothing reaches the destination."""
        ...
