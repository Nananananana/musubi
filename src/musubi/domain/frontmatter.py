"""The two things musubi is entitled to say about a document it converted.

`tsumugi` reads front matter as **flat ``key: value`` lines and nothing more** --
no YAML parser, on the stated grounds that one is a dependency and the structure
inside front matter has never been what makes a document findable. So musubi
writes flat ``key: value`` lines and nothing more, and the two halves of the seam
have the same shape by agreement rather than by luck.

Two consequences follow from reading that parser rather than guessing at it.

**Values are not quoted.** `tsumugi` strips the line and keeps what is left, so a
quoted value arrives with its quotes. A value that cannot be written bare -- one
containing a newline -- is refused rather than escaped into something the reader
would hand back wrong.

**The first occurrence of a key wins**, because the parser uses ``setdefault``.
So musubi inserts only the keys a document does not already state, and an owner
who declared their own is left alone.

## What is deliberately not written

**No ``title``.** `tsumugi` already takes one from the document's first level-one
heading when the front matter does not give it, and the heading is a better title
than a filename. Writing ``title: gear`` would *override* 「テント設計メモ」 with
something worse.

**No ``observed_at``.** musubi does not know when a note was written. The
filesystem knows when it was last touched, which is a different fact, and putting
it here would also make an artefact's content depend on its modification time --
so a re-sync that changed nothing would rewrite the corpus, and [ADR-0006]'s
whole idempotence claim would be false.

**Never ``layer: interpretation``** ([ADR-0010]). An interpretation needs a
reading, a reading needs a model, and musubi has none. An interpretation with no
author is laundering.
"""

from __future__ import annotations

from dataclasses import dataclass

from .span import Span
from .text import Replacement

__all__ = [
    "FENCES",
    "FRONT_MATTER",
    "PRODUCER",
    "FrontMatter",
    "block_of",
    "replacements",
    "stated_keys",
]

#: The kind carried by everything this module inserts. It becomes a
#: ``synthetic`` segment: musubi wrote it, and it came from nothing in the
#: source.
FRONT_MATTER = "front_matter"

#: What musubi calls itself in a document's metadata. A contract-shaped name and
#: not a version: a version here would change every artefact in the corpus on
#: every release, and rewrite a corpus that had not changed.
PRODUCER = "musubi.sync/1"

#: What closes a front-matter block, as `tsumugi`'s parser accepts it.
FENCES = ("---", "...")

_LAYERS = ("fact", "measure")


@dataclass(frozen=True, slots=True)
class FrontMatter:
    """The keys musubi states about a document it converted."""

    layer: str = "fact"
    producer: str = PRODUCER

    def __post_init__(self) -> None:
        if self.layer not in _LAYERS:
            raise ValueError(
                f"musubi emits {' or '.join(_LAYERS)} and never {self.layer!r}: an "
                f"interpretation needs a reading, a reading needs a model, and musubi "
                f"has none"
            )
        for name, value in (("layer", self.layer), ("producer", self.producer)):
            if not value or value.strip() != value:
                raise ValueError(f"{name} must be a bare single-line value, not {value!r}")
            if "\n" in value or "\r" in value:
                raise ValueError(
                    f"{name} contains a line break, and the reader takes one line per key"
                )

    def as_lines(self) -> tuple[str, ...]:
        return (f"layer: {self.layer}", f"producer: {self.producer}")


def block_of(text: str) -> Span | None:
    """The document's own front-matter block, or ``None``.

    Detected exactly as `tsumugi`'s parser detects it: an opening fence on the
    very first line, and a closing fence somewhere after it. A document that
    opens a fence and never closes one has no front matter, there as here --
    matching the reader is the whole point, because a block musubi thinks is
    front matter and the reader thinks is prose puts musubi's keys into the
    document body.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != FENCES[0]:
        return None
    at = len(lines[0]) + 1
    for line in lines[1:]:
        if line.strip() in FENCES:
            return Span(0, at + len(line))
        at += len(line) + 1
    return None


def stated_keys(text: str, block: Span) -> frozenset[str]:
    """Which keys this block already states.

    A line scan, not a parse: the reader does not parse either, so anything
    subtler would be musubi disagreeing with its own consumer about what a
    document says.
    """
    found: set[str] = set()
    for line in block.slice(text).split("\n"):
        key, separator, _ = line.partition(":")
        cleaned = key.strip()
        if separator and cleaned and not cleaned.startswith("-") and cleaned not in FENCES:
            found.add(cleaned)
    return frozenset(found)


def replacements(text: str, matter: FrontMatter) -> tuple[Replacement, ...]:
    """What to insert so that this document states what musubi knows.

    Either a whole block at the top, or the missing lines inside the block the
    document already has. Both are insertions, so both become ``synthetic``
    segments and neither moves a character of what the owner wrote.
    """
    lines = matter.as_lines()
    block = block_of(text)

    if block is None:
        body = "\n".join((FENCES[0], *lines, FENCES[0], ""))
        return (Replacement(span=Span(0, 0), text=body, kind=FRONT_MATTER),)

    already = stated_keys(text, block)
    missing = [line for line in lines if line.partition(":")[0] not in already]
    if not missing:
        return ()

    # Immediately after the opening fence, so the keys are inside the block the
    # reader will find, and every offset of the owner's own front matter still
    # points where it did.
    at = text.index("\n") + 1
    return (Replacement(span=Span(at, at), text="\n".join((*missing, "")), kind=FRONT_MATTER),)
