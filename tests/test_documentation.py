"""The documentation rules, where they can be checked by machine.

``docs/README.md`` says the three kinds of document must never be mistaken for
one another, and that an ADR index that has drifted from the directory is a
defect. Both are cheap to assert and expensive to notice by eye, so they are
asserted.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ADR = ROOT / "docs" / "adr"

#: Claims musubi is not entitled to make, anywhere a reader will see them. The
#: screener is a roughly 70%-recall instrument (ADR-0008) and cleansing removes
#: what its rules name and nothing else (ADR-0009), so a sentence promising a
#: corpus free of secrets is not a marketing flourish -- it is a false statement
#: about a security property, and it is the one this project would most easily
#: drift into.
FORBIDDEN_IN_OUTPUT = (
    "secret-free",
    "fully anonymized",
    "fully anonymised",
    "guaranteed clean",
    "removes all tracking",
)


def _adr_files() -> list[Path]:
    found = sorted(p for p in ADR.glob("*.md") if p.name != "README.md")
    assert found, "no ADRs found; this test is measuring nothing"
    return found


def test_every_adr_is_listed_in_the_index() -> None:
    index = (ADR / "README.md").read_text(encoding="utf-8")
    for adr in _adr_files():
        assert adr.name in index, (
            f"{adr.name} exists but the ADR index does not list it. An index that has "
            f"drifted from the directory is how a decision stops being findable."
        )


def test_the_index_lists_no_adr_that_does_not_exist() -> None:
    index = (ADR / "README.md").read_text(encoding="utf-8")
    listed = set(re.findall(r"\((\d{4}-[a-z0-9-]+\.md)\)", index))
    present = {adr.name for adr in _adr_files()}
    assert listed == present, (
        f"the index lists {sorted(listed - present)} which do not exist, and omits "
        f"{sorted(present - listed)}."
    )


def test_adr_numbers_are_unique_and_contiguous() -> None:
    numbers = sorted(int(adr.name[:4]) for adr in _adr_files())
    assert numbers == list(range(1, len(numbers) + 1)), (
        f"ADR numbers are {numbers}; they should run from 1 with no gaps and no "
        f"duplicates. A superseded decision keeps its number and gains a successor."
    )


@pytest.mark.parametrize("adr", _adr_files(), ids=lambda p: p.name)
def test_every_adr_says_what_it_costs(adr: Path) -> None:
    """The section that is usually missing, and the reason these are worth writing."""
    text = adr.read_text(encoding="utf-8")
    assert "## What it costs" in text, (
        f"{adr.name} has no 'What it costs' section. A decision recorded without its "
        f"price is a decision the next reader cannot re-examine."
    )


@pytest.mark.parametrize("adr", _adr_files(), ids=lambda p: p.name)
def test_every_adr_declares_its_status(adr: Path) -> None:
    text = adr.read_text(encoding="utf-8")
    assert re.search(r"^\*\*Status:\*\* (accepted|proposed|superseded)", text, re.MULTILINE), (
        f"{adr.name} does not declare a status on its own second line."
    )


def test_the_design_proposal_says_it_is_a_proposal() -> None:
    """A proposal read as current state is how unbuilt work gets depended on."""
    design = (ROOT / "docs" / "proposals" / "0001-the-design.md").read_text(encoding="utf-8")
    assert "**Status: proposed.**" in design
    assert "Nothing in this document exists yet" in design


def test_there_is_no_architecture_document_yet() -> None:
    """ADR-style rule from ``AGENTS.md``: a current-state document before the code
    is fiction. When ``domain/`` has an architecture, this test is deleted in the
    same commit that describes it."""
    assert not (ROOT / "docs" / "architecture.md").exists(), (
        "docs/architecture.md exists. If there is now an architecture to describe, "
        "delete this test in the commit that describes it."
    )


def test_a_published_schema_is_packaged_with_the_wheel() -> None:
    """ADR-0002: the contract ships inside the wheel.

    The ``force-include`` block in ``pyproject.toml`` is commented out while
    ``schemas/`` is empty, because hatchling refuses to build against a
    force-include that resolves to nothing. This is what stops that comment
    from outliving its reason.
    """
    if not list((ROOT / "schemas").glob("*.json")):
        pytest.skip("no schema published yet; v0.2")

    pyproject = ROOT / "pyproject.toml"
    live = [
        line
        for line in pyproject.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    assert "[tool.hatch.build.targets.wheel.force-include]" in live, (
        "schemas/ now holds a published contract, so the force-include block in "
        "pyproject.toml must be uncommented. A consumer validating a manifest should not "
        "have to fetch a schema from the internet."
    )


@pytest.mark.parametrize("word", FORBIDDEN_IN_OUTPUT)
def test_the_forbidden_vocabulary_is_absent_from_the_readme(word: str) -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert word not in readme, (
        f"README.md contains {word!r}. musubi removes what its rules name and stops on "
        f"what its screener recognises, and neither is a guarantee about what is left. "
        f"See docs/adr/0008-a-credential-stops-the-run.md"
    )
