"""Where a converted, cleansed unit goes, and what it becomes.

[ADR-0013] musubi publishes **one** output family -- documents, a manifest and
a trace map -- and ships no consumer-specific emitter. This port exists so that
a third party can write their own, out of tree, without a musubi release.

[ADR-0008] The gate depends on staging. A run writes into a staging area and
promotes when everything has passed; a credential means nothing is promoted, and
that is a property of the *decision* rather than of any one write.
"""

from __future__ import annotations

from collections.abc import Iterable
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

    def begin(self) -> None:
        """Clear whatever a previous run left behind and start again."""
        ...

    def render(self, document: Document) -> Rendered:
        """What this document would become. Touches nothing."""
        ...

    def stage(self, document: Document) -> Artefact:
        """Write one document where it will wait, and say what it became."""
        ...

    def stage_manifest(self, body: str) -> None:
        """The run's own account, written last and promoted with the rest."""
        ...

    def promote(self) -> tuple[str, ...]:
        """Move everything staged into place. Returns what moved."""
        ...

    def discard(self) -> None:
        """Throw the staging area away. Nothing reaches the destination."""
        ...

    def previously_written(self) -> frozenset[str]:
        """What the last run recorded writing here, from its own manifest.

        The previous manifest is the ledger. There is no separate store,
        because a corpus that already says what is in it does not need one --
        and a ledger that can disagree with the corpus is a second source of
        truth to keep in step.
        """
        ...

    def withdraw(self, paths: Iterable[str]) -> tuple[str, ...]:
        """Take these out of the corpus. Returns what was actually removed.

        Only ever a path a previous manifest recorded writing. musubi deletes
        what it wrote and never what it merely found, so a folder somebody put
        something else in survives a sync intact.
        """
        ...
