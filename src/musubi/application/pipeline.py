"""The six stages, in the one order that is safe.

Open, screen, convert, cleanse, compose, render -- and the manifest assembled
across all of them. `plan` runs this and writes nothing; `sync` runs the same
thing and promotes what it staged. They share this module rather than each
having a copy, because two implementations of one pipeline is exactly how a dry
run stops predicting the real one.

**Screening comes before conversion**, and the order is the point. A unit is
looked at while it is still bytes in memory, so a secret never reaches a file
musubi wrote and a run that stops has nothing on disk to clean up ([ADR-0008]).

**Nothing is promoted from inside here.** This stages and reports; whether to
promote is the caller's decision, which is what makes "a credential stops the
whole run" a property of the decision rather than of any one write.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from ..domain.cleansing import cleanse
from ..domain.hashing import content_hash
from ..domain.manifest import Artefact, Manifest, Skip, SourceRecord
from ..domain.record import Unit, unit_key
from ..domain.removal import RemovalRecord, Ruleset
from ..domain.screening import Finding
from ..domain.trace import TraceMap
from ..ports.converter import Converted, Converter
from ..ports.emitter import Document, Emitter
from ..ports.screener import Screener
from ..ports.source import Source

__all__ = ["Outcome", "Settings", "run"]


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything a run needs that is not the source."""

    ruleset: Ruleset
    screener: Screener
    converter_for: Callable[[str], Converter | None]
    musubi_version: str
    #: ``rule:unit_key`` pairs the owner has looked at and decided against.
    #: Recorded in the manifest, because an exemption nobody can see is an
    #: exemption that outlives its reason ([ADR-0008]).
    allowed: frozenset[str] = frozenset()
    created_at: str = ""


@dataclass(slots=True)
class Outcome:
    """What the pipeline produced, before anybody decided what to do with it."""

    manifest: Manifest
    #: What would stop a sync. A list rather than an exception, so that a plan
    #: reports every hit instead of sending its reader back for another run.
    refusals: list[tuple[str, Finding]] = field(default_factory=list)

    @property
    def refused(self) -> bool:
        return bool(self.refusals)


def run(source: Source, settings: Settings, emitter: Emitter, *, write: bool) -> Outcome:
    """Walk a source through the six stages.

    ``write`` is the only difference between a plan and a sync in here: the same
    decisions, the same numbers, the same manifest, and one of them puts bytes
    into a staging area.
    """
    discovery = source.discover()
    artefacts: list[Artefact] = []
    removals: list[tuple[str, RemovalRecord]] = []
    findings: list[tuple[str, Finding]] = []
    refusals: list[tuple[str, Finding]] = []
    converters: set[str] = set()

    skipped = [
        Skip(source.source_id, item.origin, item.reason, item.detail) for item in discovery.skipped
    ]

    for found in sorted(discovery.found, key=lambda f: f.key_parts):
        key = unit_key(*found.key_parts)
        content = source.read(found)

        hits = list(settings.screener.screen(_peek(content)))
        findings.extend((key, hit) for hit in hits)
        refused = [hit for hit in hits if f"{hit.rule}:{key}" not in settings.allowed]
        if refused:
            refusals.extend((key, hit) for hit in refused)
            skipped.append(Skip(source.source_id, key, "credential", refused[0].rule))
            continue

        converter = settings.converter_for(found.media_type)
        if converter is None:
            skipped.append(Skip(source.source_id, key, "no_converter", found.media_type))
            continue

        converted = converter.convert(content, found.media_type)
        if not isinstance(converted, Converted):
            skipped.append(Skip(source.source_id, key, converted.reason, converted.detail))
            continue
        converters.add(converted.converter)

        unit = Unit(
            source_id=source.source_id,
            unit_key=key,
            content_hash=content_hash(content),
            media_type=found.media_type,
        )
        document, struck = _cleanse(unit, converted, settings.ruleset)
        removals.extend((key, record) for record in struck)

        artefacts.append(emitter.stage(document) if write else emitter.render(document).artefact)

    manifest = Manifest(
        kind="sync" if write else "plan",
        musubi_version=settings.musubi_version,
        sources=(
            SourceRecord(
                source_id=source.source_id,
                adapter=source.adapter,
                key_derivation=source.key_derivation,
                units=len(discovery.found),
                caps=discovery.caps,
                root=source.origin,
            ),
        ),
        rulesets=((settings.ruleset.id, settings.ruleset.version),),
        converters=tuple(sorted(converters)),
        screener=settings.screener.name,
        emitter=emitter.name,
        artefacts=tuple(artefacts),
        removals=tuple(removals),
        skipped=tuple(sorted(skipped, key=lambda s: (s.origin, s.reason))),
        findings=tuple(findings),
        allowed=tuple(sorted(settings.allowed)),
        created_at=settings.created_at,
    )
    return Outcome(manifest=manifest, refusals=refusals)


def _cleanse(
    unit: Unit, converted: Converted, ruleset: Ruleset
) -> tuple[Document, Sequence[RemovalRecord]]:
    """Stages four and five: take the tracking out, and compose the two maps."""
    cleansed = cleanse(converted.text, ruleset)
    composed = converted.trace.followed_by(TraceMap.of_rewrite(cleansed.rewritten)).merged()
    return (
        Document(
            unit=unit,
            text=cleansed.text,
            trace=composed,
            converter=converted.converter,
            source_encoding=converted.source_encoding,
            source_bom_bytes=converted.source_bom_bytes,
        ),
        cleansed.removals,
    )


def _peek(content: bytes) -> str:
    """The bytes, as text the screener can look at.

    Deliberately lossy. Every credential format anybody issues is ASCII, so
    reading with ``replace`` finds one even in a file musubi will refuse to
    convert -- and that is the point: screening a unit that is about to be
    reported unreadable is the one place a secret in an unconvertible file still
    gets caught.
    """
    return content.decode("utf-8", errors="replace")
