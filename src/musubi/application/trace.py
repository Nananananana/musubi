"""Following an offset back to the file it came from. The command the design is for.

Everything else in musubi is a pipeline somebody else also has. This is the part
that only works because of [ADR-0004]: a range in a document musubi built,
resolved through every transformation, to a place in the owner's own file.

Four things it does that a naive answer would not.

**It reports the kind.** A range that lands in a `synthetic` run came from
nothing -- musubi wrote it -- and saying so is the difference between an answer
and a wrong answer.

**It reports what was taken out of the range.** A removal occupies no output, so
it overlaps nothing and a span union covers it silently. Somebody tracing a
stretch that had a tracking parameter cut out of the middle of it should be
told, which is [ADR-0005] applied to a query rather than to a manifest.

**It converts to bytes here, and only here.** The map is in characters
([ADR-0018]) because that is the only unit composition is sound in. Turning one
into a byte offset takes the encoding, the byte-order mark and the file, and
this is the layer that has all three.

**It checks the source has not changed.** The map carries the source's hash. If
the file on disk no longer matches, the offsets are about a document that no
longer exists, and reporting them without saying so would point a reader
confidently at the wrong place.

All the I/O is behind :class:`~musubi.ports.corpus.CorpusReader`. What is left
here is arithmetic, which is why it can be tested without a disk.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from ..domain.hashing import content_hash
from ..domain.span import Span
from ..domain.text import Decoded, decode
from ..domain.trace import CHARACTERS, Kind, Segment
from ..errors import TraceError
from ..ports.corpus import CorpusReader, SourceReference

__all__ = ["STATUSES", "Resolution", "as_document", "resolve"]


@dataclass(frozen=True, slots=True)
class Resolution:
    """Where a range of an artefact came from, and how sure that is."""

    artefact: str
    out: Span
    excerpt: str
    #: The kinds the range passes through, in order and without repeats.
    kinds: tuple[Kind, ...]
    #: Why each non-verbatim run is what it is, in the same order.
    rules: tuple[str, ...]
    converter: str
    source: SourceReference
    #: The range in the source, counted in :attr:`source_unit`.
    source_span: Span
    #: What ``source_span`` indexes: characters of the decoded source
    #: ([ADR-0018]), or `opaque` for a converter whose source has no decoded
    #: text to count -- a PDF's pages ([ADR-0025]). **A caller must read this
    #: before doing arithmetic on the span**, and a report must say it, because
    #: `[0:1]` means one character or one page and the numbers look identical.
    source_unit: str = CHARACTERS
    #: In bytes of the file, when the file was there to measure against.
    source_bytes: Span | None = None
    source_path: Path | None = None
    source_excerpt: str | None = None
    #: Set when the source is no longer the file the map was built from. The
    #: offsets are then about a document that no longer exists.
    changed: bool = False
    #: Set when the source exists and was **not** opened, because it lies
    #: outside the folder the caller is confined to. The character range is
    #: still the answer; the bytes and the excerpt are not offered.
    source_withheld: bool = False

    @property
    def is_synthetic(self) -> bool:
        """Nothing in this range came from the source: musubi wrote all of it."""
        return all(kind is Kind.SYNTHETIC for kind in self.kinds)

    @property
    def status(self) -> str:
        """One word for what kind of answer this is, for a caller that branches.

        `docs/contracts.md` rule 7 separates *musubi wrote this* from *this did
        not resolve*, and a consumer drawing a screen has to draw them
        differently. Five words, checked in the order that decides:

        ``synthetic``            musubi wrote every character in the range
        ``resolved``             a place in the source, and the file agrees
        ``source_changed``       a place in the source, and the file no longer
                                 holds what the map was built from
        ``source_missing``       a place in the source, and no file to open
        ``source_outside_root``  a place in the source, and a file the caller
                                 may not read from where it stands
        """
        if self.is_synthetic:
            return "synthetic"
        if self.source_withheld:
            return "source_outside_root"
        if self.source_path is None:
            return "source_missing"
        if self.changed:
            return "source_changed"
        return "resolved"


#: Every value `Resolution.status` can take, for a consumer to switch on and a
#: test to enumerate. A status not in this list is a musubi bug.
STATUSES: tuple[str, ...] = (
    "resolved",
    "synthetic",
    "source_changed",
    "source_missing",
    "source_outside_root",
)


def resolve(corpus: CorpusReader, key: str, out: Span, *, within: Path | None = None) -> Resolution:
    """Answer for one range of one artefact.

    ``within`` confines what this may open. The manifest names where each
    source was read from as an absolute path, and following it is the point of
    a trace -- but a caller that is itself confined to a folder (the MCP
    server, [ADR-0007]) must not be walked out of it by a manifest somebody
    else wrote. A source outside ``within`` is located, not opened, and the
    answer says so.
    """
    text = corpus.artefact(key)
    if out.end > len(text):
        raise TraceError(f"{out} is outside {key}, which has {len(text)} characters")

    held = corpus.held(key)
    if held.trace.artefact_length != len(text):
        raise TraceError(
            f"the map for {key} describes {held.trace.artefact_length} characters and the "
            f"artefact has {len(text)}: one of the two has been edited since the sync"
        )

    touched = [segment for segment in held.trace.segments if _bears_on(segment, out)]
    resolution = Resolution(
        artefact=key,
        out=out,
        excerpt=out.slice(text),
        kinds=tuple(dict.fromkeys(segment.kind for segment in touched)),
        rules=tuple(dict.fromkeys(s.rule for s in touched if s.rule)),
        converter=held.converter,
        source=held.source,
        source_span=held.trace.source_span_of(out),
        source_unit=held.source_unit,
    )
    return _against_the_file(corpus, resolution, within)


def as_document(found: Resolution) -> dict[str, object]:
    """The answer as the one shape every interface hands out.

    The command line and the MCP server used to each shape their own, and a
    consumer reading both had two vocabularies for one answer. One function,
    and `status` in it, so that a screen can branch on a word rather than on
    the presence of a byte range.
    """
    return {
        "status": found.status,
        "artefact": found.artefact,
        "out": [found.out.start, found.out.end],
        "excerpt": found.excerpt,
        "kinds": [kind.value for kind in found.kinds],
        "rules": list(found.rules),
        "converter": found.converter,
        "source": {
            "source_id": found.source.source_id,
            "unit_key": found.source.unit_key,
            "encoding": found.source.encoding,
            "bom_bytes": found.source.bom_bytes,
            "unit": found.source_unit,
            "characters": [found.source_span.start, found.source_span.end],
            "bytes": (
                None
                if found.source_bytes is None
                else [found.source_bytes.start, found.source_bytes.end]
            ),
            "path": None if found.source_path is None else str(found.source_path),
            "excerpt": found.source_excerpt,
            "changed": found.changed,
        },
    }


def _against_the_file(
    corpus: CorpusReader, resolution: Resolution, within: Path | None
) -> Resolution:
    """Open the source, if it is still there and may be opened, and say what
    the map cannot.

    A resolution without the file is still an answer -- the character range is
    what the map holds -- so a missing source degrades the report rather than
    failing it. What it cannot do without the file is give a byte offset, and it
    says that rather than guessing one.
    """
    path = corpus.locate(resolution.source)
    if path is None:
        return resolution
    if within is not None and not _under(path, within):
        # Located and not opened. Returning the path would already say more
        # than a confined caller should learn about a folder it cannot read.
        return replace(resolution, source_withheld=True)
    raw = corpus.read_source(path)
    if raw is None:
        return resolution

    changed = content_hash(raw) != resolution.source.content_hash
    if resolution.source_unit != CHARACTERS:
        # There is no decoded text to count into, so there is no byte offset to
        # give and no excerpt to slice. The page is the answer, and the path is
        # what makes it actionable: a reader opens the file at that page.
        # Attempting the arithmetic anyway would decode a PDF as if it were
        # text and hand back a byte range into mojibake.
        return replace(resolution, source_path=path, changed=changed)

    decoded = _as_the_map_read_it(raw, resolution.source.encoding)
    if decoded is None:
        # No longer readable the way it was read, so certainly edited. The
        # character range is still what the map holds.
        return replace(resolution, source_path=path, changed=True)

    span = resolution.source_span
    if span.end > len(decoded.text):
        # Shorter than the map says, which the hash check has already reported.
        return replace(resolution, source_path=path, changed=True)

    start = decoded.bom_length + len(decoded.text[: span.start].encode(decoded.codec))
    end = decoded.bom_length + len(decoded.text[: span.end].encode(decoded.codec))
    return replace(
        resolution,
        source_path=path,
        source_bytes=Span(start, end),
        source_excerpt=span.slice(decoded.text),
        changed=changed,
    )


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _as_the_map_read_it(raw: bytes, encoding: str) -> Decoded | None:
    """Decode the source the way the run that wrote the map decoded it.

    **The map records the encoding for exactly this.** [ADR-0018] says a
    character offset becomes a byte offset given the encoding, the mark's length
    and the file, and the map carries the first two so that this can have the
    third.

    Reading it back with `domain.text.decode` instead was a real defect and a
    quiet one: that reader takes UTF-8, UTF-16 with a mark and the self-
    describing stateful encodings, and a Shift-JIS note read under
    `encoding = "detect"` ([ADR-0031]) is none of those. It raised, and `trace`
    concluded **the source has changed since the sync** about a file nobody had
    touched. The demo found it; nothing else did, because every test fixture was
    UTF-8.

    `decode` is still tried first, because it is the one that reports a
    byte-order mark, and a mark is bytes the offsets have to step over.
    """
    try:
        return decode(raw)
    except ValueError:
        pass
    if not encoding:
        return None
    try:
        return Decoded(text=raw.decode(encoding), encoding=encoding, bom_length=0, codec=encoding)
    except (LookupError, UnicodeDecodeError):
        return None


def _bears_on(segment: Segment, out: Span) -> bool:
    """Which segments a range passes through, for the purpose of naming kinds.

    Wider than the arithmetic ``source_span_of`` uses, deliberately. A removal
    occupies no output, so it overlaps nothing and the span union covers it
    silently -- but somebody tracing a range that had something taken out of the
    middle of it should be told.
    """
    if segment.out.is_empty:
        return out.contains(segment.out.start) or (out.is_empty and out.start == segment.out.start)
    if out.is_empty:
        return segment.out.start <= out.start <= segment.out.end
    return segment.out.overlaps(out)
