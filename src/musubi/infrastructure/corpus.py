"""Reading a destination back: the layout, and the documents in it.

The emitter writes a corpus; this reads one. Keeping them apart is not
ceremony -- `musubi trace` runs against a folder somebody else built, possibly
with a musubi that is not this one, and it should have no way to modify it.

**A key does not concatenate back into a filename.** [ADR-0014] normalizes a key
to NFC and macOS hands back decomposed names, so ``root / unit_key`` misses on
the machine the notes were written on. That cost is stated in the ADR and paid
here: the direct path first, then a scan of the directory for a name that
normalizes to the same thing.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

from ..domain.span import Span
from ..domain.trace import CHARACTERS, OPAQUE, Kind, Segment, TraceMap
from ..errors import ContractError, TraceError
from ..ports.corpus import Held, SourceReference
from .emitters.documents import DOCUMENTS, MANIFEST, TRACES

__all__ = ["Corpus"]


#: Units this reader knows how to hand on. `characters` it can do arithmetic
#: in; `opaque` it can carry but not compute with, which is the whole of the
#: difference a caller needs (ADR-0025).
KNOWN_UNITS = frozenset({CHARACTERS, OPAQUE})


class Corpus:
    """A destination musubi wrote, opened for reading."""

    def __init__(self, destination: Path) -> None:
        self.destination = destination.expanduser().resolve()

    @classmethod
    def holding(cls, artefact: Path) -> tuple[Corpus, str]:
        """Find the corpus an artefact belongs to, and its key.

        Walks up looking for the layout rather than asking the caller for it: a
        reader following a citation has a path to a document and no reason to
        know how musubi arranges a destination.
        """
        resolved = artefact.expanduser().resolve()
        for parent in resolved.parents:
            documents = parent / DOCUMENTS
            if parent.name == DOCUMENTS or not documents.is_dir():
                continue
            try:
                key = resolved.relative_to(documents).as_posix()
            except ValueError:
                continue
            return cls(parent), key
        raise TraceError(
            f"{artefact} is not inside a musubi destination: nothing above it holds a "
            f"{DOCUMENTS}/ and a {TRACES}/"
        )

    # -- what is there -----------------------------------------------------

    def artefact(self, key: str) -> str:
        return _read(self.destination / DOCUMENTS / key)

    def held(self, key: str) -> Held:
        """The map for one artefact, read against the contract.

        Refuses a contract it does not recognise rather than parsing hopefully.
        A map read wrong points a reader at the wrong place in their own file,
        which is the failure this whole project exists to make impossible.
        """
        body = _document(self.destination / TRACES / f"{key}.json")
        contract = str(body.get("contract", ""))
        if not contract.startswith("musubi.trace-map/1"):
            raise ContractError(
                f"the map for {key} declares contract {contract!r}, which this does not "
                f"recognise. Refusing rather than resolving an offset against a guess."
            )
        unit = str(body.get("source_unit") or CHARACTERS)
        if unit not in KNOWN_UNITS:
            # A unit this does not recognise is refused rather than read as
            # characters. Reading page indices as character offsets would point
            # a citation at a confident wrong place, which is the failure this
            # project exists to prevent.
            raise ContractError(
                f"the map for {key} measures its source in {unit!r}, which this does "
                f"not recognise. Refusing rather than resolving against a guess."
            )

        segments = tuple(_segment(entry, key) for entry in body.get("segments") or [])
        source = body.get("source") or {}
        coverage = body.get("coverage") or {}
        try:
            trace = TraceMap(
                segments=segments,
                artefact_length=int(coverage.get("characters", 0)),
                source_length=max((s.src.end for s in segments), default=0),
                source_unit=unit,
            )
        except ValueError as error:
            raise TraceError(f"the map for {key} does not hold: {error}") from error

        return Held(
            trace=trace,
            source=SourceReference(
                source_id=str(source.get("source_id", "")),
                unit_key=str(source.get("unit_key", key)),
                content_hash=str(source.get("content_hash", "")),
                media_type=str(source.get("media_type", "")),
                encoding=str(source.get("encoding", "utf-8")),
                bom_bytes=int(source.get("bom_bytes", 0)),
            ),
            converter=str(body.get("converter", "")),
        )

    def manifest_document(self) -> dict[str, Any]:
        """The manifest as it is on disk.

        Raises rather than returning ``{}`` when it is missing: ``roots()``
        degrades because a trace still answers without it, and a verification
        with no manifest has nothing to verify against.
        """
        path = self.destination / MANIFEST
        if not path.is_file():
            raise ContractError(
                f"{self.destination} holds no {MANIFEST}. A destination without one is "
                f"not a corpus musubi wrote, and there is nothing to check it against."
            )
        return _document(path)

    def artefact_bytes(self, key: str) -> bytes:
        return (self.destination / DOCUMENTS / key).read_bytes()

    def key_of(self, artefact_path: str, trace_path: str) -> str:
        document = f"{DOCUMENTS}/"
        traces = f"{TRACES}/"
        if not artefact_path.startswith(document):
            raise ContractError(
                f"the manifest puts a document at {artefact_path!r}, which is not under "
                f"{document}. This is not the layout musubi writes."
            )
        key = artefact_path[len(document) :]
        # The prefix says where it starts, not where it ends up. `documents/`
        # followed by `../../` leaves the corpus, and on Windows followed by
        # `C:/` leaves it without a `..` in sight, because joining an absolute
        # path discards everything to its left. `verify` would then hash a file
        # nobody synced and report on it by a name that is not its own.
        if not self._stays_inside(key):
            raise ContractError(
                f"the manifest puts a document at {artefact_path!r}, which does not stay "
                f"under {document}. Refusing rather than reading a file outside the corpus."
            )
        expected = f"{traces}{key}.json"
        if trace_path != expected:
            raise ContractError(
                f"the document {artefact_path!r} names its map as {trace_path!r} and the "
                f"layout puts it at {expected!r}"
            )
        return key

    def _stays_inside(self, key: str) -> bool:
        """Does joining this key actually land under `documents/`?

        Asked of the filesystem rather than of the string, because the ways out
        are platform-shaped. `../..` is the obvious one. `C:/Windows/win.ini` is
        not: it holds no `..`, it is not absolute by POSIX rules, and joining it
        on Windows **discards everything to its left**. A syntactic check would
        have to know which platform it is on to be right; this one does not.
        """
        under = self.destination / DOCUMENTS
        try:
            (under / key).resolve().relative_to(under.resolve())
        except (OSError, ValueError):
            return False
        return bool(key) and not key.endswith("/")

    def roots(self) -> dict[str, str]:
        """Where each source read from, as the manifest recorded it.

        Recorded for a reader rather than for the run id, which is what makes it
        usable here and useless for re-deriving anything.
        """
        manifest = self.destination / MANIFEST
        if not manifest.is_file():
            return {}
        body = _document(manifest)
        return {
            str(source.get("source_id", "")): str(source.get("root", ""))
            for source in body.get("sources") or []
            if source.get("root")
        }

    def source(self, reference: SourceReference) -> tuple[Path, bytes] | None:
        """The file this artefact was made from, if it is still findable.

        ``None`` rather than a raise: the map alone is still an answer, and a
        source that has been moved or deleted degrades a report rather than
        failing it.
        """
        path = self._source_file(reference)
        if path is None:
            return None
        try:
            return path, path.read_bytes()
        except OSError:  # pragma: no cover - a race, not a state
            # The file was there when `is_file()` was asked and gone, or
            # unreadable, by the time it was opened. There is no portable way to
            # arrange that in a test, and degrading is still the right answer.
            return None

    def _source_file(self, reference: SourceReference) -> Path | None:
        root = self.roots().get(reference.source_id)
        if not root:
            return None
        direct = Path(root).joinpath(*reference.unit_key.split("/"))
        if direct.is_file():
            return direct
        return _by_normalized_name(Path(root), reference.unit_key.split("/"))


def _by_normalized_name(root: Path, parts: list[str]) -> Path | None:
    """Find a path whose names normalize to these, one level at a time.

    [ADR-0014]'s stated cost. A key is NFC and a macOS filename is NFD, so the
    same note has a name that does not concatenate back. Searching is what the
    ADR said this would take.
    """
    here = root
    for part in parts:
        if not here.is_dir():
            return None
        wanted = unicodedata.normalize("NFC", part)
        found = next(
            (
                child
                for child in sorted(here.iterdir(), key=lambda p: p.name)
                if unicodedata.normalize("NFC", child.name) == wanted
            ),
            None,
        )
        if found is None:
            return None
        here = found
    return here if here.is_file() else None


def _segment(entry: Any, key: str) -> Segment:
    try:
        out = entry["out"]
        src = entry["src"]
        kind = Kind(entry["kind"])
    except (KeyError, TypeError, ValueError) as error:
        raise ContractError(f"the map for {key} holds a segment this cannot read: {error}") from (
            error
        )
    return Segment(
        out=Span(int(out[0]), int(out[1])),
        src=Span(int(src[0]), int(src[1])),
        kind=kind,
        rule=entry.get("rule"),
    )


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise TraceError(f"cannot read {path}: {error}") from error


def _document(path: Path) -> dict[str, Any]:
    try:
        body = json.loads(_read(path))
    except json.JSONDecodeError as error:
        raise ContractError(f"{path} is not readable as a document: {error}") from error
    if not isinstance(body, dict):
        raise ContractError(f"{path} is a {type(body).__name__}, not an object")
    return body
