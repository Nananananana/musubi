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
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from typing import Any, cast

from .hashing import Canonical, hash_of
from .removal import RemovalRecord
from .screening import Finding
from .trace import CHARACTERS

__all__ = [
    "CONTRACT",
    "LIMITS",
    "Artefact",
    "Coverage",
    "Manifest",
    "Skip",
    "SourceRecord",
    "published_artefact_fields",
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
    #: What this artefact's map counts its source in -- `characters`, or
    #: `opaque` for a converter whose source has no decoded text ([ADR-0025]).
    #: In the manifest as well as in the map, because a reader deciding whether
    #: two coverage numbers may be added had to open every sidecar to find out.
    #: What the document calls itself, or ``None`` where it says nothing.
    #: Never ``""``: a document that states an empty title has said something
    #: and one that says nothing has not, and a caller that cannot tell them
    #: apart falls back for the wrong one ([ADR-0040]).
    title: str | None = None
    source_unit: str = CHARACTERS
    #: `answer_width`'s numerator: how much source the map hands back, summed
    #: over every traceable character, in `source_unit`. Published so that a
    #: run's aggregate is a sum of numerators over a sum of denominators rather
    #: than a mean of means ([ADR-0038]).
    answered_source_units: int = 0
    #: The hash of the **source** bytes this was converted from -- the trace
    #: map already carries it; the manifest carries it so that a re-sync can
    #: ask *did the bytes change* without opening ten thousand sidecars
    #: ([ADR-0036]). Empty on a manifest written before it existed, and not part
    #: of ``run_id``: the id is over the outputs, and an input hash added to it
    #: would change the id of every existing corpus on upgrade.
    source_hash: str = ""
    #: The facts the source stated about this unit, as written into the front
    #: matter ([ADR-0037]). Recorded so that a re-sync whose record changed
    #: while the page did not still converts the unit ([ADR-0036]). Not part of
    #: ``run_id``: the facts are in the artefact's text and therefore already
    #: in its ``content_hash``.
    facts: tuple[tuple[str, str], ...] = ()
    #: How the source bytes were read. The trace map has carried this since
    #: [ADR-0018]; the manifest carries it so that a question about a whole run
    #: -- *how much of this corpus rests on a guess* -- does not mean opening
    #: every sidecar. #82 assumed it was already here. It was not.
    encoding: str = "utf-8"
    #: And whether that was **detected** rather than declared. `shift_jis` is a
    #: fact when the settings named it and a guess when a detector did, and the
    #: name alone does not say which ([ADR-0044]).
    encoding_detected: bool = False

    @property
    def traceable_coverage(self) -> float:
        """1.0 for an empty artefact: no character fails the guarantee."""
        if not self.characters:
            return 1.0
        return self.traceable_characters / self.characters

    @property
    def answer_width(self) -> float | None:
        """Ask about one character of this artefact: how much source comes back?

        1.0 answers a character with a character. A large number answers a
        character with a paragraph, which is what a map that resolves
        everywhere and locates nothing looks like ([ADR-0033]).

        ``None`` where there is no numerator -- an artefact with nothing
        traceable, or one read out of a manifest written before the field
        existed. Not 0.0, which would claim that a character resolves to no
        source at all: a number no real map can produce, and the shape
        `traceable_coverage` was filed for producing (#81).
        """
        if not self.answered_source_units:
            return None
        return self.answered_source_units / self.traceable_characters


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
    #: Summed across the run, in whichever unit the artefacts share.
    answered_source_units: int = 0
    #: Every `source_unit` the run's artefacts measure their sources in.
    #: One entry is a corpus whose widths may be added; more than one is a
    #: corpus whose widths may not ([ADR-0038]).
    source_units: tuple[str, ...] = ()

    @property
    def traceable_coverage(self) -> float:
        if not self.characters:
            return 1.0
        return self.traceable_characters / self.characters

    @property
    def answer_width(self) -> float | None:
        """The run's answer width, or ``None`` where there is no such number.

        **A sum of numerators over a sum of denominators**, weighted by
        traceable characters exactly as coverage is -- not a mean of the
        per-document widths, which would let one tiny document dominate a
        corpus.

        ``None`` when the run's artefacts do not share a `source_unit`. A PDF's
        map answers in pages and a Markdown map answers in characters, and
        their sum is pages added to characters: a number with no dimension,
        printed to four decimal places. `traceable_coverage` survives the same
        corpus because its numerator and denominator are both *output*
        characters; this one does not, and says so rather than being averaged
        into nonsense.
        """
        if len(self.source_units) > 1 or not self.answered_source_units:
            return None
        return self.answered_source_units / self.traceable_characters


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
            answered_source_units=sum(a.answered_source_units for a in self.artefacts),
            # Only the artefacts that have something to measure: an empty
            # document's unit says nothing about whether two widths may be
            # added, and counting it would make a corpus look mixed because it
            # holds one empty file.
            source_units=tuple(
                sorted({a.source_unit for a in self.artefacts if a.traceable_characters})
            ),
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
        # Beside the percentage and never instead of it. The percentage is the
        # one that reads as a success and can be maximised by a map that
        # resolves everywhere and locates nothing ([ADR-0033]); this is the one
        # that goes the wrong way when that happens, so a reader who sees only
        # the headline still sees it.
        width = coverage.answer_width
        beside = f", {width:.2f} answer width" if width is not None else ""
        return (
            f"{coverage.emitted} emitted, {coverage.skipped} skipped, "
            f"{len(self.removals)} removals, {traceable}{beside}"
        )


def render(manifest: Manifest) -> str:
    """The manifest as the document it is, as one string ([ADR-0002]).

    A stable key order and a trailing newline, so two runs over the same input
    produce the same bytes. Indented rather than minified: this is the file a
    reviewer opens, and the id is computed over the canonical form rather than
    over this, so the formatting is free.

    **`chunks()` is what a sync uses.** Building the whole document as one
    string was the largest thing a run held: 1.51x the size of the input, to
    produce a 269 kB file ([ADR-0045]). This stays for the callers that
    genuinely want a string -- `musubi plan` prints one -- and for tests.
    """
    return "".join(chunks(manifest))


def chunks(manifest: Manifest) -> Iterator[str]:
    """The same document, a piece at a time.

    `json.dumps` builds every piece and then joins them, so the join and the
    pieces are both resident at the moment it returns. `iterencode` yields the
    pieces, and a caller writing each one to a file never holds the whole.

    The document itself -- the nested dict `document()` builds -- is still
    built whole, and that is the 0.53x this does not fix. Streaming that too
    would mean writing JSON by hand around a generator of artefacts, and the
    manifest is the one document here whose exact bytes are a contract.
    """
    yield from json.JSONEncoder(ensure_ascii=False, indent=2).iterencode(document(manifest))
    yield "\n"


def document(manifest: Manifest) -> Canonical:
    """The manifest as data, before anything has decided how to write it."""
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
                "title": artefact.title,
                "characters": artefact.characters,
                "traceable_characters": artefact.traceable_characters,
                "source_unit": artefact.source_unit,
                "answered_source_units": artefact.answered_source_units,
                "encoding": artefact.encoding,
                "encoding_detected": artefact.encoding_detected,
                **({"facts": dict(artefact.facts)} if artefact.facts else {}),
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
            "answered_source_units": coverage.answered_source_units,
            "source_units": list(coverage.source_units),
        },
        "limits": list(manifest.limits),
    }
    return body


@cache
def published_artefact_fields() -> frozenset[str]:
    """Every key `render` writes for an artefact, taken from the renderer.

    Not a list beside it. The point is that a field added to `render` becomes
    a field a **reused** record must already have, without anybody remembering
    to say so ([ADR-0048]).

    `facts` is absent because it is written only when there are any, which is
    what makes it optional in the contract too.
    """
    sample = Artefact(
        path="",
        content_hash="",
        trace_path="",
        source_id="",
        unit_key="",
        converter="",
        traceable_characters=0,
        characters=0,
        layer="fact",
    )
    body = cast(
        "dict[str, Any]", document(Manifest(kind="sync", musubi_version="0", artefacts=(sample,)))
    )
    (only,) = body["artefacts"]
    assert isinstance(only, dict), "an artefact record is no longer an object"
    return frozenset(only)
