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
from ..errors import SourceError
from ..ports.converter import Converted, Converter
from ..ports.emitter import Document, Emitter, Previous, Retained
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
    #: Unit keys carried forward from the previous run without being read past
    #: their hash ([ADR-0036]). On the outcome and not in the manifest: the
    #: manifest is an account of the corpus, and whether a document was
    #: converted this morning or last month is an account of the run's effort.
    kept: tuple[str, ...] = ()

    @property
    def refused(self) -> bool:
        return bool(self.refusals)


def run(
    source: Source,
    settings: Settings,
    emitter: Emitter,
    *,
    write: bool,
    previous: Previous | None = None,
) -> Outcome:
    """Walk a source through the six stages.

    ``write`` is the only difference between a plan and a sync in here: the same
    decisions, the same numbers, the same manifest, and one of them puts bytes
    into a staging area.

    **A unit whose bytes did not change is not converted again** ([ADR-0036]),
    on three conditions checked in the order they are cheap: the previous run
    was decided by the same things this one is (`decided_by`), the bytes hash
    to what that run recorded for the unit, and the artefact and its map are
    still on the disk exactly as recorded. A plan and a sync make the same
    decision from the same evidence, so the dry run predicts the real one.
    """
    discovery = source.discover()
    artefacts: list[Artefact] = []
    removals: list[tuple[str, RemovalRecord]] = []
    findings: list[tuple[str, Finding]] = []
    refusals: list[tuple[str, Finding]] = []
    kept: list[str] = []
    converters: set[str] = set()

    skipped = [
        Skip(source.source_id, item.origin, item.reason, item.detail) for item in discovery.skipped
    ]

    # `sync` has already read it for withdrawal and the journal; a plan has
    # not. One parse of the manifest either way.
    if previous is None:
        previous = emitter.previous()
    retainable = previous.retained if previous.decided_by == _decided_by(settings, emitter) else {}

    # A key is the artefact's path, so two units sharing one is one document
    # overwriting another with the manifest listing both -- a corpus quietly
    # smaller than its own account of itself, and every coverage number in it
    # counting a file that is not there. Refused rather than resolved: which of
    # two pages owns a page id is not something musubi can decide, and the
    # source's `key_derivation` is the thing that turned out not to be true.
    claimed: dict[str, str] = {}

    for found in sorted(discovery.found, key=lambda f: f.key_parts):
        key = unit_key(*found.key_parts)
        if key in claimed:
            raise SourceError(
                f"{source.source_id} derives the key {key!r} for two different units "
                f"({claimed[key]} and {found.origin}). Its key_derivation is "
                f"{source.key_derivation!r}, and one of the two would have overwritten "
                f"the other while the manifest listed both."
            )
        claimed[key] = found.origin
        content = source.read(found)
        digest = content_hash(content)

        retained = retainable.get(key)
        if (
            retained is not None
            and _still_holds(retained, digest, found.media_type, settings)
            # Last, because it reads the artefact back off the disk.
            and emitter.retain(retained.artefact, found.modified_at)
        ):
            artefacts.append(retained.artefact)
            removals.extend((key, record) for record in retained.removals)
            findings.extend((key, hit) for hit in retained.findings)
            converters.add(retained.artefact.converter)
            kept.append(key)
            continue

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
            content_hash=digest,
            media_type=found.media_type,
        )
        document, struck = _cleanse(unit, converted, settings.ruleset, found.modified_at)
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
    return Outcome(manifest=manifest, refusals=refusals, kept=tuple(kept))


def _decided_by(settings: Settings, emitter: Emitter) -> dict[str, object]:
    """Everything other than the bytes that decided what a run wrote.

    The same shape `Previous.decided_by` is read back in, so the comparison is
    one equality. Any difference is a cold run: a new ruleset fires on the old
    corpus, a new signature list looks at bytes it has never seen, and a musubi
    upgrade converts everything again on purpose -- a converter that changed
    without changing its name is the one case nothing else here would catch.
    """
    return {
        "musubi": settings.musubi_version,
        "rulesets": [(settings.ruleset.id, settings.ruleset.version)],
        "screener": settings.screener.name,
        "emitter": emitter.name,
        "allowed": sorted(settings.allowed),
    }


def _still_holds(retained: Retained, digest: str, media_type: str, settings: Settings) -> bool:
    """The bytes are the bytes, and the converter is the converter.

    The per-unit half of the decision. The converter is compared by name for
    this unit's media type rather than by the set the previous run used: a
    setting that switched `text/html` to a different extractor changes what
    this unit would become and may leave the set of names looking the same.
    """
    if digest != retained.artefact.source_hash:
        return False
    converter = settings.converter_for(media_type)
    return converter is not None and converter.name == retained.artefact.converter


def _cleanse(
    unit: Unit, converted: Converted, ruleset: Ruleset, modified_at: float | None = None
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
            modified_at=modified_at,
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
