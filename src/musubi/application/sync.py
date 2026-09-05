"""The run that writes, and the one decision it makes that a plan does not.

`sync` is `plan` plus two things: it stages, and then it decides whether to
promote. The pipeline is the same module, run with ``write=True``, because two
implementations of one walk is exactly how a dry run stops predicting the real
one.

**Everything a run stops for, it stops for before anything is promoted**
([ADR-0008]). A credential means `discard()` — not the offending unit skipped,
not the clean ones kept, nothing. The decision is all-or-nothing; the writes
that follow it are one atomic replace per file.

**And a corpus is not only what was added.** A note the owner deleted has to
leave, or the corpus goes on answering questions from a document they withdrew.
The previous manifest is the ledger for that: musubi deletes what it recorded
writing, and never what it merely found.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..domain.journal import Entry, changes
from ..domain.manifest import Manifest, render
from ..errors import CredentialFoundError, EmptySourceError
from ..ports.emitter import Emitter
from ..ports.source import Source
from .pipeline import Settings, run

__all__ = ["Synced", "empties_the_corpus", "sync", "withdrawals"]


@dataclass(frozen=True, slots=True)
class Synced:
    """What the run put in the corpus, and what it took out."""

    manifest: Manifest
    promoted: tuple[str, ...]
    withdrawn: tuple[str, ...]
    #: Carried forward unconverted ([ADR-0036]). See `Outcome.kept`.
    kept: tuple[str, ...] = ()


def withdrawals(held: frozenset[str] | set[str], manifest: Manifest) -> tuple[str, ...]:
    """What a sync producing ``manifest`` would take back out of a corpus.

    Shared with ``plan`` rather than computed inside ``sync``. A dry run that
    reports what will be written and stays silent about what will be deleted is
    not a dry run of the same command, and deletion is the half an operator
    would want the warning about.
    """
    written = {artefact.path for artefact in manifest.artefacts}
    written |= {artefact.trace_path for artefact in manifest.artefacts}
    return tuple(sorted(held - written))


def empties_the_corpus(held: frozenset[str] | set[str], manifest: Manifest) -> bool:
    """Whether this run read nothing and would delete a corpus that exists.

    The ambiguous case, and only that one: see
    :class:`~musubi.errors.EmptySourceError`.
    """
    return not manifest.artefacts and bool(held)


def sync(
    source: Source, settings: Settings, emitter: Emitter, *, withdraw_all: bool = False
) -> Synced:
    """Read a source and build the corpus, or refuse and build nothing.

    Raises :class:`~musubi.errors.CredentialFoundError` when the screener found
    something nobody allowed. The message names the unit and the kind and never
    the value: the run stops so that the secret does not travel, and an
    exception quoting it would send it to a log file instead of to a corpus.

    Raises :class:`~musubi.errors.EmptySourceError` when the source produced
    nothing and a corpus already exists, because withdrawal would then take all
    of it. ``withdraw_all`` is the operator saying they have looked.
    """
    before = emitter.previous()
    held = before.written

    emitter.begin()
    outcome = run(source, settings, emitter, write=True, previous=before)

    if outcome.refused:
        emitter.discard()
        key, finding = outcome.refusals[0]
        others = len(outcome.refusals) - 1
        also = f", and {others} more were found" if others else ""
        raise CredentialFoundError(
            f"{finding.describe(key)}{also}. Nothing was written. Look, then pass "
            f"--allow {finding.rule}:{key} if it is not what it looks like."
        )

    withdrawn = withdrawals(held, outcome.manifest)

    if empties_the_corpus(held, outcome.manifest) and not withdraw_all:
        emitter.discard()
        raise EmptySourceError(
            f"The source {source.source_id!r} produced no units, and {len(withdrawn)} files "
            f"in the corpus would be taken back out -- all of it. An empty source and "
            f"an unreadable one look the same from here. Nothing was written and "
            f"nothing was deleted. Look at the source, then pass --withdraw-all if it "
            f"really is empty."
        )

    # Assembled before the manifest is staged, so that the document says what
    # the run did rather than what it did minus the last step.
    manifest = replace(outcome.manifest, withdrawn=withdrawn)
    emitter.stage_manifest(render(manifest))
    promoted = emitter.promote()

    # After the promotion, never before it. Deleting first and failing to
    # promote would leave the corpus missing documents that nothing replaced.
    removed = emitter.withdraw(withdrawn)

    # Last, and only once the corpus is what the entry says it is. An entry
    # written before the promotion would describe a run that could still refuse
    # ([ADR-0034]).
    emitter.append_journal(
        Entry(
            run_id=manifest.run_id,
            parent=before.run_id,
            created_at=manifest.created_at,
            musubi_version=manifest.musubi_version,
            kind=manifest.kind,
            change=changes(before.artefacts, {a.path: a.content_hash for a in manifest.artefacts}),
        )
    )

    return Synced(manifest=manifest, promoted=promoted, withdrawn=removed, kept=outcome.kept)
