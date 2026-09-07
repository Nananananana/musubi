"""Why a file did not become a document, and whether the list of reasons is true.

`Skip.reason` and `Unconvertible.reason` are the same promise the error
catalogue makes one layer up, and `Unconvertible`'s own docstring makes it:

    ``reason`` is a stable token a reader can count and filter on --
    ``no_text_layer``, ``undecodable``

The manifest carries them, so they are part of a published contract. A consumer
counting them is doing the thing musubi told it to do.

**The contract named eight of twenty-two.** Nothing it named was fake, which is
the good half; the other fourteen are reasons a consumer can meet and has never
been told about — including `composite_font`, `no_text_layer` and
`no_main_content`, which are exactly the "every file skipped, and the only sign
is a count" case that `sora` came to musubi about.

So the population is derived from the code and the documents are held to it.
This is the same family as [ADR-0047] through [ADR-0050]: a list beside a thing
has no reason to change when the thing does, and this one lived in a schema
description, which is the last place anybody looks for drift.

## What this does not cover

A reason built at run time rather than written as a literal. There is none
today and this would not find one, which is worth saying rather than implying
the derivation is total.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "musubi"
CONTRACTS = ROOT / "docs" / "contracts.md"
MANIFEST_SCHEMA = PACKAGE / "schemas" / "musubi-sync-manifest-1.json"

#: Where a reason can be written. Four shapes, because a reason reaches a
#: manifest from a source's discovery, from the pipeline itself, and from any
#: converter's refusal.
_WRITTEN = (
    re.compile(r'Skipped\(\s*[^,]+,\s*"([a-z_]+)"'),
    re.compile(r'Skip\([^,]+,\s*[^,]+,\s*"([a-z_]+)"'),
    re.compile(r'Unconvertible\(\s*\n?\s*"([a-z_]+)"'),
    re.compile(r'reason="([a-z_]+)"'),
)


def reasons() -> dict[str, set[str]]:
    """Every reason the package can put in a manifest, and where it is written."""
    found: dict[str, set[str]] = {}
    for source in sorted(PACKAGE.rglob("*.py")):
        body = source.read_text(encoding="utf-8")
        where = source.relative_to(PACKAGE).as_posix()
        for pattern in _WRITTEN:
            for name in pattern.findall(body):
                found.setdefault(name, set()).add(where)
    return found


def documented() -> set[str]:
    """The reasons `docs/contracts.md` lists, from its own table."""
    body = CONTRACTS.read_text(encoding="utf-8")
    block = body[body.index("### Why a file did not become a document") :]
    block = block[: block.index("\n## ")] if "\n## " in block else block
    return set(re.findall(r"^\| `([a-z_]+)` \|", block, re.M))


def named_by_the_schema() -> set[str]:
    body = json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8"))
    said = body["$defs"]["skip"]["properties"]["reason"]["description"]
    return set(re.findall(r"`([a-z_]+)`", said))


# -- the population, before anything is asserted about it -------------------


def test_there_are_reasons_to_check() -> None:
    """A regex that stops matching leaves every test below comparing two empty
    sets and passing. Twenty-two is what it found when this was written; the
    bound is loose because the number is allowed to grow."""
    assert len(reasons()) >= 15, f"found only {sorted(reasons())}"


# -- the two documents that publish them ------------------------------------


@pytest.mark.parametrize("reason", sorted(reasons()), ids=lambda r: r)
def test_every_reason_a_manifest_can_carry_is_documented(reason: str) -> None:
    """`docs/contracts.md` is the page a consumer writes a reader against. A
    reason it does not list is one they meet and cannot name."""
    assert reason in documented(), (
        f"{reason!r} can reach a manifest (from {sorted(reasons()[reason])}) and "
        f"`docs/contracts.md` does not list it."
    )


def test_the_documents_name_no_reason_that_cannot_happen() -> None:
    """Backwards. A reason documented and never produced sends a consumer
    writing a branch that never runs -- and every one this named was real,
    which is why the list read as trustworthy while being a third complete."""
    invented = sorted((documented() | named_by_the_schema()) - set(reasons()))
    assert not invented, f"{invented} are published and nothing produces them"


def test_the_schema_points_at_the_list_rather_than_repeating_it() -> None:
    """It used to carry eight of them inline, which is a copy that drifts. The
    description now says where the whole list is, and a schema description is
    the last place anybody looks for drift."""
    body = json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8"))
    said = body["$defs"]["skip"]["properties"]["reason"]["description"]
    assert "docs/contracts.md" in said
    assert len(named_by_the_schema()) <= 4, (
        "the schema is listing reasons again; an example or two is fine and a "
        "copy of the list is a second list to keep in step"
    )


# -- and what each entry has to say -----------------------------------------


@pytest.mark.parametrize("reason", sorted(reasons()), ids=lambda r: r)
def test_every_documented_reason_says_what_to_do_about_it(reason: str) -> None:
    """A token with no sentence under it is a token a reader can count and not
    act on, and counting was never the point."""
    body = CONTRACTS.read_text(encoding="utf-8")
    (row,) = [line for line in body.splitlines() if line.startswith(f"| `{reason}` |")]
    _, where, what = (cell.strip() for cell in row.strip("|").split("|"))
    assert where in {"source", "pipeline", "converter"}, (
        f"{reason!r} says it comes from {where!r}, which is not a layer that produces one"
    )
    assert len(what) > 30, f"{reason!r} has no real sentence under it"
