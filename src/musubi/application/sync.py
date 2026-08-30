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

from ..domain.manifest import Manifest, render
from ..errors import CredentialFoundError
from ..ports.emitter import Emitter
from ..ports.source import Source
from .pipeline import Settings, run

__all__ = ["Synced", "sync"]


@dataclass(frozen=True, slots=True)
class Synced:
    """What the run put in the corpus, and what it took out."""

    manifest: Manifest
    promoted: tuple[str, ...]
    withdrawn: tuple[str, ...]


def sync(source: Source, settings: Settings, emitter: Emitter) -> Synced:
    """Read a source and build the corpus, or refuse and build nothing.

    Raises :class:`~musubi.errors.CredentialFoundError` when the screener found
    something nobody allowed. The message names the unit and the kind and never
    the value: the run stops so that the secret does not travel, and an
    exception quoting it would send it to a log file instead of to a corpus.
    """
    held = emitter.previously_written()

    emitter.begin()
    outcome = run(source, settings, emitter, write=True)

    if outcome.refused:
        emitter.discard()
        key, finding = outcome.refusals[0]
        others = len(outcome.refusals) - 1
        also = f", and {others} more were found" if others else ""
        raise CredentialFoundError(
            f"{finding.describe(key)}{also}. Nothing was written. Look, then pass "
            f"--allow {finding.rule}:{key} if it is not what it looks like."
        )

    written = {artefact.path for artefact in outcome.manifest.artefacts}
    written |= {artefact.trace_path for artefact in outcome.manifest.artefacts}
    withdrawn = tuple(sorted(held - written))

    # Assembled before the manifest is staged, so that the document says what
    # the run did rather than what it did minus the last step.
    manifest = replace(outcome.manifest, withdrawn=withdrawn)
    emitter.stage_manifest(render(manifest))
    promoted = emitter.promote()

    # After the promotion, never before it. Deleting first and failing to
    # promote would leave the corpus missing documents that nothing replaced.
    removed = emitter.withdraw(withdrawn)

    return Synced(manifest=manifest, promoted=promoted, withdrawn=removed)
