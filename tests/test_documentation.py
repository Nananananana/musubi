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
    """ADR-0002: the contract ships with the package. ADR-0023: where from.

    The files sit inside the package tree, so hatchling ships them without a
    ``force-include`` and ``importlib.resources`` finds them in an editable
    install too. That last part is the point: while they lived at the repository
    root the loading instruction in `docs/contracts.md` was true for a consumer
    who ran ``pip install musubi`` and false for everybody working on musubi,
    and nothing here ran the sentence it published.

    The "the schemas ship inside the wheel" CI job still builds a wheel and opens
    it, which is the different question of whether they are in the artefact.
    """
    packaged = ROOT / "src" / "musubi" / "schemas"
    assert list(packaged.glob("*.json")), "both contracts have schemas since #24"
    assert not list((ROOT / "schemas").glob("*.json")), (
        "the schemas moved into the package (ADR-0023). The root directory is a "
        "signpost; a .json back at the root is a second copy of a contract, which is "
        "two contracts as soon as somebody edits one."
    )
    signpost = (ROOT / "schemas" / "README.md").read_text(encoding="utf-8")
    for name in packaged.glob("*.json"):
        assert name.name in signpost, f"the signpost does not mention {name.name}"

    # The guarantee that replaced the `force-include` block: the sentence
    # `docs/contracts.md` publishes resolves here, in this checkout, without a
    # wheel being built. That is what the old configuration could not offer.
    from musubi.schemas import CONTRACTS, path_to, schemas

    assert schemas().is_dir(), (
        "`importlib.resources.files('musubi') / 'schemas'` does not resolve. This is "
        "the sentence docs/contracts.md tells consumers to use, and it was false in an "
        "editable install for as long as the schemas lived at the repository root."
    )
    for contract in CONTRACTS:
        assert path_to(contract).is_file(), f"{contract} has no schema where it says"
        assert path_to(f"{contract}-draft").is_file(), "a consumer reads the draft suffix"


@pytest.mark.parametrize("word", FORBIDDEN_IN_OUTPUT)
def test_the_forbidden_vocabulary_is_absent_from_the_readme(word: str) -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert word not in readme, (
        f"README.md contains {word!r}. musubi removes what its rules name and stops on "
        f"what its screener recognises, and neither is a guarantee about what is left. "
        f"See docs/adr/0008-a-credential-stops-the-run.md"
    )


# -- what exists, checked against what exists -------------------------------

WHAT_EXISTS = ROOT / "docs" / "README.md"


def _section(heading: str) -> str:
    """The text between one bold heading in `docs/README.md` and the next."""
    body = WHAT_EXISTS.read_text(encoding="utf-8")
    start = body.index(heading) + len(heading)
    rest = body[start:]
    end = rest.find("\n**")
    return rest if end == -1 else rest[:end]


def _commands(section: str) -> set[str]:
    return set(re.findall(r"`musubi ([a-z]+)`", section))


def _exists(command: str) -> bool:
    """Whether the CLI knows this command, asked the way a user would."""
    from musubi.interfaces.cli import main

    try:
        main([command, "--help"])
    except SystemExit as exit_code:
        return exit_code.code == 0
    return True


def _built_commands() -> set[str]:
    """The commands `docs/README.md` claims are built.

    Asserted non-empty for the same reason `_adr_files` and `_refusals` are, and
    against a failure the others cannot have. Those two lose their subject when
    a *file* disappears, which is loud in other ways. This one loses its subject
    when the section survives and merely stops matching -- rewrite ```musubi
    plan`` as **musubi plan** and the checks below collect zero cases and pass.

    Measured: doing exactly that took this file from 60 collected tests to 58,
    green both times. The guard did not break. It stopped being handed anything
    to guard, which is the failure iriguchi found by renaming a CI job and
    watching seven guards die in one line.
    """
    found = _commands(_section("**Built,"))
    assert found, (
        "docs/README.md's Built section names no `musubi <command>`; the check "
        "below would run zero times and pass. Either the section stopped using "
        "backticks or the heading moved."
    )
    return found


@pytest.mark.parametrize("command", sorted(_built_commands()))
def test_a_command_the_docs_call_built_is_built(command: str) -> None:
    assert _exists(command), (
        f"docs/README.md lists `musubi {command}` as built and the CLI does not have it. "
        f"This project's whole claim is that its documents and its code do not diverge."
    )


# Deliberately not asserted non-empty, unlike the Built section above: this one
# is *supposed* to reach zero. When the last unbuilt thing is built the section
# empties, and a guard that failed then would be demanding the project stay
# unfinished. An empty collection here is a legitimate answer; there it is a
# missing question.
@pytest.mark.parametrize("command", sorted(_commands(_section("**Not built,"))))
def test_a_command_the_docs_call_missing_is_missing(command: str) -> None:
    assert not _exists(command), (
        f"`musubi {command}` now exists and docs/README.md still lists it as not built. "
        f"Update 'What exists' in the same pull request as the code it describes."
    )


def test_the_counts_in_the_docs_are_the_counts_in_the_code() -> None:
    """The same discipline as asserting a schema's enums against the code's:
    two statements of one fact, kept one by a test."""
    from musubi.infrastructure.rules import CORE
    from musubi.infrastructure.screeners.signatures import SIGNATURES

    body = WHAT_EXISTS.read_text(encoding="utf-8")
    assert f"{len(CORE.rules)} rules" in body, f"the pack has {len(CORE.rules)} rules"
    assert f"{len(SIGNATURES)} credential signatures" in body, f"there are {len(SIGNATURES)}"

    listed = len(_adr_files())
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"{_spelled(listed)} decisions" in readme, f"there are {listed} ADRs"


_NUMBERS = {
    12: "Twelve",
    13: "Thirteen",
    14: "Fourteen",
    15: "Fifteen",
    16: "Sixteen",
    17: "Seventeen",
    18: "Eighteen",
    19: "Nineteen",
    20: "Twenty",
    21: "Twenty-one",
    22: "Twenty-two",
    23: "Twenty-three",
    24: "Twenty-four",
}


def _spelled(count: int) -> str:
    assert count in _NUMBERS, f"add {count} to _NUMBERS"
    return _NUMBERS[count]


def test_no_current_state_document_says_nothing_is_built() -> None:
    """It was true for four days. A README saying it over a working command
    costs more credibility than any other kind of staleness, which is why this
    is a test and not a note."""
    for name in ("README.md", "AGENTS.md", "docs/README.md"):
        body = (ROOT / name).read_text(encoding="utf-8")
        assert "Nothing is built" not in body, f"{name} still says nothing is built"
