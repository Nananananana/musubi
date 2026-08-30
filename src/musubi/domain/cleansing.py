"""Finding URLs, and taking the tracking out of them without losing the offsets.

The algorithm; the rules it runs are data ([ADR-0009]) and live in
``infrastructure/rules/``.

Everything here is a linear scan. There is no regular expression matching a rule
([ADR-0016]) and no regular expression finding a URL either: a pattern that
scans somebody's whole corpus, unattended, is not a place to accept
backtracking. The scanner walks forward, consumes what a URL can contain, and
trims what punctuation put on the end.

The output is a set of :class:`~musubi.domain.text.Replacement` -- so cleansing
goes through the same one code path as every other transformation and gets its
tiling for free -- and a :class:`~musubi.domain.removal.RemovalRecord` for every
rule that fired.

**One replacement per query, one record per parameter.** A query cut by three
rules is one discontinuity in the artefact and three things somebody may want to
appeal, and collapsing either into the other would lose something. The map says
*this stretch became that shorter stretch*, which is exactly true; the manifest
says which rules did it and where each one struck.
"""

from __future__ import annotations

from dataclasses import dataclass

from .removal import RemovalRecord, Ruleset
from .span import Span
from .text import Replacement, Rewritten, rewrite

__all__ = ["Cleansed", "cleanse", "find_urls"]

#: The kind carried by the replacement a cleansed query produces. The rule ids
#: are on the removal records: a single query can be cut by several rules at
#: once, and a replacement names one thing.
QUERY_KIND = "url_query"

_SCHEMES = ("https://", "http://")

#: A URL ends at whitespace or at something that cannot be inside one. ``<`` and
#: ``>`` are here so that an autolink written ``<https://example.com>`` ends
#: where the writer meant it to.
_TERMINATORS = frozenset(" \t\n\r\f\v<>\"'`|\\^{}")

#: Trailing punctuation belongs to the sentence, not to the link.
_TRAILING = ".,;:!?"

_CLOSERS = {")": "(", "]": "[", "}": "{"}


@dataclass(frozen=True, slots=True)
class Cleansed:
    """Cleansed text, its map, and the account of what was taken."""

    rewritten: Rewritten
    removals: tuple[RemovalRecord, ...]

    @property
    def text(self) -> str:
        return self.rewritten.text


def cleanse(text: str, ruleset: Ruleset) -> Cleansed:
    """Take the tracking parameters out of every URL in this text."""
    replacements: list[Replacement] = []
    removals: list[RemovalRecord] = []

    for url in find_urls(text):
        query = _query_span(text, url)
        if query is None:
            continue
        rebuilt, struck = _strip(text, query, ruleset)
        if not struck:
            continue
        replacements.append(Replacement(span=query, text=rebuilt, kind=QUERY_KIND))
        removals.extend(struck)

    return Cleansed(
        rewritten=rewrite(text, replacements),
        removals=tuple(removals),
    )


def find_urls(text: str) -> list[Span]:
    """Every URL in the text, as spans, left to right.

    Deliberately simple and deliberately linear. Being wrong about where a URL
    ends produces a worse *removal* and cannot produce a wrong *offset*, which
    is the same trade ADR-0001 makes for the parsers.
    """
    found: list[Span] = []
    at = 0
    while at < len(text):
        starts = [found_at for s in _SCHEMES if (found_at := text.find(s, at)) != -1]
        if not starts:
            break
        start = min(starts)
        end = start
        while end < len(text) and text[end] not in _TERMINATORS:
            end += 1
        end = _trim(text, start, end)
        if end > start:
            found.append(Span(start, end))
        at = max(end, start + 1)
    return found


def _trim(text: str, start: int, end: int) -> int:
    """Give back the punctuation that belongs to the sentence around the link."""
    while end > start:
        last = text[end - 1]
        if last in _TRAILING:
            end -= 1
            continue
        opener = _CLOSERS.get(last)
        if opener is None:
            break
        # A URL may legitimately contain brackets -- a Wikipedia article, a
        # generated report. Only give back a closer that never opened.
        inside = text[start : end - 1]
        if inside.count(last) >= inside.count(opener):
            end -= 1
            continue
        break
    return end


def _query_span(text: str, url: Span) -> Span | None:
    """The ``?query`` part of this URL, including the question mark."""
    body = url.slice(text)
    mark = body.find("?")
    if mark == -1:
        return None
    fragment = body.find("#", mark)
    end = url.start + (fragment if fragment != -1 else len(body))
    return Span(url.start + mark, end)


def _strip(text: str, query: Span, ruleset: Ruleset) -> tuple[str, list[RemovalRecord]]:
    """Rebuild this query without the parameters the rules claim."""
    body = query.slice(text)[1:]  # past the '?'
    at = query.start + 1

    kept: list[str] = []
    struck: list[RemovalRecord] = []
    for part in body.split("&"):
        name = part.split("=", 1)[0]
        rule = ruleset.matching(name) if name else None
        if rule is None:
            kept.append(part)
        else:
            struck.append(RemovalRecord.of(rule, Span(at, at + len(part)), part))
        at += len(part) + 1  # past the '&'

    if not struck:
        return query.slice(text), []
    return ("?" + "&".join(kept) if kept else ""), struck
