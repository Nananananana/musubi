"""Reading a destination back: what `musubi trace` needs, and nothing more.

The emitter writes a corpus and this reads one, and keeping them apart is not
ceremony: `trace` runs against a folder somebody else built, possibly with a
musubi that is not this one, and it should have no way to modify it.

The port exists because following a citation is *arithmetic* -- decoding,
hashing, converting a character offset into a byte offset -- and arithmetic
belongs above the layer that knows what a file is. What is behind here is only
the reading.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..domain.trace import TraceMap

__all__ = ["CorpusReader", "Held", "SourceReference"]


@dataclass(frozen=True, slots=True)
class SourceReference:
    """What a trace map says about where its artefact came from."""

    source_id: str
    unit_key: str
    content_hash: str
    media_type: str
    encoding: str
    bom_bytes: int


@dataclass(frozen=True, slots=True)
class Held:
    """One artefact's map, and what it says about its source."""

    trace: TraceMap
    source: SourceReference
    converter: str

    @property
    def source_unit(self) -> str:
        """What the map's source offsets index. The map is the holder."""
        return self.trace.source_unit


class CorpusReader(Protocol):
    """Satisfied by anything that can read a destination musubi wrote."""

    def artefact(self, key: str) -> str:
        """The document, as it was written."""
        ...

    def held(self, key: str) -> Held:
        """The map for one artefact, read against its contract."""
        ...

    def source(self, reference: SourceReference) -> tuple[Path, bytes] | None:
        """The file the artefact was made from, if it is still findable.

        ``None`` rather than a raise: the map alone is still an answer, and a
        missing source degrades a report rather than failing it.
        """
        ...

    def manifest_document(self) -> dict[str, Any]:
        """The manifest as it is on disk, parsed and not interpreted.

        A dict rather than a :class:`~musubi.domain.manifest.Manifest`, because
        the domain renders manifests and does not read them, and because a
        checker that reconstructs the producer's object can only find faults the
        producer's object can represent. ``verify`` reads what is written.
        """
        ...

    def artefact_bytes(self, key: str) -> bytes:
        """The document as bytes, for hashing it as it sits on the disk."""
        ...

    def key_of(self, artefact_path: str, trace_path: str) -> str:
        """The key a manifest's two paths refer to, in this corpus's layout.

        Where a corpus puts its documents and its maps is the reader's business
        and not the checker's -- an application that stripped ``documents/``
        itself would be a second place that knows the layout, and the two would
        drift. Raises :class:`~musubi.errors.ContractError` when the paths are
        not where the layout says, which is itself a thing worth reporting.
        """
        ...
