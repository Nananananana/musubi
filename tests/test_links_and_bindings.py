"""Two checks that only fail where two halves meet.

Both come from the family: the link resolution from `tsumugi` via `akashi`, and
the identifier-to-schema binding from `akashi`, whose statement of it is the
clearest — a document declares *I am this contract*, the schema describes
something, and **nothing looks at both**, so every other test passes while the
two disagree. Each sees its own half.

The second check is deliberately musubi's own rule rather than a copy of
`akashi`'s. `akashi` warned that its version only asks whether the two name the
same *version*, that every project binds them differently, and that copying its
shape would pass vacuously elsewhere. musubi binds an identifier to a filename
through `musubi.schemas.CONTRACTS`, and each schema states the identifier it
describes as a `pattern` — so what is checked here is that those two agree, which
is a sentence about musubi and not about `akashi`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from musubi.schemas import CONTRACTS, load, schemas

ROOT = Path(__file__).resolve().parent.parent

#: `[text](target)`. Bare autolinks and reference definitions are not used here.
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _markdown() -> list[Path]:
    found = sorted(
        p
        for p in ROOT.rglob("*.md")
        if not {".venv", ".git", "node_modules", ".hypothesis"} & set(p.parts)
    )
    assert found, "no markdown found; this test is measuring nothing"
    return found


def _local_links(doc: Path) -> list[str]:
    out = []
    for href in LINK.findall(doc.read_text(encoding="utf-8")):
        if href.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = href.split("#", 1)[0]
        if target:
            out.append(target)
    return out


# -- every local link resolves ----------------------------------------------


@pytest.mark.parametrize("doc", _markdown(), ids=lambda p: str(p.relative_to(ROOT)))
def test_every_local_link_resolves(doc: Path) -> None:
    """Resolved, not pattern-matched, which is the whole difference.

    ADR-0023 recorded a gap it could not close: the signpost at `schemas/` is a
    redirect, and a redirect rots — the test there catches a schema being added
    without the signpost mentioning it, and would not catch the target directory
    moving. **This catches that**, because it asks the filesystem whether the
    target is there rather than asking whether the string looks right.

    Measured: renaming `src/musubi/schemas/` breaks five links, including the
    signpost's own link to the directory.
    """
    missing = [href for href in _local_links(doc) if not (doc.parent / href).resolve().exists()]
    assert not missing, f"{doc.relative_to(ROOT)} links to {missing}, which do not exist"


def test_the_links_are_worth_checking() -> None:
    """A per-file test passes for a file with no links at all, and 34 of those
    read exactly like 34 files whose links resolve."""
    total = sum(len(_local_links(doc)) for doc in _markdown())
    assert total > 50, f"only {total} local links found; the check above is nearly empty"


# -- the identifier and the schema describe the same thing -------------------


@pytest.mark.parametrize("contract", sorted(CONTRACTS))
def test_a_schema_says_it_is_about_the_contract_it_is_reached_by(contract: str) -> None:
    """The half-meets-half check. `CONTRACTS` maps an identifier to a file; the
    file states the identifier it describes. Nothing else looks at both.

    Rename one side and every other test still passes: the conformance tests
    validate real output against whatever file they were handed, and the
    documents carry whatever identifier the code writes. They agree with
    themselves.
    """
    pattern = load(contract)["properties"]["contract"]["pattern"]
    assert re.match(pattern, contract), (
        f"{contract} is mapped to {CONTRACTS[contract]}, whose `contract` pattern "
        f"{pattern!r} does not accept it. One side was renamed and the other was not."
    )
    assert re.match(pattern, f"{contract}-draft"), (
        f"{CONTRACTS[contract]} does not accept the -draft form of {contract}. The "
        f"suffix is what says the freeze has not happened, and documents carry it."
    )


def test_no_two_contracts_share_a_schema() -> None:
    names = list(CONTRACTS.values())
    assert len(names) == len(set(names)), f"two identifiers point at one file: {names}"


def test_every_schema_shipped_is_reachable_by_an_identifier() -> None:
    """A schema in the package that nothing maps to is a published file no
    consumer can find from a document it is holding."""
    shipped = {p.name for p in schemas().iterdir() if p.name.endswith(".json")}
    assert shipped == set(CONTRACTS.values()), (
        f"the package ships {sorted(shipped)} and `CONTRACTS` names {sorted(CONTRACTS.values())}"
    )


def test_a_document_musubi_writes_declares_a_contract_its_schema_accepts(
    tmp_path: Path,
) -> None:
    """The two halves, met over real output rather than over the mapping.

    A real sync writes the identifier; the schema reached by that identifier
    states what it accepts. This is the only place both are read at once, and it
    reads a file that landed rather than a document a test assembled.
    """
    import contextlib
    import io

    from musubi.interfaces.cli.main import main

    root, into = tmp_path / "vault", tmp_path / "synced"
    root.mkdir(parents=True)
    (root / "a.md").write_text("# a\n", encoding="utf-8", newline="\n")
    with contextlib.redirect_stdout(io.StringIO()):
        main(["sync", str(root), "--into", str(into)])

    written = json.loads((into / "manifest.json").read_text(encoding="utf-8"))
    declared = written["contract"]
    pattern = load("musubi.sync-manifest/1")["properties"]["contract"]["pattern"]
    assert re.match(pattern, declared), (
        f"musubi writes contract {declared!r} and the schema reached by "
        f"'musubi.sync-manifest/1' accepts {pattern!r}"
    )

    trace = json.loads(next((into / "traces").rglob("*.json")).read_text(encoding="utf-8"))
    pattern = load("musubi.trace-map/1")["properties"]["contract"]["pattern"]
    assert re.match(pattern, trace["contract"]), (
        f"musubi writes contract {trace['contract']!r} and the schema reached by "
        f"'musubi.trace-map/1' accepts {pattern!r}"
    )
