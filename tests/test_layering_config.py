"""The commented-out layering contracts get switched on when their code lands.

``.importlinter`` carries three contracts that name packages which do not exist
yet. import-linter refuses a contract whose modules it cannot find, so they are
commented -- and a comment is exactly the kind of promise that gets forgotten.

This test is what stops that. The moment ``src/musubi/domain/`` exists, the
``domain-purity`` contract has to be uncommented or the build goes red.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".importlinter"
SRC = ROOT / "src" / "musubi"

#: Contract name -> the packages it needs in order to resolve. When every
#: package in the value exists, the contract must be live.
DEPENDS_ON: dict[str, tuple[str, ...]] = {
    # A `forbidden` contract has to resolve both sides, so these wait on every
    # package they name and not only the one they are about.
    "domain-purity": (
        "domain",
        "ports",
        "application",
        "infrastructure",
        "interfaces",
        "evaluation",
    ),
    "the-screener-is-optional": ("domain", "ports", "application", "evaluation", "interfaces"),
    "domain-no-io": ("domain",),
}


def _live_contracts(text: str) -> set[str]:
    """Contract names on a line that is not commented out."""
    return {
        match.group(1)
        for line in text.splitlines()
        if not line.lstrip().startswith("#")
        if (match := re.match(r"\[importlinter:contract:([a-z0-9-]+)\]", line.strip()))
    }


def _named_contracts(text: str) -> set[str]:
    """Every contract name in the file, commented or not."""
    return set(re.findall(r"\[importlinter:contract:([a-z0-9-]+)\]", text))


def test_every_deferred_contract_is_actually_in_the_config() -> None:
    named = _named_contracts(CONFIG.read_text(encoding="utf-8"))
    missing = sorted(set(DEPENDS_ON) - named)
    assert not missing, (
        f"{missing} are listed here as deferred but do not appear in .importlinter at "
        f"all. This test would then be guarding nothing."
    )


@pytest.mark.parametrize("contract", sorted(DEPENDS_ON), ids=sorted(DEPENDS_ON))
def test_a_deferred_contract_is_enabled_once_its_packages_exist(contract: str) -> None:
    needed = DEPENDS_ON[contract]
    present = [name for name in needed if (SRC / name).is_dir()]
    if len(present) < len(needed):
        pytest.skip(f"still waiting on {sorted(set(needed) - set(present))}")

    assert contract in _live_contracts(CONFIG.read_text(encoding="utf-8")), (
        f"src/musubi/{{{','.join(needed)}}}/ now exist, so the {contract!r} contract in "
        f".importlinter must be uncommented. It was deferred because import-linter "
        f"could not resolve it, and that reason has expired."
    )
