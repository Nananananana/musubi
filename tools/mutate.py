"""Change one operator, run the tests, and see whether anything notices.

A green suite says the tests pass. It does not say the tests would go red if the
code were wrong, and this repository has now found five populations that could
not (`docs/adr/0020`, the cp932 fixture, `#72`'s empty parameter sets). Each was
found by hand. This does it by machine: take the module apart, change one thing,
put it back, and ask.

**A survivor is a sentence about the tests, not about the code.** `<` became
`<=` and 894 tests still passed means one of three things, in descending order
of how often it is true:

1. the mutation is *equivalent* -- it cannot change behaviour, and no test could
   have caught it;
2. the branch is unreachable, or the value is never at the boundary in any
   fixture, which is a **population** problem;
3. nothing checks that property at all, which is a **coverage** problem.

Only the reader can tell which, and the report is written to be read rather than
scored. There is no threshold in CI, deliberately: a mutation score is a number
that goes up when you delete equivalent mutants from the operator list, and
[`mamori`'s ADR-0023] is about exactly that.

## Why this and not `mutmut`

`mutmut` 3 is the tool, and it refuses to run outside WSL on Windows, which is
where this repository is developed. A CI job for a tool nobody here can run
would be a check whose failures nobody could reproduce. This is 200 lines of
`ast`, it runs where the code is written, and its operator list is short on
purpose -- these are the mutations that correspond to the mistakes this codebase
actually makes: an off-by-one in a half-open range, a boundary that should have
been inclusive, an `and` that should have been an `or`.

## What it has found

`src/musubi/domain/screening.py`, 39 mutants, twice:

```text
against tests/test_screening.py    29/39 killed   74%
against the whole suite            39/39 killed  100%
```

**A mutation score is a statement about the test selection, not about the
code.** Nothing changed between those two runs but the argument to `--tests`.
The ten that survived the narrow run were the boundary arithmetic in
`Signature.find` and `frozen=True` on two dataclasses -- all killed by tests
living in other files, which is where they belong.

It also found something about itself, which is why `TIMEOUT` exists: mutating
the advance of `Signature.find`'s `while` loop produces code that does not
terminate. The first sweep sat spinning with no output and stopped on the fifth
module. `find`'s own docstring said *nothing here can backtrack*; that is true
of what is written and one character away from being false.

That is now closed from the other side. `find` states its bound -- at most
`len(text) + 1` iterations, because the prefix can never be empty -- and
`tests/test_the_scan_cannot_run_away.py` checks the validation that buys it and
runs the worst-case input in a subprocess with a deadline. **A hang has to be
made into a failure by somebody**; it will not become one on its own.

## Running it

    uv run python tools/mutate.py src/musubi/domain/span.py
    uv run python tools/mutate.py src/musubi/domain --tests tests/test_tiling.py

The module is **edited in place** and restored in a `finally`, which is the only
way to be sure the installed package is the mutated one. It refuses to start if
the target has uncommitted changes, so an interrupted run cannot cost anything
that was not already committed.
"""

from __future__ import annotations

import argparse
import ast
import copy
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path

#: Comparisons, which is where a half-open range goes wrong.
COMPARISONS: dict[type[ast.cmpop], list[type[ast.cmpop]]] = {
    ast.Lt: [ast.LtE, ast.Gt],
    ast.LtE: [ast.Lt, ast.GtE],
    ast.Gt: [ast.GtE, ast.Lt],
    ast.GtE: [ast.Gt, ast.LtE],
    ast.Eq: [ast.NotEq],
    ast.NotEq: [ast.Eq],
    ast.Is: [ast.IsNot],
    ast.IsNot: [ast.Is],
    ast.In: [ast.NotIn],
    ast.NotIn: [ast.In],
}

#: Arithmetic, which is where an offset goes wrong.
ARITHMETIC: dict[type[ast.operator], list[type[ast.operator]]] = {
    ast.Add: [ast.Sub],
    ast.Sub: [ast.Add],
    ast.Mult: [ast.FloorDiv],
    ast.Div: [ast.Mult],
    ast.FloorDiv: [ast.Mult],
}

BOOLEANS: dict[type[ast.boolop], list[type[ast.boolop]]] = {
    ast.And: [ast.Or],
    ast.Or: [ast.And],
}


@dataclass(frozen=True, slots=True)
class Mutation:
    """One change, and enough to say what it was in a report."""

    index: int
    line: int
    what: str

    def __str__(self) -> str:
        return f"line {self.line}: {self.what}"


class Planner(ast.NodeVisitor):
    """Numbers every place a mutation could go, without making any.

    Two passes rather than one so that mutation *n* is the same mutation on
    every run: the plan is built from the untouched tree, and applying one is a
    separate walk that stops when it reaches the ordinal it was given.
    """

    def __init__(self) -> None:
        self.plan: list[Mutation] = []

    def _add(self, line: int, what: str) -> None:
        self.plan.append(Mutation(len(self.plan), line, what))

    def visit_Compare(self, node: ast.Compare) -> None:
        for operator in node.ops:
            for replacement in COMPARISONS.get(type(operator), []):
                self._add(node.lineno, f"{_name(type(operator))} -> {_name(replacement)}")
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        for replacement in ARITHMETIC.get(type(node.op), []):
            self._add(node.lineno, f"{_name(type(node.op))} -> {_name(replacement)}")
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        for replacement in BOOLEANS.get(type(node.op), []):
            self._add(node.lineno, f"{_name(type(node.op))} -> {_name(replacement)}")
        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        if isinstance(node.op, ast.Not):
            self._add(node.lineno, "drop a `not`")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        # Strings are skipped: every message in this codebase is a string, and
        # mutating one produces a mutant killed by whichever test happens to
        # assert on the wording, which measures the wording.
        if isinstance(node.value, bool):
            self._add(node.lineno, f"{node.value} -> {not node.value}")
        elif isinstance(node.value, int):
            self._add(node.lineno, f"{node.value} -> {node.value + 1}")
        self.generic_visit(node)


class Applier(ast.NodeTransformer):
    """Applies exactly the mutation with the given ordinal, and no other."""

    def __init__(self, wanted: int) -> None:
        self.wanted = wanted
        self.at = 0
        self.applied = False

    def _take(self) -> bool:
        taken = self.at == self.wanted
        self.at += 1
        if taken:
            self.applied = True
        return taken

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        for position, operator in enumerate(node.ops):
            for replacement in COMPARISONS.get(type(operator), []):
                if self._take():
                    node.ops[position] = replacement()
        return self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        for replacement in ARITHMETIC.get(type(node.op), []):
            if self._take():
                node.op = replacement()
        return self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        for replacement in BOOLEANS.get(type(node.op), []):
            if self._take():
                node.op = replacement()
        return self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        if isinstance(node.op, ast.Not) and self._take():
            return self.generic_visit(node.operand)
        return self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, bool):
            if self._take():
                return ast.Constant(value=not node.value)
        elif isinstance(node.value, int) and self._take():
            return ast.Constant(value=node.value + 1)
        return node


def _name(operator: type[ast.AST]) -> str:
    return {
        "Lt": "<", "LtE": "<=", "Gt": ">", "GtE": ">=", "Eq": "==", "NotEq": "!=",
        "Is": "is", "IsNot": "is not", "In": "in", "NotIn": "not in",
        "Add": "+", "Sub": "-", "Mult": "*", "Div": "/", "FloorDiv": "//",
        "And": "and", "Or": "or",
    }.get(operator.__name__, operator.__name__)  # fmt: skip


def targets(where: Path) -> list[Path]:
    if where.is_file():
        return [where]
    return sorted(p for p in where.rglob("*.py") if p.name != "__init__.py")


def dirty(paths: list[Path]) -> list[Path]:
    """Which of these git considers modified. An interrupted run must be free."""
    changed = subprocess.run(
        ["git", "status", "--porcelain", "--", *[str(p) for p in paths]],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return [Path(line[3:].strip()) for line in changed.splitlines() if line.strip()]


#: How long one mutant's test run may take before it is called a hang.
#:
#: **Not optional.** A mutation of a `while` loop's advance produces code that
#: does not terminate, and the first run of this tool found two: `pytest` sat
#: spinning with no output and the whole sweep stopped on the fifth module. A
#: hang is also a *result* -- a mutant nothing killed because nothing finished
#: -- and reporting it as one is the only way it does not silently become an
#: overnight job that never ends.
#:
#: Ten times a clean run of the whole suite, which is about 16 seconds here.
TIMEOUT = 180.0


def survivors(module: Path, tests: str, limit: int | None) -> Iterator[tuple[Mutation, bool]]:
    """Every mutation of `module`, and whether the suite noticed."""
    # Bytes, not text. `write_text` translates a newline to the platform's on
    # the way out, so restoring a file read as text rewrites every line ending
    # on a machine whose checkout is CRLF -- the module comes back correct and
    # `git status` says the whole file changed.
    original = module.read_bytes()
    tree = ast.parse(original.decode("utf-8"))

    planner = Planner()
    planner.visit(tree)
    plan = planner.plan[:limit] if limit else planner.plan

    try:
        for mutation in plan:
            applier = Applier(mutation.index)
            mutated = ast.fix_missing_locations(applier.visit(copy.deepcopy(tree)))
            module.write_bytes(ast.unparse(mutated).encode("utf-8"))
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        tests,
                        "-x",
                        "-q",
                        "--no-header",
                        "-p",
                        "no:cacheprovider",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                yield replace(mutation, what=f"{mutation.what} [did not terminate]"), False
                continue
            yield mutation, result.returncode == 0
    finally:
        module.write_bytes(original)


def main() -> int:
    parser = argparse.ArgumentParser(description="Mutate a module and see what the tests notice.")
    parser.add_argument("target", type=Path, help="a .py file, or a package directory")
    parser.add_argument("--tests", default="tests", help="what to run against each mutant")
    parser.add_argument("--limit", type=int, default=None, help="stop after this many per module")
    args = parser.parse_args()

    modules = targets(args.target)
    if not modules:
        print(f"{args.target} holds nothing to mutate", file=sys.stderr)
        return 2
    unclean = dirty(modules)
    if unclean:
        print(
            "refusing to start: these have uncommitted changes, and this edits in place\n  "
            + "\n  ".join(str(p) for p in unclean),
            file=sys.stderr,
        )
        return 2

    started = time.monotonic()
    total = 0
    lived: list[tuple[Path, Mutation]] = []
    for module in modules:
        alive = 0
        count = 0
        for mutation, survived in survivors(module, args.tests, args.limit):
            count += 1
            if survived:
                alive += 1
                lived.append((module, mutation))
        total += count
        killed = count - alive
        share = f"{killed / count:.0%}" if count else "n/a"
        # Flushed, because this is a long run whose output is usually
        # redirected, and a buffered pipe reports nothing until it ends -- which
        # is exactly when a hang is indistinguishable from slow progress.
        print(f"{module.as_posix():48s} {killed:4d}/{count:<4d} killed  {share}", flush=True)

    print(f"\n{total} mutants in {time.monotonic() - started:.0f}s")
    if not lived:
        print("nothing survived")
        return 0

    print(
        f"\n{len(lived)} survived -- each is equivalent, a gap in the population, or a gap "
        f"in what is asserted:\n"
    )
    for module, mutation in lived:
        print(f"  {module.as_posix()}:{mutation.line}  {mutation.what}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
