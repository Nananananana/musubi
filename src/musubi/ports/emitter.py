"""Where a converted, cleansed unit goes, and what it becomes.

[ADR-0013] musubi publishes **one** output family -- documents, a manifest and
a trace map -- and ships no consumer-specific emitter. This port exists so that
a third party can write their own, out of tree, without a musubi release.

[ADR-0008] The gate depends on staging. A run writes into a staging area and
promotes when everything has passed; a credential means nothing is promoted, and
that is a property of the *decision* rather than of any one write.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

from ..domain.journal import Entry
from ..domain.manifest import Artefact
from ..domain.record import Unit
from ..domain.removal import RemovalRecord
from ..domain.screening import Finding
from ..domain.trace import TraceMap

__all__ = ["Artefact", "Document", "Emitter", "Previous", "Rendered", "Retained"]


@dataclass(frozen=True, slots=True)
class Retained:
    """One artefact as the last run recorded it, with everything a run that
    does not convert it again still has to say about it ([ADR-0036]).

    The removals and the findings travel with the artefact because the
    manifest is an account of the corpus and not of the run's effort: a
    re-sync that converted nothing still lists every rule that fired on the
    documents it holds, or the corpus it describes is one nobody can appeal.
    """

    artefact: Artefact
    removals: tuple[RemovalRecord, ...]
    findings: tuple[Finding, ...]


@dataclass(frozen=True, slots=True)
class Previous:
    """The corpus as the last run left it.

    `run_id` is ``None`` for a destination nothing has written yet, which is the
    first entry in a journal and the one with no parent.
    """

    run_id: str | None
    #: Artefact path to content hash. What `changes()` compares.
    artefacts: Mapping[str, str]
    #: Every path the last run recorded writing, documents and trace maps both.
    #: This is what withdrawal is allowed to delete.
    written: frozenset[str]
    #: Everything that decided the last run's outputs other than the bytes:
    #: `musubi`, `rulesets`, `screener`, `emitter`, `allowed`, as the manifest
    #: recorded them. A run whose own values differ in any of these converts
    #: everything, because the bytes being the same then proves nothing.
    decided_by: Mapping[str, object] = field(default_factory=dict)
    #: By unit key. What a run may carry forward instead of converting, once
    #: it has checked the bytes and the disk.
    retained: Mapping[str, Retained] = field(default_factory=dict)


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
    #: The source's own timestamp, to be put back on the written file
    #: (ADR-0022). ``None`` from a source that does not know.
    modified_at: float | None = None


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

    def previous(self) -> Previous:
        """What the corpus was before this run, read from its own manifest.

        One read rather than two: withdrawal needs the paths, and the journal
        needs the run id and the hashes ([ADR-0034]). A second reader of the
        same file is a second thing to keep in step.
        """
        ...

    def retain(self, artefact: Artefact, modified_at: float | None = None) -> bool:
        """Is this artefact still on the disk exactly as the manifest says?

        The check that makes carrying a record forward safe rather than
        hopeful ([ADR-0036]). A document somebody edited by hand, or a sidecar
        that went missing, is not the conversion the manifest describes, and a
        run that kept its record would leave a corpus whose account of itself
        is wrong -- the failure `musubi verify` exists to find, put there by
        `musubi sync`.

        ``modified_at`` is the source's timestamp, to be put on the retained
        document when the run promotes ([ADR-0022]) -- and not before, because
        a run that refuses must have touched nothing.
        """
        ...

    def append_journal(self, entry: Entry) -> None:
        """Record what this run did, after it has landed.

        After, never before. An entry written first and a promotion that then
        failed would claim a run that did not happen -- and the journal is the
        thing a reader trusts about what happened.
        """
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
