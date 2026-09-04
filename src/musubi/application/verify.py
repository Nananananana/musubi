"""Check a corpus that is already on a disk.

Everything else musubi asserts about a corpus, it asserts *while writing it*.
`tests/test_invariants.py` checks the ten properties `docs/contracts.md`
enumerates, and checks them against a sync it performed a moment earlier in a
temporary directory.

**A corpus is written once and read for years.** In between it is a folder: it
gets copied, synced, restored from a backup, opened by an editor that rewrites
line endings, half-transferred, and pointed at by `kiseki-notes` long after the
run that built it ended. This answers *is this still internally consistent*
about a folder, with no run in sight.

**What it cannot answer, and this is the important half.** Every check here
compares the corpus with **its own manifest**. That proves nothing has changed
since the run wrote it; it does not prove the run wrote the right thing. A
corruption that happened *before* the hash was taken is recorded in the hash,
and this reports `all hold` -- measured, by replacing every non-ASCII character
in `render()`: the corpus said `# ????` where the vault said `# ギア設計`, and
`verify` returned 0.

That is not a defect to fix here. `verify` exists to answer a question about a
folder **with no run in sight**, and the sources may be long gone. But
**consistency is not fidelity**, and a hash agreeing with itself only proves the
damage was deterministic. The command that compares a corpus with the file it
came from is `musubi trace`, which opens the source and says `changed` when the
hashes disagree; and the property that catches it *during* a run is ADR-0004's,
because a substituted character makes a `verbatim` segment's equality false.

**No JSON Schema here.** `jsonschema` is a dev dependency and ADR-0001 keeps the
runtime at zero, so these are the invariants checked directly -- which is the
half a schema cannot express in any case. A consumer that has `jsonschema`
validates shape against the schemas in the wheel; this checks what those cannot
say.

**These checks are written twice on purpose.** `tests/test_invariants.py` keeps
its own implementation rather than asserting on this one's output. If the tests
became assertions about `verify`, a single mistake here would make both agree
and nothing would notice -- the guard and the thing it guards would be one body
of code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from ..domain.hashing import Canonical, content_hash, hash_of
from ..domain.trace import Kind
from ..errors import ContractError, TraceError
from ..ports.corpus import CorpusReader

__all__ = ["Fault", "Verified", "verify"]


@dataclass(frozen=True, slots=True)
class Fault:
    """One thing that does not hold, and where.

    ``invariant`` names the entry in `docs/contracts.md` so that a reader can go
    from a failure to the paragraph that says why it matters.
    """

    invariant: str
    subject: str
    detail: str

    def describe(self) -> str:
        return f"{self.invariant}  {self.subject}: {self.detail}"


@dataclass(frozen=True, slots=True)
class Verified:
    """What was checked, and what did not hold."""

    destination: str
    run_id: str
    artefacts: int
    checks: int
    faults: tuple[Fault, ...] = field(default_factory=tuple)

    @property
    def holds(self) -> bool:
        return not self.faults

    def summary(self) -> str:
        if self.holds:
            return f"{self.artefacts} artefacts, {self.checks} checks, all hold"
        return f"{self.artefacts} artefacts, {self.checks} checks, {len(self.faults)} failed"


def verify(corpus: CorpusReader) -> Verified:
    """Read a destination and check every invariant that can be checked.

    Collects rather than raises. A corpus with four broken maps should report
    four, not send its owner back through the same command four times -- the
    same reason `plan` collects refusals instead of stopping at the first.

    A manifest that cannot be read at all *is* a raise: there is then nothing to
    check anything against, and a report saying "0 faults" would be true and
    dishonest.
    """
    document = corpus.manifest_document()
    faults: list[Fault] = []
    checks = 0

    entries = _artefacts(document)
    units = {(a["source"]["source_id"], a["source"]["unit_key"]) for a in entries}

    checks += 1
    faults.extend(_run_id_re_derives(document))

    checks += 1
    faults.extend(_coverage_totals_agree(document, entries))

    checks += 1
    faults.extend(_records_name_units_the_run_saw(document, units))

    checks += 1
    faults.extend(_journal_agrees(corpus, document))

    for entry in entries:
        checks += 1
        faults.extend(_artefact_holds(corpus, entry))

    return Verified(
        destination=str(getattr(corpus, "destination", "")),
        run_id=str(document.get("run_id", "")),
        artefacts=len(entries),
        checks=checks,
        faults=tuple(faults),
    )


# -- journal ---------------------------------------------------------------


def _journal_agrees(corpus: CorpusReader, document: dict[str, Any]) -> list[Fault]:
    """The history's last entry names the corpus that is actually here.

    A corpus with **no** journal passes: one written before [ADR-0034] keeps no
    history and is not thereby broken. A corpus with a journal whose last entry
    names a different run is a corpus and a history that have come apart --
    somebody restored `manifest.json` from a backup, or copied documents in
    over the top, or ran a musubi old enough not to append.

    This is the check that makes the journal worth trusting. Without it the
    file is a log: something written beside the corpus that nothing ever
    compares against, and therefore something that can drift for a year without
    anybody finding out.

    The chain is checked too. Every entry but the first names its predecessor's
    run as its parent, and a break in that says the file was edited or a line
    was lost -- which matters more here than in most places, because
    ``musubi diff`` folds a range of entries and a missing line silently
    removes the changes it recorded.
    """
    entries = corpus.journal()
    if not entries:
        return []

    faults = []
    stated = str(document.get("run_id", ""))
    if entries[-1].run_id != stated:
        faults.append(
            Fault(
                "journal 1",
                "run_id",
                f"the corpus is run {stated} and its history ends at "
                f"{entries[-1].run_id}. The two have come apart.",
            )
        )

    for older, newer in pairwise(entries):
        if newer.parent != older.run_id:
            faults.append(
                Fault(
                    "journal 2",
                    f"entry {newer.short}",
                    f"names parent {newer.parent or '(none)'} and follows run "
                    f"{older.run_id}. A line was edited or lost.",
                )
            )
    return faults


def _artefacts(document: dict[str, Any]) -> list[dict[str, Any]]:
    entries = document.get("artefacts") or []
    if not isinstance(entries, list):
        raise ContractError("the manifest's `artefacts` is not a list; refusing to guess")
    return [dict(entry) for entry in entries]


# -- manifest 1 -------------------------------------------------------------


def _run_id_re_derives(document: dict[str, Any]) -> list[Fault]:
    """The id is over exactly the inputs, so a reader can compute it again.

    Rebuilt from the manifest's own fields rather than from a reconstructed
    :class:`Manifest`: an id that only re-derives through the producer's object
    has not been shown to be re-derivable by anybody else.
    """
    stated = str(document.get("run_id", ""))
    identity: Canonical = {
        "musubi": document.get("musubi_version", ""),
        "sources": [
            {
                "source_id": source.get("source_id", ""),
                "adapter": source.get("adapter", ""),
                "key_derivation": source.get("key_derivation", ""),
            }
            for source in document.get("sources") or []
        ],
        "rulesets": [
            {"id": ruleset.get("id", ""), "version": ruleset.get("version", "")}
            for ruleset in document.get("rulesets") or []
        ],
        "converters": list(document.get("converters") or []),
        "screener": document.get("screener", ""),
        "emitter": document.get("emitter", ""),
        "artefacts": [
            {
                "path": entry.get("path", ""),
                "source_id": (entry.get("source") or {}).get("source_id", ""),
                "unit_key": (entry.get("source") or {}).get("unit_key", ""),
                "content_hash": entry.get("content_hash", ""),
            }
            for entry in document.get("artefacts") or []
        ],
        "skipped": [
            {
                "source_id": skip.get("source_id", ""),
                "origin": skip.get("origin", ""),
                "reason": skip.get("reason", ""),
            }
            for skip in document.get("skipped") or []
        ],
        "allowed": list(document.get("allowed") or []),
    }
    derived = hash_of(identity)
    if derived != stated:
        return [
            Fault(
                "manifest 1",
                "run_id",
                f"the manifest says {stated} and its own inputs give {derived}",
            )
        ]
    return []


# -- manifest 2 -------------------------------------------------------------


def _coverage_totals_agree(document: dict[str, Any], entries: list[dict[str, Any]]) -> list[Fault]:
    """The published denominators are the sums of the artefacts."""
    coverage = document.get("coverage") or {}
    faults = []
    for name in ("characters", "traceable_characters"):
        stated = int(coverage.get(name, 0))
        summed = sum(int(entry.get(name, 0)) for entry in entries)
        if stated != summed:
            faults.append(
                Fault("manifest 2", f"coverage.{name}", f"says {stated}, artefacts sum to {summed}")
            )
    stated = int(coverage.get("emitted", 0))
    if stated != len(entries):
        faults.append(
            Fault("manifest 2", "coverage.emitted", f"says {stated}, there are {len(entries)}")
        )
    return faults


# -- manifest 3 -------------------------------------------------------------


def _records_name_units_the_run_saw(
    document: dict[str, Any], units: set[tuple[str, str]]
) -> list[Fault]:
    """A removal about a unit no artefact came from is an account of nothing."""
    keys = {key for _, key in units}
    faults = []
    for record in document.get("removals") or []:
        key = str(record.get("unit_key", ""))
        if key not in keys:
            faults.append(
                Fault("manifest 3", f"removal {key}", "names a unit no artefact came from")
            )
    return faults


# -- manifest 4 and the trace invariants ------------------------------------


def _artefact_holds(corpus: CorpusReader, entry: dict[str, Any]) -> list[Fault]:
    """Everything checkable about one artefact and the map that describes it."""
    path = str(entry.get("path", ""))
    faults: list[Fault] = []

    try:
        key = corpus.key_of(path, str(entry.get("trace_map", "")))
    except ContractError as error:
        return [Fault("manifest 4", path, str(error))]

    try:
        body = corpus.artefact(key)
        raw = corpus.artefact_bytes(key)
    except (OSError, TraceError) as error:
        return [Fault("manifest 4", path, f"the manifest names it and it cannot be read: {error}")]

    # The check only this command can make. The tests build and check in one
    # breath, so their file has had no chance to change; this one may have been
    # sitting on a disk for a year.
    stated = str(entry.get("content_hash", ""))
    actual = content_hash(raw)
    if stated != actual:
        faults.append(
            Fault("content", path, f"the manifest says {stated}, the file on disk is {actual}")
        )

    try:
        held = corpus.held(key)
    except (ContractError, TraceError) as error:
        # `held` builds a TraceMap, whose constructor is where tiling is
        # enforced, so trace 1 arrives here rather than as its own check.
        return [*faults, Fault("trace 1", path, str(error))]

    trace = held.trace
    if trace.artefact_length != len(body):
        faults.append(
            Fault(
                "trace 1",
                path,
                f"the map covers {trace.artefact_length} characters and the document has "
                f"{len(body)}",
            )
        )

    for segment in trace.segments:
        if segment.out.end < segment.out.start or segment.src.end < segment.src.start:
            faults.append(Fault("trace 2", path, f"{segment.kind.value} span runs backwards"))
        if segment.kind is Kind.REMOVAL and not segment.out.is_empty:
            faults.append(Fault("trace 4", path, "a removal occupies output it should not occupy"))
        if segment.kind is Kind.VERBATIM and len(segment.out) != len(segment.src):
            faults.append(
                Fault(
                    "trace 3",
                    path,
                    f"a verbatim segment is {len(segment.out)} out and {len(segment.src)} in",
                )
            )

    traceable = sum(
        len(segment.out) for segment in trace.segments if segment.kind is not Kind.SYNTHETIC
    )
    stated_traceable = int(entry.get("traceable_characters", 0))
    if traceable != stated_traceable:
        faults.append(
            Fault(
                "trace 5",
                path,
                f"the manifest says {stated_traceable} traceable and the map's segments "
                f"give {traceable}",
            )
        )

    unit = (entry.get("source") or {}).get("unit_key", "")
    if held.source.unit_key != unit:
        faults.append(
            Fault(
                "manifest 4",
                path,
                f"the manifest says it came from {unit!r} and its map says "
                f"{held.source.unit_key!r}",
            )
        )

    return faults
