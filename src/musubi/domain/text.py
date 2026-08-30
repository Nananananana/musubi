"""Rewriting that keeps its offsets, and decoding that refuses to guess.

Every transformation musubi performs is a *rewrite*: a set of replacements over
a source string, applied to produce a new string **and an account of where every
character of it came from**. Deleting is replacing with the empty string;
inserting is replacing an empty span. There is one code path, and the account
falls out of it rather than being maintained beside it.

The account is a sequence of :class:`Piece`, and the invariant that makes it
worth anything is that the pieces tile **both sides**: the output with no gap
and no overlap, and the source with no gap and no overlap. A rewrite that lost a
character of the source would be a rewrite whose map had quietly started lying,
and every offset after that point would be wrong in a way nothing downstream
could detect. ADR-0004 is the reason; the property tests are the enforcement.

Nothing here knows what a file is. It is handed a string, or a block of bytes,
and hands back values.
"""

from __future__ import annotations

import codecs
import itertools
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .span import Span, resolve

__all__ = [
    "KEPT",
    "Decoded",
    "Piece",
    "Replacement",
    "Rewritten",
    "decode",
    "normalize_line_endings",
    "rewrite",
]

#: The kind carried by a run that was not touched. Its output and its source
#: are the same characters, so an offset inside it resolves exactly.
KEPT = "kept"

#: The kind :func:`normalize_line_endings` reports.
LINE_ENDING = "line_ending"


@dataclass(frozen=True, slots=True)
class Replacement:
    """Put ``text`` where ``span`` is.

    ``text=""`` is a deletion. A zero-length ``span`` is an insertion. ``kind``
    says why, and travels all the way to the trace map -- a rewrite that cannot
    say why it happened is a rewrite nobody can appeal.
    """

    span: Span
    text: str
    kind: str

    def __post_init__(self) -> None:
        if not self.kind:
            raise ValueError("a replacement with no kind cannot be explained later")
        if self.kind == KEPT:
            raise ValueError(f"{KEPT!r} is reserved for runs that were not replaced")


@dataclass(frozen=True, slots=True)
class Piece:
    """One run of the output, and the run of the source it accounts for.

    For a :data:`KEPT` piece the two are the same characters and the same
    length, so an offset inside it maps exactly. For any other kind they are
    two descriptions of the same content and the correspondence holds only at
    the ends -- which is why :meth:`Rewritten.source_offset` declines to answer
    inside one.
    """

    out: Span
    src: Span
    kind: str


@dataclass(frozen=True, slots=True)
class Rewritten:
    """The result of a rewrite: the text, and the account of where it came from."""

    text: str
    pieces: tuple[Piece, ...]
    source_length: int

    def __post_init__(self) -> None:
        _assert_tiles((piece.out for piece in self.pieces), len(self.text), "output")
        _assert_tiles((piece.src for piece in self.pieces), self.source_length, "source")

    def piece_at(self, offset: int) -> Piece:
        """The piece covering this output offset.

        Zero-length pieces -- deletions -- cover nothing and are skipped, which
        is what makes "exactly one piece" true rather than nearly true.
        """
        for piece in self.pieces:
            if piece.out.contains(offset):
                return piece
        raise ValueError(f"offset {offset} is outside the output [0:{len(self.text)}]")

    def source_offset(self, offset: int) -> int | None:
        """Where this output character came from, or ``None`` if that is not a
        question with an exact answer.

        Inside a :data:`KEPT` run the relation is affine and the answer is
        exact. Inside a rewritten run there is no character-level
        correspondence, and inventing one is precisely what this project exists
        to stop. Ask :meth:`source_span_of` instead, which answers as a range.
        """
        piece = self.piece_at(offset)
        if piece.kind != KEPT:
            return None
        return piece.src.start + (offset - piece.out.start)

    def source_span_of(self, out: Span) -> Span:
        """The source this output range came from.

        Clipped inside :data:`KEPT` runs, where the relation is exact, and taken
        whole for every other kind, where it is not. So a query that touches one
        character of a rewritten run reports the whole of what that run replaced
        -- which is honest, and is what a reader following a citation wants to
        be shown.
        """
        if out.end > len(self.text):
            raise ValueError(f"{out} is outside the output [0:{len(self.text)}]")

        runs = [(piece.out, piece.src, piece.kind == KEPT) for piece in self.pieces]
        found = resolve(runs, out)
        # ``None`` only when there are no pieces, which happens only for an
        # empty source -- and an empty source came from position zero.
        return Span(0, 0) if found is None else found


@dataclass(frozen=True, slots=True)
class Decoded:
    """Bytes, read as text, with what it took to do it."""

    text: str
    encoding: str
    #: Bytes consumed by a byte-order mark. Never zero on a file a Windows
    #: producer wrote without being asked, and a real offset difference: every
    #: byte offset in the file is that much further along than the character
    #: index suggests.
    bom_length: int
    #: The codec that turns ``text`` back into the bytes it came from, without
    #: adding a mark of its own. ``utf-8`` for both UTF-8 forms; ``utf-16-le``
    #: or ``utf-16-be`` and never ``utf-16``, which would write a fresh
    #: byte-order mark every time it was asked to measure something.
    codec: str = "utf-8"


def rewrite(source: str, replacements: Iterable[Replacement]) -> Rewritten:
    """Apply replacements to ``source``, and report where everything went.

    Replacements may arrive in any order; they are applied in source order. Two
    insertions at the same point keep the order they were given, which is the
    only ordering rule that is not derivable from the spans and so the only one
    that has to be stated.

    Overlapping replacements are refused rather than resolved. Which of two
    overlapping rules should win is a decision somebody has to make deliberately
    (ADR-0009), and a library that picked silently would make it forty times a
    run.
    """
    # A replacement that takes nothing and puts nothing is not an event. Left
    # in, it would split the run it sits inside into two identical halves and
    # put a piece in the tiling that accounts for no source and no output.
    happening = [r for r in replacements if not (r.span.is_empty and not r.text)]
    ordered = sorted(happening, key=lambda r: (r.span.start, r.span.end))
    _refuse_overlaps(ordered)

    pieces: list[Piece] = []
    out: list[str] = []
    at_out = 0
    at_src = 0

    def keep_until(source_offset: int) -> None:
        nonlocal at_out, at_src
        if source_offset <= at_src:
            return
        run = source[at_src:source_offset]
        pieces.append(
            Piece(
                out=Span(at_out, at_out + len(run)),
                src=Span(at_src, source_offset),
                kind=KEPT,
            )
        )
        out.append(run)
        at_out += len(run)
        at_src = source_offset

    for replacement in ordered:
        if replacement.span.end > len(source):
            raise ValueError(
                f"replacement {replacement.span} is outside the source [0:{len(source)}]"
            )
        keep_until(replacement.span.start)
        pieces.append(
            Piece(
                out=Span(at_out, at_out + len(replacement.text)),
                src=replacement.span,
                kind=replacement.kind,
            )
        )
        out.append(replacement.text)
        at_out += len(replacement.text)
        at_src = replacement.span.end

    keep_until(len(source))
    return Rewritten(text="".join(out), pieces=tuple(pieces), source_length=len(source))


_LINE_ENDING = re.compile(r"\r\n|\r")


def normalize_line_endings(text: str) -> Rewritten:
    """CRLF and lone CR become LF, and the map says where.

    musubi reads folders written on other people's machines, and a corpus whose
    line endings depend on which one would make every offset machine-specific
    and every diff noise. This is the smallest transformation that is not the
    identity, which makes it the one to get right first.
    """
    return rewrite(
        text,
        [
            Replacement(Span(match.start(), match.end()), "\n", LINE_ENDING)
            for match in _LINE_ENDING.finditer(text)
        ],
    )


def decode(data: bytes) -> Decoded:
    """Read bytes as text, or refuse.

    UTF-8, with or without a byte-order mark, and UTF-16 when it announces
    itself with one. Nothing else.

    **No detection, and no fallback.** A guessed legacy encoding writes mojibake
    into a corpus that will be sent to a model, and it looks exactly like
    successful ingestion -- no error, no warning, a file full of plausible
    nonsense. The caller reports the unit as unreadable and the owner converts
    it, which is a visible problem rather than an invisible one.
    """
    if data.startswith(codecs.BOM_UTF8):
        return Decoded(
            text=data[len(codecs.BOM_UTF8) :].decode("utf-8"),
            encoding="utf-8-sig",
            bom_length=len(codecs.BOM_UTF8),
            codec="utf-8",
        )
    for bom, codec in ((codecs.BOM_UTF16_LE, "utf-16-le"), (codecs.BOM_UTF16_BE, "utf-16-be")):
        if data.startswith(bom):
            return Decoded(
                text=data.decode("utf-16"),
                encoding="utf-16",
                bom_length=len(bom),
                codec=codec,
            )
    try:
        return Decoded(text=data.decode("utf-8"), encoding="utf-8", bom_length=0)
    except UnicodeDecodeError as error:
        raise ValueError(
            f"not decodable as UTF-8 or as UTF-16 with a byte-order mark "
            f"(byte {error.start} is {data[error.start]:#04x}); musubi does not guess an "
            f"encoding, because a wrong guess is indistinguishable from a successful read"
        ) from error


def _refuse_overlaps(ordered: Sequence[Replacement]) -> None:
    for earlier, later in itertools.pairwise(ordered):
        if earlier.span.overlaps(later.span):
            raise ValueError(
                f"replacements {earlier.kind!r} {earlier.span} and {later.kind!r} "
                f"{later.span} overlap; which one wins is a decision, not a default"
            )


def _assert_tiles(spans: Iterable[Span], total: int, side: str) -> None:
    at = 0
    for span in spans:
        if span.start != at:
            raise ValueError(
                f"the {side} tiling has a gap or an overlap at {at}: the next piece is {span}"
            )
        at = span.end
    if at != total:
        raise ValueError(f"the {side} tiling covers [0:{at}] but the {side} is [0:{total}]")
