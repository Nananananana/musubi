"""A folder of pages somebody fetched, each with a record of the fetch beside it.

## Who this is for

An orchestrator that pulls articles from feeds and wants them in a corpus
whose documents can be traced back to **the bytes it fetched**. The `sora`
orchestrator asked for exactly this (`musubi-work/01_sora_requirements.md`,
R1): it lays pages out as ``<feed>/<date>/<id>.html`` and has two facts about
each that the page itself does not state -- the URL it came from and when it
was fetched -- and it wants those facts to reach the consumer downstream.

## Where the facts travel, and why not anywhere else

Three places were available and two were wrong.

**Not a sidecar in the corpus.** `tsumugi`'s corpus walk indexes a sidecar as a
document (measured, in `emitters/documents.py`), and the artefact's path has to
be exactly `documents/` + `unit_key` (#62).

**Not front matter the producer writes into the page.** The orchestrator said
so itself: *Sora が勝手に front matter を書き足すことはしない*. A page with
front matter it did not have when it was fetched is a page whose bytes are no
longer the fetched bytes, and the trace would then lead back to something the
orchestrator made up.

**So: a record beside the page, in the source tree, read by this adapter,
stated by musubi.** ``<id>.html`` and ``<id>.fetch.json``:

```json
{"url": "https://example.test/a/1", "fetched_at": "2026-09-05T03:12:00Z",
 "canonical_url": "https://example.test/a/1"}
```

The record is the orchestrator saying *here is what I know about this fetch*.
That is a fact about the source, and musubi is entitled to state facts about a
source in a document's front matter (`domain/frontmatter.py`): it writes
``source_url`` and ``fetched_at`` as flat ``key: value`` lines, which is the
one shape the downstream reader parses. The page's bytes are untouched, so a
trace still leads to what was fetched.

## What the record changes, and what it does not

**Identity stays the path.** ``key_derivation`` is ``path``, as for any
folder, and the record does not enter the unit's ``content_hash`` -- that is
the hash of the page, and `musubi trace` checks the page on disk against it.
The record enters the *artefact* instead: the manifest lists each artefact's
facts, and a re-sync that finds the record changed converts the unit again
even though the page did not change ([ADR-0036] compares both).

**A missing record is not an error.** The page is read and states no facts.
A record that is present and cannot be read *is* a skip, with a reason: a
record that lies is worse than none.

## The same article from two feeds

``canonical_url`` is what the orchestrator asked for (U2). Two pages with the
same canonical URL -- or the same ``url``, when no canonical one is given --
are one article, and a corpus with both is a corpus that answers the same
question twice. The first in walk order is read; the rest are skipped with
reason ``duplicate`` and the origin of the one that was kept, so the manifest
says which page stood for which.

The choice is made here and not in the orchestrator's keying, because a key
that is a hash of a URL is a key nobody can read in a citation, and
[ADR-0006]'s weak-but-legible ``path`` is the better trade for a folder whose
layout the orchestrator already controls.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from ...ports.source import Discovery, Found, Skipped
from .filesystem import MACHINERY, MAXIMUM_BYTES, FilesystemSource

__all__ = ["FACTS", "RECORD_SUFFIX", "FetchedSource"]

#: What a record file is called, beside the page it describes.
RECORD_SUFFIX = ".fetch.json"

#: Record key -> front matter key. Only these travel; a record may say more,
#: and what it says beyond this is the orchestrator's business.
FACTS: tuple[tuple[str, str], ...] = (
    ("url", "source_url"),
    ("fetched_at", "fetched_at"),
    ("canonical_url", "canonical_url"),
)


class FetchedSource(FilesystemSource):
    """Satisfies :class:`~musubi.ports.source.Source`.

    A filesystem source that reads the fetch record beside each page and
    refuses to read the same article twice.
    """

    def __init__(
        self,
        root: Path,
        *,
        source_id: str = "fetched",
        machinery: Iterable[str] = MACHINERY,
        maximum_bytes: int = MAXIMUM_BYTES,
    ) -> None:
        super().__init__(
            root,
            source_id=source_id,
            adapter="fetched@1",
            machinery=machinery,
            maximum_bytes=maximum_bytes,
        )

    def discover(self) -> Discovery:
        walked = super().discover()
        found: list[Found] = []
        skipped = list(walked.skipped)

        # Which page stands for which article. Walk order, which is sorted at
        # every level, so the same folder always keeps the same page.
        seen: dict[str, str] = {}
        for page in walked.found:
            article = _article_of(page)
            if article is not None and article in seen:
                skipped.append(
                    Skipped(page.origin, "duplicate", f"same article as {seen[article]}")
                )
                continue
            if article is not None:
                seen[article] = page.origin
            found.append(page)

        return Discovery(
            found=tuple(found),
            skipped=tuple(skipped),
            caps=(
                *walked.caps,
                "a page whose canonical url another page already carries is not read",
            ),
        )

    def _consider(
        self, entry: Path, relative: str, found: list[Found], skipped: list[Skipped]
    ) -> None:
        if entry.name.endswith(RECORD_SUFFIX):
            # The record is this adapter's machinery, not a document and not a
            # skip: reporting every record as `unknown_format` would double the
            # length of every manifest for no information.
            return

        before = len(found)
        super()._consider(entry, relative, found, skipped)
        if len(found) == before:
            return  # skipped by the walk, with its reason already recorded

        page = found.pop()
        record = entry.with_name(entry.name + RECORD_SUFFIX)
        if not record.is_file():
            found.append(page)
            return
        try:
            facts = _facts_from(record)
        except ValueError as error:
            skipped.append(Skipped(relative, "bad_fetch_record", str(error)))
            return
        found.append(replace(page, facts=facts))


def _facts_from(record: Path) -> tuple[tuple[str, str], ...]:
    """The record's facts, as front matter keys, or a reason it cannot be read."""
    try:
        body = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{record.name} is not a JSON object: {error}") from error
    if not isinstance(body, dict):
        raise ValueError(f"{record.name} is a {type(body).__name__}, not an object")

    facts = []
    for theirs, ours in FACTS:
        if theirs not in body:
            continue
        value = body[theirs]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{record.name} gives {theirs!r} as {value!r}, not a bare string")
        if "\n" in value or "\r" in value:
            # The downstream reader takes one line per key, and a value that
            # breaks the line would put the rest of it into the document body.
            raise ValueError(f"{record.name} gives {theirs!r} with a line break in it")
        facts.append((ours, value.strip()))
    return tuple(facts)


def _article_of(page: Found) -> str | None:
    facts = dict(page.facts)
    return facts.get("canonical_url") or facts.get("source_url")
