"""What a run did, as values, and as the document it becomes.

[ADR-0002] The manifest is a document that stands on its own. The Python objects
here are a convenience over it and never the other way round: the questions a
manifest answers get asked by a reviewer holding a JSON file, by a shell script
six months from now, and by the next program in the chain, which does not import
musubi.

[ADR-0003] ``run_id`` is over exactly the inputs that determine the output.
**Not** ``created_at``, so two runs of the same input share an id and the diff
between their artefacts is empty. **Not** the source's root path, so a corpus
built on one machine has the same id as the same corpus built on another --
an id that embeds an absolute path is an id nobody else can re-derive.

[ADR-0005] ``removals`` and ``skipped`` are long and boring on purpose. An
account nobody reads is still an account somebody *can* read, and the
alternative is an artefact that cannot be appealed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .hashing import Canonical, hash_of
from .removal import RemovalRecord
from .screening import Finding

__all__ = [
    "CONTRACT",
    "LIMITS",
    "Artefact",
    "Coverage",
    "Manifest",
    "Skip",
    "SourceRecord",
    "render",
]

#: Not frozen. v0.2 writes the schema and freezes the name once a second program
#: has produced and consumed one ([ADR-0002]).
CONTRACT = "musubi.sync-manifest/1-draft"

#: What the document does not say, carried *in* the document. The artefact
#: travels and the documentation does not.
LIMITS: tuple[str, ...] = (
    "A traceable character means an offset resolves to a place in the source. "
    "It does not mean the conversion read the document in the right order.",
    "How precisely it resolves depends on the converter, and the totals here do "
    "not say. A character map answers with a character; a PDF's map answers with "
    "a page. Each trace map states its own `source_unit`, and a corpus of mixed "
    "formats has one coverage number over more than one meaning of traceable.",
    "Where a map's `source_unit` is `characters`, turning a source offset into a "
    "byte offset takes the encoding, the byte-order mark's length and the file "
    "itself. Where it is not, there is no byte offset to turn it into.",
    "The screener catches credential formats their issuers made recognisable. "
    "Its recall against a labelled corpus has not been measured, and no number "
    "is claimed for it.",
    "Removals are recorded by hash, not by value. Confirming one requires the source.",
    "Rules remove what they name and nothing else. That is not a guarantee about what is left.",
)


@dataclass(frozen=True, slots=True)
class Artefact:
    """One thing that was written, or that a plan says would be."""

    #: Relative to the destination, and derived from the ``unit_key`` rather
    #: than from the source's filename ([ADR-0013]) -- `kiseki-notes` hashes the
    #: path to make a note's stable reference, so a name that moved would make
    #: every note look new.
    path: str
    content_hash: str
    trace_path: str
    source_id: str
    unit_key: str
    converter: str
    traceable_characters: int
    characters: int
    layer: str
    #: The hash of the **source** bytes this was converted from -- the trace
    #: map already carries it; the manifest carries it so that a re-sync can
    #: ask *did the bytes change* without opening ten thousand sidecars
    #: ([ADR-0036]). Empty on a manifest written before it existed, and not part
    #: of ``run_id``: the id is over the outputs, and an input hash added to it
    #: would change the id of every existing corpus on upgrade.
    source_hash: str = ""

    @property
    def traceable_coverage(self) -> float:
        """1.0 for an empty artefact: no character fails the guarantee."""
        if not self.characters:
            return 1.0
        return self.traceable_characters / self.characters


@dataclass(frozen=True, slots=True)
class Skip:
    """Something that was seen and not carried, and why."""

    source_id: str
    origin: str
    reason: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """One source, as the manifest names it."""

    source_id: str
    adapter: str
    key_derivation: str
    units: int
    #: Every bound that shortened what this source offered ([ADR-0005]).
    caps: tuple[str, ...] = ()
    #: Recorded for a reader and **excluded from the run id**: an id that
    #: embedded it would differ between two machines holding the same corpus.
    root: str = ""


@dataclass(frozen=True, slots=True)
class Coverage:
    """The denominators, published beside the numerators.

    ``emitted`` alone would let a reader compute a ratio against the wrong
    total, and they would.
    """

    units_read: int
    emitted: int
    skipped: int
    characters: int
    traceable_characters: int

    @property
    def traceable_coverage(self) -> float:
        if not self.characters:
            return 1.0
        return self.traceable_characters / self.characters


@dataclass(frozen=True, slots=True)
class Manifest:
    """What a run did. ``kind`` is ``plan`` or ``sync``."""

    kind: str
    musubi_version: str
    sources: tuple[SourceRecord, ...] = ()
    rulesets: tuple[tuple[str, str], ...] = ()
    converters: tuple[str, ...] = ()
    screener: str = ""
    emitter: str = ""
    artefacts: tuple[Artefact, ...] = ()
    removals: tuple[tuple[str, RemovalRecord], ...] = ()
    skipped: tuple[Skip, ...] = ()
    findings: tuple[tuple[str, Finding], ...] = ()
    #: Allowances the owner granted, recorded because an exemption nobody can
    #: see is an exemption that outlives its reason ([ADR-0008]).
    allowed: tuple[str, ...] = ()
    #: Artefacts taken *out* of the corpus, because the unit they came from is
    #: no longer in the source. A corpus that keeps a document its owner
    #: deleted is a corpus that answers questions from something they withdrew,
    #: so removing it is correctness rather than tidiness -- and saying which
    #: ones is the same obligation as saying what was skipped.
    withdrawn: tuple[str, ...] = ()
    limits: tuple[str, ...] = LIMITS
    #: Metadata, and deliberately not part of the id.
    created_at: str = ""

    @property
    def coverage(self) -> Coverage:
        return Coverage(
            units_read=len(self.artefacts) + len(self.skipped),
            emitted=len(self.artefacts),
            skipped=len(self.skipped),
            characters=sum(a.characters for a in self.artefacts),
            traceable_characters=sum(a.traceable_characters for a in self.artefacts),
        )

    @property
    def run_id(self) -> str:
        """Over exactly the inputs that determine the output.

        A plan and a sync over the same input have the *same* id, which is what
        lets ``sync`` know a plan was made for what it is about to do
        ([ADR-0012]). The kind is metadata about which command ran, not about
        what the run would produce.
        """
        return hash_of(self.identity())

    def identity(self) -> Canonical:
        """The inputs, canonically. Public so that a reader can re-derive it."""
        return {
            "musubi": self.musubi_version,
            "sources": [
                {
                    "source_id": source.source_id,
                    "adapter": source.adapter,
                    "key_derivation": source.key_derivation,
                }
                for source in self.sources
            ],
            "rulesets": [{"id": name, "version": version} for name, version in self.rulesets],
            "converters": list(self.converters),
            "screener": self.screener,
            "emitter": self.emitter,
            "artefacts": [
                {
                    "path": artefact.path,
                    "source_id": artefact.source_id,
                    "unit_key": artefact.unit_key,
                    "content_hash": artefact.content_hash,
                }
                for artefact in self.artefacts
            ],
            "skipped": [
                {"source_id": skip.source_id, "origin": skip.origin, "reason": skip.reason}
                for skip in self.skipped
            ],
            "allowed": list(self.allowed),
        }

    def summary(self) -> str:
        """The headline, which must not read as a success when nothing happened.

        `Coverage.traceable_coverage` is 1.0 for an empty artefact, and that is
        right per document: no character failed the guarantee. Aggregated over a
        run that emitted **nothing**, it printed

            0 emitted, 1 skipped, 0 removals, **100.0% traceable**

        which is the same shape as the `answer_width` finding ([ADR-0033]) --
        the number a reader trusts, maximised by total failure. A percentage of
        nothing is not a percentage.
        """
        coverage = self.coverage
        traceable = (
            f"{coverage.traceable_coverage:.1%} traceable"
            if coverage.characters
            else "no characters to trace"
        )
        return (
            f"{coverage.emitted} emitted, {coverage.skipped} skipped, "
            f"{len(self.removals)} removals, {traceable}"
        )


def render(manifest: Manifest) -> str:
    """The manifest as the document it is ([ADR-0002]).

    A stable key order and a trailing newline, so two runs over the same input
    produce the same bytes. Indented rather than minified: this is the file a
    reviewer opens, and the id is computed over the canonical form rather than
    over this, so the formatting is free.
    """
    coverage = manifest.coverage
    body: Canonical = {
        "contract": CONTRACT,
        "run_id": manifest.run_id,
        "kind": manifest.kind,
        "created_at": manifest.created_at,
        "musubi_version": manifest.musubi_version,
        "sources": [
            {
                "source_id": source.source_id,
                "adapter": source.adapter,
                "key_derivation": source.key_derivation,
                "root": source.root,
                "units": source.units,
                "caps": list(source.caps),
            }
            for source in manifest.sources
        ],
        "rulesets": [{"id": name, "version": version} for name, version in manifest.rulesets],
        "converters": list(manifest.converters),
        "screener": manifest.screener,
        "emitter": manifest.emitter,
        "artefacts": [
            {
                "path": artefact.path,
                "content_hash": artefact.content_hash,
                "trace_map": artefact.trace_path,
                "source": {
                    "source_id": artefact.source_id,
                    "unit_key": artefact.unit_key,
                    **({"content_hash": artefact.source_hash} if artefact.source_hash else {}),
                },
                "converter": artefact.converter,
                "layer": artefact.layer,
                "characters": artefact.characters,
                "traceable_characters": artefact.traceable_characters,
            }
            for artefact in manifest.artefacts
        ],
        "removals": [
            {
                "unit_key": key,
                "rule": record.rule,
                "kind": record.kind,
                "span": [record.span.start, record.span.end],
                "removed_characters": record.removed_characters,
                "removed_sha256": record.removed_hash,
            }
            for key, record in manifest.removals
        ],
        "skipped": [
            {
                "source_id": skip.source_id,
                "origin": skip.origin,
                "reason": skip.reason,
                "detail": skip.detail,
            }
            for skip in manifest.skipped
        ],
        # No span and no length ([ADR-0019]). A finding points at a credential
        # that is still in the owner's source file and still valid, and a
        # manifest naming its offset and its length is the targeting
        # information an attacker would want. The owner does not need it -- the
        # terminal report prints it, because a person looking at their own
        # screen is who ADR-0008 stops the run for.
        "findings": [
            {
                "unit_key": key,
                "rule": finding.rule,
                "label": finding.label,
                "matched_sha256": finding.matched_hash,
            }
            for key, finding in manifest.findings
        ],
        "allowed": list(manifest.allowed),
        "withdrawn": list(manifest.withdrawn),
        "coverage": {
            "units_read": coverage.units_read,
            "emitted": coverage.emitted,
            "skipped": coverage.skipped,
            "characters": coverage.characters,
            "traceable_characters": coverage.traceable_characters,
        },
        "limits": list(manifest.limits),
    }
    return json.dumps(body, ensure_ascii=False, indent=2) + "\n"
