"""Writing the corpus, and not writing it until the whole run has passed.

## The layout, and why it is three folders rather than one

```text
<destination>/
├── documents/   what a consumer ingests
├── traces/      the map for each one
└── manifest.json
```

The obvious arrangement is a sidecar beside each document -- `gear.md` and
`gear.md.trace.json` in the same folder. It does not survive contact with the
consumer. `tsumugi`'s corpus walk skips a fixed list of directories that does not
include `.musubi`, and its parser registry claims `.json`; sidecars beside the
documents would be **ingested as documents**, and a corpus would end up holding a
per-character index of itself.

**What separating the trees buys, precisely.** It makes a correct invocation
*available*: `tsumugi ingest <destination>/documents` reads the documents and
nothing else, which a sidecar arrangement makes impossible however carefully it
is called. It does **not** make an incorrect one safe. Measured, on a real run:

```text
tsumugi ingest corpus/documents   ->  2 new
tsumugi ingest corpus             ->  5 new
```

The five are the documents, the manifest and the trace maps, indexed by section
heading, so `tsumugi search "removal"` returns the map of a document rather than
the document. `0 skipped, 0 failed`; nothing anywhere says something went wrong.
Naming `<destination>` is a completely natural way to call it.

So musubi cannot stop a consumer from ingesting the wrong subtree, and does not
claim to. What it does instead is say which one is right, at the end of the run
that created the ambiguity, and again in `docs/contracts.md` where a consumer
reads. Adding `traces` to somebody else's skip list would buy a fix by
abandoning the argument for the layout, and writing a `.tsumugiignore` into the
destination would put a file in the owner's output folder that they did not ask
for, help exactly one consumer, and make the contents depend on which sibling
happens to exist.

`musubi trace` finds a map by construction rather than by convention, which the
separation does deliver unconditionally.

## Staging

[ADR-0008] hangs on this. Everything is written under `.musubi-staging/` and
moved into place only when the whole run has passed; a credential means
`discard()` and nothing reaches the destination -- not the offending unit and
not the ones that converted cleanly before it.

**What is atomic, precisely.** The *decision* is all-or-nothing. The writes are
one `os.replace` per file, each of which is atomic on every filesystem musubi
runs on, and there is no moment at which a half-written document is readable.
There is no claim that a reader sees the whole set appear at once: that would
need a directory swap, and a directory swap would mean rewriting every unchanged
artefact on every run, which is the incrementality [ADR-0006] exists to buy.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from ...domain.frontmatter import FrontMatter, replacements
from ...domain.hashing import content_hash
from ...domain.journal import Entry
from ...domain.manifest import Artefact
from ...domain.removal import RemovalRecord
from ...domain.screening import Finding
from ...domain.span import Span
from ...domain.text import rewrite
from ...domain.trace import TraceMap
from ...errors import ContractError, ConversionError
from ...ports.emitter import Document, Previous, Rendered, Retained

__all__ = [
    "DOCUMENTS",
    "JOURNAL",
    "MANIFEST",
    "STAGING",
    "TRACES",
    "TRACE_CONTRACT",
    "DocumentEmitter",
]

DOCUMENTS = "documents"
TRACES = "traces"
MANIFEST = "manifest.json"

#: The corpus's history: one JSON object per run, appended ([ADR-0034]).
JOURNAL = "runs.jsonl"
STAGING = ".musubi-staging"

#: Not frozen. v0.2 writes the schema and freezes the name once a second program
#: has produced and consumed one ([ADR-0002]); until then the ``-draft`` says so
#: on every file rather than in a release note.
TRACE_CONTRACT = "musubi.trace-map/1-draft"

#: Front matter is a Markdown convention. A `.txt` gets none, and its layer and
#: producer live in the manifest and the trace map, which is where a consumer
#: that cannot read front matter would look anyway.
_TAKES_FRONT_MATTER = frozenset({"text/markdown"})


class DocumentEmitter:
    """Satisfies :class:`~musubi.ports.emitter.Emitter`."""

    name = "documents@1"

    def __init__(self, destination: Path) -> None:
        self.destination = destination.expanduser().resolve()
        self.staging = self.destination / STAGING
        # Resolved once each. `_inside` is called twice per artefact and a
        # root's resolution cannot change during a run.
        self._resolved_destination = self.destination.resolve()
        self._resolved_staging = self.staging.resolve()
        self._staged: list[str] = []
        #: Retained documents whose source timestamp moved, applied at
        #: promotion and dropped on a discard.
        self._retimed: list[tuple[Path, float]] = []

    # -- staging -----------------------------------------------------------

    def begin(self) -> None:
        """Clear whatever a previous run left behind and start again.

        A staging area from a crashed run holds a half-built corpus. Reusing it
        would promote a mixture of two runs, which is exactly the thing
        [ADR-0003] promises cannot happen.
        """
        if self.staging.exists():
            shutil.rmtree(self.staging)
        self.staging.mkdir(parents=True)
        self._staged = []
        self._retimed = []

    def render(self, document: Document) -> Rendered:
        """What this document would become. Touches nothing.

        `plan` needs every number a `sync` would produce and needs them without
        writing anything ([ADR-0012]), so the arithmetic lives here and the only
        thing `stage` adds is the disk.
        """
        text, trace = self._with_front_matter(document)
        relative = document.unit.unit_key
        return Rendered(
            text=text,
            trace=trace,
            artefact=Artefact(
                path=f"{DOCUMENTS}/{relative}",
                content_hash=content_hash(text),
                trace_path=f"{TRACES}/{relative}.json",
                source_id=document.unit.source_id,
                unit_key=relative,
                converter=document.converter,
                traceable_characters=trace.traceable_characters,
                characters=trace.artefact_length,
                layer=document.layer,
                source_hash=document.unit.content_hash,
            ),
        )

    def stage(self, document: Document) -> Artefact:
        """Write one document and its map into the staging area."""
        rendered = self.render(document)
        relative = document.unit.unit_key
        self._write(Path(DOCUMENTS) / relative, rendered.text)
        # The document keeps the source's timestamp; musubi's own records --
        # the map and the manifest -- keep the run's (ADR-0022). `promote` is a
        # rename, so what is set here is what lands.
        self._keep_time(Path(DOCUMENTS) / relative, document.modified_at)
        self._write(
            Path(TRACES) / f"{relative}.json",
            _render_trace(document, rendered.text, rendered.trace, relative),
        )
        return rendered.artefact

    def stage_manifest(self, body: str) -> None:
        """The run's own account, written last and promoted with the rest."""
        self._write(Path(MANIFEST), body)

    def _with_front_matter(self, document: Document) -> tuple[str, TraceMap]:
        if document.unit.media_type not in _TAKES_FRONT_MATTER:
            return document.text, document.trace

        inserted = rewrite(document.text, replacements(document.text, FrontMatter(document.layer)))
        try:
            composed = document.trace.followed_by(TraceMap.of_rewrite(inserted))
        except ValueError as error:  # pragma: no cover - a bug, not an input
            raise ConversionError(
                f"the map for {document.unit.unit_key} did not survive the front matter: {error}"
            ) from error
        return inserted.text, composed.merged()

    def _write(self, relative: Path, body: str) -> None:
        target = self.staging / relative
        if not _inside(target, self._resolved_staging):
            raise ConversionError(f"{relative} would be written outside the staging area")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Written as UTF-8 with LF, on every platform. A corpus whose bytes
        # depend on which machine built it is a corpus whose hashes do
        # ([ADR-0003]).
        target.write_text(body, encoding="utf-8", newline="\n")
        self._staged.append(relative.as_posix())

    def _keep_time(self, relative: Path, modified_at: float | None) -> None:
        """Put the source's timestamp back on the document musubi wrote.

        A converted note whose mtime is the conversion date has lost the one
        fact the filesystem was carrying about it, and every note in the corpus
        then shares a single date. `kiseki-notes` reads that mtime as the day a
        note was written, so the loss is silent on both sides: musubi succeeds,
        the manifest is correct, `musubi verify` passes, and a decade of history
        has become one afternoon.

        Not an error when it fails. The corpus is written and correct; a
        timestamp that would not set is a worse corpus, not a failed run, and a
        read-only or exotic filesystem is not a reason to throw away a sync.
        """
        if modified_at is None:
            return
        target = self.staging / relative
        with contextlib.suppress(OSError):  # a filesystem, not a state
            os.utime(target, (modified_at, modified_at))

    # -- promoting ---------------------------------------------------------

    def promote(self) -> tuple[str, ...]:
        """Move everything staged into place, one atomic replace at a time.

        **The manifest goes last.** Sorted, ``documents/`` < ``manifest.json``
        < ``traces/``, so a crash between the second and the third left a
        manifest describing maps that were not there yet -- a corpus whose
        account of itself was ahead of it. Promoted last, a crash at any point
        leaves the old manifest describing the old corpus, and the next run's
        `retain()` finds the half-promoted documents not matching it and
        converts them again.
        """
        moved: list[str] = []
        ordered = sorted(self._staged, key=lambda relative: (relative == MANIFEST, relative))
        for relative in ordered:
            source = self.staging / relative
            target = self.destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            source.replace(target)
            moved.append(relative)
        for document, modified_at in self._retimed:
            with contextlib.suppress(OSError):  # a filesystem, not a state
                os.utime(document, (modified_at, modified_at))
        self.discard()
        return tuple(moved)

    def discard(self) -> None:
        """Throw the staging area away. Nothing reaches the destination."""
        if self.staging.exists():
            shutil.rmtree(self.staging)
        self._staged = []
        self._retimed = []

    @property
    def staged(self) -> tuple[str, ...]:
        """What is waiting, in a fixed order."""
        return tuple(sorted(self._staged))

    # -- withdrawing -------------------------------------------------------

    def previously_written(self) -> frozenset[str]:
        """What the last run recorded writing here, read from its manifest.

        The previous manifest is the ledger. There is no separate store,
        because a corpus that already says what is in it does not need one, and
        a ledger that can disagree with the corpus is a second source of truth
        to keep in step.

        A manifest naming a contract this does not recognise stops the run
        rather than being parsed hopefully: guessing at it would produce a list
        of files to delete.
        """
        return self.previous().written

    def previous(self) -> Previous:
        """The corpus as the last run left it: its id, its hashes, its paths --
        and everything a run that converts nothing would still have to say.

        One read of one file. Withdrawal wants the paths, the journal wants
        the run id and the hashes ([ADR-0034]), and the incremental path wants
        each artefact's record and source hash ([ADR-0036]). Three readers of
        the same document are three things to keep in step.

        The records are rebuilt from the manifest's own fields, which is the
        reverse of `render()`. A field this cannot read makes the artefact
        unretainable rather than the run fail: an older manifest is a reason
        to convert, not a reason to stop.
        """
        body = self._previous_manifest()
        if body is None:
            return Previous(run_id=None, artefacts={}, written=frozenset())

        hashes: dict[str, str] = {}
        written: set[str] = set()
        retained: dict[str, Retained] = {}
        removals = _grouped(body.get("removals"), _removal_from)
        findings = _grouped(body.get("findings"), _finding_from)
        for entry in body.get("artefacts") or []:
            path = entry.get("path")
            if isinstance(path, str) and path:
                written.add(path)
                digest = entry.get("content_hash")
                if isinstance(digest, str) and digest:
                    hashes[path] = digest
            trace = entry.get("trace_map")
            if isinstance(trace, str) and trace:
                written.add(trace)
            artefact = _artefact_from(entry)
            if artefact is not None and artefact.source_hash:
                retained[artefact.unit_key] = Retained(
                    artefact=artefact,
                    removals=removals.get(artefact.unit_key, ()),
                    findings=findings.get(artefact.unit_key, ()),
                )

        run_id = body.get("run_id")
        return Previous(
            run_id=run_id if isinstance(run_id, str) and run_id else None,
            artefacts=hashes,
            written=frozenset(written),
            decided_by={
                "musubi": body.get("musubi_version"),
                "rulesets": [
                    (ruleset.get("id"), ruleset.get("version"))
                    for ruleset in body.get("rulesets") or []
                ],
                "screener": body.get("screener"),
                "emitter": body.get("emitter"),
                "allowed": sorted(body.get("allowed") or []),
            },
            retained=retained,
        )

    def retain(self, artefact: Artefact, modified_at: float | None = None) -> bool:
        """Is this artefact still on the disk exactly as the manifest says?

        Both files, and the document by its hash. Hashing it means reading it,
        which is a cost the incremental path pays on purpose: the alternative
        is trusting that nothing touched the corpus since the manifest was
        written, and `musubi verify` exists because that is not a thing to
        trust ([ADR-0036]).

        The source's timestamp is noted and **applied at promotion**, not here.
        A note whose bytes did not change and whose mtime did still owes the
        corpus the new date ([ADR-0022]) -- but a run that later refuses must
        have touched nothing in the destination, and a timestamp is a touch.
        """
        document = self.destination / artefact.path
        sidecar = self.destination / artefact.trace_path
        if not _inside(document, self._resolved_destination) or not sidecar.is_file():
            return False
        try:
            holds = content_hash(document.read_bytes()) == artefact.content_hash
        except OSError:
            return False
        if holds and modified_at is not None:
            self._retimed.append((document, modified_at))
        return holds

    def append_journal(self, entry: Entry) -> None:
        """Add one line to the corpus's history.

        **Appended, and outside the staging area.** Everything else musubi
        writes is staged and promoted together because [ADR-0008] is
        fail-closed; the journal is the opposite kind of thing -- a record that
        a run happened, written once the run *has* happened. Staging it would
        mean discarding it on a refusal, which is right, and promoting it with
        the rest would mean replacing the file rather than adding to it.

        One `json.dumps` and a newline, opened in append mode, which is the
        write a reader can `tail` and a crash can only truncate at a line
        boundary.
        """
        self.destination.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry.document(), ensure_ascii=False, sort_keys=True)
        with (self.destination / JOURNAL).open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")

    def _previous_manifest(self) -> dict[str, Any] | None:
        manifest = self.destination / MANIFEST
        if not manifest.is_file():
            return None
        try:
            body = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ContractError(f"{manifest} is not readable as a manifest: {error}") from error
        if not isinstance(body, dict) or not str(body.get("contract", "")).startswith(
            "musubi.sync-manifest/1"
        ):
            raise ContractError(
                f"{manifest} declares contract {body.get('contract')!r}, which this does "
                f"not recognise. Refusing rather than guessing at a list of files to delete."
            )
        return body

    def withdraw(self, paths: Iterable[str]) -> tuple[str, ...]:
        """Take these out of the corpus. Returns what was actually removed.

        Only a path a previous manifest recorded writing, checked again here
        against the destination: musubi deletes what it wrote and never what it
        merely found, so a folder somebody put something else in survives a
        sync intact.
        """
        removed: list[str] = []
        for relative in sorted(paths):
            target = self.destination / relative
            if not _inside(target, self._resolved_destination) or not target.is_file():
                continue
            target.unlink()
            removed.append(relative)
            _prune(target.parent, self.destination)
        return tuple(removed)


def _render_trace(document: Document, text: str, trace: TraceMap, relative: str) -> str:
    """The sidecar, as `musubi trace` will read it back.

    Written with a stable key order and a trailing newline, so that two runs
    over the same input produce the same bytes.

    **Minified, and it used to be indented.** The reason given was that this is
    the file a reviewer opens, which was fair when nobody had measured the file.
    Measured (#76, `tools/scaling.py --only map`), the indentation is about as
    many bytes as the data -- 36,241 down to 16,093 for one HTML map, with
    `traces/` at 10.7x the documents it describes.

    And it is not only storage: encoding these was **27% of a 300-document
    sync** in the profile, most of it whitespace. A reviewer who wants to read
    one pipes it through `jq`; nobody gets the disk back.
    """
    body = {
        "contract": TRACE_CONTRACT,
        "artefact": {"path": f"{DOCUMENTS}/{relative}", "content_hash": content_hash(text)},
        "source": {
            "source_id": document.unit.source_id,
            "unit_key": document.unit.unit_key,
            "content_hash": document.unit.content_hash,
            "media_type": document.unit.media_type,
            # With these and the file, a character offset becomes a byte offset
            # ([ADR-0018]).
            "encoding": document.source_encoding,
            "bom_bytes": document.source_bom_bytes,
        },
        "converter": document.converter,
        "source_unit": trace.source_unit,
        "coverage": {
            "characters": trace.artefact_length,
            "traceable": trace.traceable_characters,
        },
        "segments": [
            {
                "out": [segment.out.start, segment.out.end],
                "src": [segment.src.start, segment.src.end],
                "kind": segment.kind.value,
                **({"rule": segment.rule} if segment.rule else {}),
            }
            for segment in trace.segments
        ],
    }
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "\n"


def _inside(target: Path, root: Path) -> bool:
    """Does this path stay under that root?

    `root` arrives **already resolved**. This is called twice per artefact, and
    resolving the root each time was 7% of a 300-document sync: a syscall per
    check, for an answer that cannot change during a run.
    """
    try:
        target.resolve().relative_to(root)
    except (OSError, ValueError):
        return False
    return True


def _prune(directory: Path, stop: Path) -> None:
    """Remove directories a withdrawal emptied, and stop at the destination.

    ``rmdir`` refuses a directory that is not empty, which is what makes this
    safe: it cannot take anything with it.
    """
    while directory != stop and _inside(directory, stop):
        try:
            directory.rmdir()
        except OSError:
            return
        directory = directory.parent


# -- reading a manifest back ------------------------------------------------
#
# The reverse of `domain.manifest.render`, kept beside the writer of the same
# layout rather than in the domain: the domain renders manifests and does not
# read them, and a reader that reconstructs the producer's object can only see
# what the object can represent. `verify` reads the raw document for exactly
# that reason. This reads it into records because a run carrying an artefact
# forward has to hand the pipeline the same type a conversion would have.


def _artefact_from(entry: Mapping[str, Any]) -> Artefact | None:
    """One artefact record, or ``None`` for one this cannot read whole."""
    source = entry.get("source")
    if not isinstance(source, Mapping):
        return None
    try:
        return Artefact(
            path=_string(entry, "path"),
            content_hash=_string(entry, "content_hash"),
            trace_path=_string(entry, "trace_map"),
            source_id=_string(source, "source_id"),
            unit_key=_string(source, "unit_key"),
            converter=_string(entry, "converter"),
            traceable_characters=int(entry["traceable_characters"]),
            characters=int(entry["characters"]),
            layer=_string(entry, "layer"),
            source_hash=str(source.get("content_hash") or ""),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _removal_from(entry: Mapping[str, Any]) -> RemovalRecord:
    span = entry["span"]
    return RemovalRecord(
        rule=_string(entry, "rule"),
        kind=_string(entry, "kind"),
        span=Span(int(span[0]), int(span[1])),
        removed_characters=int(entry["removed_characters"]),
        removed_hash=_string(entry, "removed_sha256"),
    )


def _finding_from(entry: Mapping[str, Any]) -> Finding:
    # The manifest carries no span and no length, on purpose ([ADR-0019]). A
    # finding read back has an empty span, and the only thing a run does with
    # one it carried forward is write it back out the same way.
    return Finding(
        rule=_string(entry, "rule"),
        label=_string(entry, "label"),
        span=Span(0, 0),
        matched_characters=0,
        matched_hash=_string(entry, "matched_sha256"),
    )


def _grouped[T](
    entries: object, read: Callable[[Mapping[str, Any]], T]
) -> dict[str, tuple[T, ...]]:
    """Records by the unit key they name, in the order the manifest has them."""
    grouped: dict[str, list[T]] = {}
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            try:
                grouped.setdefault(_string(entry, "unit_key"), []).append(read(entry))
            except (KeyError, TypeError, ValueError):
                continue
    return {key: tuple(records) for key, records in grouped.items()}


def _string(entry: Mapping[str, Any], key: str) -> str:
    value = entry[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} is not a string")
    return value
