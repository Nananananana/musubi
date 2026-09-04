"""The tool that asks whether the tests would notice, checked the same way.

`tools/mutate.py` edits a module in place and restores it. Two properties have
to hold or it is worse than nothing:

- **mutation `n` is the same mutation on every run**, or a report naming
  `line 115: + -> -` points at whatever happened to be counted 115th today;
- **the file comes back**, whatever happened in between.

The findings it produced are in the docstring there. The one worth repeating is
that a score is a statement about the *test selection* and not about the code:
`domain/screening.py` scored 74% against its own test file and **100% against
the suite**, unchanged.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from mutate import Applier, Planner, targets

SAMPLE = '''
def f(a, b):
    """A docstring with the number 3 in it, which must not be mutated."""
    if a < b and b > 0:
        return a + 1
    return not b
'''


def _plan(source: str) -> list[str]:
    planner = Planner()
    planner.visit(ast.parse(source))
    return [m.what for m in planner.plan]


def test_the_plan_is_the_same_every_time() -> None:
    """Ordinals are the report's only handle on which change was made."""
    assert _plan(SAMPLE) == _plan(SAMPLE)
    assert _plan(SAMPLE), "nothing to mutate; every assertion below would be vacuous"


def test_applying_mutation_n_changes_exactly_one_thing() -> None:
    """A transformer that applied two would report one and measure the other."""
    original = ast.unparse(ast.parse(SAMPLE))
    seen = set()
    for index in range(len(_plan(SAMPLE))):
        applier = Applier(index)
        mutated = ast.unparse(ast.fix_missing_locations(applier.visit(ast.parse(SAMPLE))))
        assert applier.applied, f"mutation {index} was planned and not applied"
        assert mutated != original, f"mutation {index} changed nothing"
        seen.add(mutated)
    assert len(seen) == len(_plan(SAMPLE)), "two ordinals produce the same mutant"


def test_a_string_is_never_mutated() -> None:
    """Every message in this codebase is a string. Mutating one produces a
    mutant killed by whichever test happens to assert on the wording, which
    measures the wording."""
    assert not any("docstring" in what for what in _plan(SAMPLE))


def test_the_number_in_a_docstring_is_left_alone() -> None:
    mutants = {
        ast.unparse(ast.fix_missing_locations(Applier(i).visit(ast.parse(SAMPLE))))
        for i in range(len(_plan(SAMPLE)))
    }
    assert all("number 3 in it" in mutant for mutant in mutants)


def test_a_package_directory_yields_its_modules_and_not_its_dunder_init() -> None:
    found = targets(Path("src/musubi/domain"))
    assert found, "no modules; a sweep over this would report 100% of nothing"
    assert all(path.name != "__init__.py" for path in found)


@pytest.mark.parametrize("expression", ["a < b", "a and b", "not a", "a + 1", "a == b"])
def test_the_operators_that_matter_here_are_all_covered(expression: str) -> None:
    """The operator list is short on purpose, and short lists silently lose
    entries. These are the mistakes a half-open range makes."""
    assert _plan(f"def f(a, b):\n    return {expression}\n")
