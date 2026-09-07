"""How a tiling is written down, and read back, in one place.

The map is the thing musubi exists to produce, and on a real corpus it was
**10.7 times the size of the documents it describes** ([#76]). The design named
that as a falsification condition of the whole idea:

> If a map routinely exceeds its document, the guarantee costs more storage than
> the corpus. Measured in v0.4; the fix is converter-side, and if there is no
> fix, the map becomes optional and the project is much less interesting.

Minifying the sidecar took it to 4.9x. What was left was not whitespace: a map
was **within 3% of its own minified size**, so the remaining cost was the
segments themselves, at about 71 bytes each. Nearly all of that was the same
five key names and the same rule strings, written out once per segment:

```text
{"out":[0,3],"src":[0,3],"kind":"verbatim"}                       43 bytes
{"out":[3,4],"src":[3,5],"kind":"transformed","rule":"line_ending"}  67 bytes
```

## What this does instead

A segment becomes a **row of numbers**, with the names and the strings hoisted
into tables the file carries:

```json
"segment_fields": ["out_length", "src_start", "src_end", "kind", "rule"],
"kinds": ["verbatim", "transformed", "synthetic", "removal"],
"rules": ["line_ending"],
"segments": [[3, 0, 3, 0, null], [1, 3, 5, 1, 0]]
```

Measured at **18.9 bytes a segment against 71**, which is 3.8x. Nothing about
what a segment *means* changes: same spans, same kinds, same rules, same
answers to `source_span_of` at every offset.

## The tables are in the file, not in this module

A reader uses the file's own `kinds` and `rules` rather than an order it
remembers. That is [ADR-0024]'s rule applied early: a kind added to the enum
later would silently reinterpret every existing map if the order lived only in
the code. Here it costs about 120 bytes a file and buys immunity.

`segment_fields` is checked rather than honoured. A file naming a different
layout is refused, not rearranged -- resolving an offset against a guessed
column order is exactly the confident wrong answer this project exists to avoid.

## Why the output start is not stored

Because the tiling already determines it. [ADR-0004]'s invariant is that the
segments cover every character of the artefact **exactly once**, in order, so
each segment starts where the last one ended and storing that is storing
something already known.

That is the pleasing half: the invariant stops being a rule somebody checks and
becomes a shape the format cannot express a violation of. A map with a gap or an
overlap has nowhere to put it.

## Both shapes are read

Corpora written before this exist and are synced against for months at a time.
A reader that required the new shape would stop resolving every one of them,
which is the mistake [ADR-0041] caught the last time a field moved. An element
that is an object is the old form and is read as such.

[#76]: https://github.com/Nananananana/musubi/issues/76
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..domain.span import Span
from ..domain.trace import Kind, Segment
from ..errors import ContractError

__all__ = ["SEGMENT_FIELDS", "packed", "unpacked"]

#: The columns of a segment row, in order. Written into every map so that a
#: reader can check it rather than assume it.
SEGMENT_FIELDS: tuple[str, ...] = ("out_length", "src_start", "src_end", "kind", "rule")


def packed(segments: Sequence[Segment]) -> dict[str, Any]:
    """The parts of a trace map that describe the tiling.

    Returns the tables and the rows together, because they are meaningless
    apart: a rule index without the rule table is a number.
    """
    kinds: list[str] = []
    rules: list[str] = []
    at: dict[str, int] = {}
    rows: list[list[int | None]] = []

    for segment in segments:
        kind = segment.kind.value
        if kind not in kinds:
            kinds.append(kind)
        rule = segment.rule
        if rule and rule not in at:
            at[rule] = len(rules)
            rules.append(rule)
        rows.append(
            [
                segment.out.length,
                segment.src.start,
                segment.src.end,
                kinds.index(kind),
                at[rule] if rule else None,
            ]
        )

    return {
        "segment_fields": list(SEGMENT_FIELDS),
        "kinds": kinds,
        "rules": rules,
        "segments": rows,
    }


def unpacked(body: dict[str, Any], key: str) -> tuple[Segment, ...]:
    """The segments of a map, in either shape it may have been written in.

    `key` is only for the error messages, and the error messages are the point:
    a map this cannot read is refused by name rather than resolved against a
    guess.
    """
    raw = body.get("segments") or []
    if not raw:
        return ()
    if isinstance(raw[0], dict):
        return tuple(_from_object(entry, key) for entry in raw)

    fields = body.get("segment_fields")
    if fields != list(SEGMENT_FIELDS):
        raise ContractError(
            f"the map for {key} lays its segments out as {fields!r}, and this reads "
            f"{list(SEGMENT_FIELDS)!r}. Refusing rather than resolving an offset "
            f"against a guessed column order."
        )
    kinds = body.get("kinds") or []
    rules = body.get("rules") or []

    found: list[Segment] = []
    at = 0
    for row in raw:
        try:
            length, source_start, source_end, kind_at, rule_at = row
            kind = Kind(kinds[int(kind_at)])
            rule = None if rule_at is None else str(rules[int(rule_at)])
            found.append(
                Segment(
                    out=Span(at, at + int(length)),
                    src=Span(int(source_start), int(source_end)),
                    kind=kind,
                    rule=rule,
                )
            )
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise ContractError(
                f"the map for {key} holds a segment this cannot read: {error}"
            ) from error
        at += int(length)
    return tuple(found)


def _from_object(entry: Any, key: str) -> Segment:
    """A segment written before the rows: one object with its names on it."""
    try:
        out = entry["out"]
        src = entry["src"]
        kind = Kind(entry["kind"])
    except (KeyError, TypeError, ValueError) as error:
        raise ContractError(
            f"the map for {key} holds a segment this cannot read: {error}"
        ) from error
    return Segment(
        out=Span(int(out[0]), int(out[1])),
        src=Span(int(src[0]), int(src[1])),
        kind=kind,
        rule=entry.get("rule"),
    )
