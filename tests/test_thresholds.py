"""Every constant that gates behaviour, classified, with nowhere to hide.

A number in this codebase is one of three things and only the third is a
liability:

```text
**bound**         exceeded, it refuses or degrades, loudly and visibly
**measured**      derived from data, by a named script
**threshold**     changes what the output *is*, chosen by hand
```

A threshold is fine on the corpus it was written against and unknown on every
other one. After a release the library meets documents nobody has seen, and the
question is not whether the value is right but whether the **answer is
delicate** — a threshold on a plateau survives contact with the world and one on
a cliff was fitted, whether or not anybody meant to fit it.

So this file is a register. Adding a module-level numeric constant to `src/`
without an entry here turns the build red, and each entry has to say which of
the three it is and where the evidence is. That is the part that keeps working
after everybody who chose the numbers has forgotten them.

`tools/sensitivity.py` produces the sweeps the `threshold` entries cite.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "musubi"


@dataclass(frozen=True, slots=True)
class Constant:
    """One number, what kind it is, and what backs it."""

    module: str
    name: str
    kind: str
    basis: str


#: Classified by hand, because the classification is the judgement. `kind` is
#: `bound`, `measured` or `threshold`; `basis` says where the evidence is or,
#: for a bound, what happens when it is passed.
REGISTER: tuple[Constant, ...] = (
    Constant(
        "application/export.py",
        "ROW_GROUP",
        "bound",
        "documents held before a Parquet row group is flushed. Past it the writer "
        "writes and drops; the rows a reader gets back are the same at any value, "
        "and only the peak memory (7.4 MB at 1,000 on 2,000 generated notes, "
        "docs/measurements.md) moves with it.",
    ),
    Constant(
        "domain/alignment.py",
        "MINIMUM_RUN",
        "threshold",
        "tools/sensitivity.py --only alignment: identical output from 1 to 80, "
        "collapsing only past the length of a paragraph. A broad plateau, so 12 is "
        "not load-bearing.",
    ),
    Constant(
        "domain/alignment.py",
        "WINDOW",
        "bound",
        "past it a run is reported as transformed: true, and less precise. The "
        "sweep shows it biting below about 1 kB, which is why the default is 64 kB "
        "and why `answer_width` is published beside coverage.",
    ),
    Constant(
        "infrastructure/converters/pdf.py",
        "MAXIMUM_STREAM_BYTES",
        "bound",
        "refuses with `stream_too_large`. Without it a few hundred bytes of "
        "compressed zeroes end the process, which is not fail-closed but absent.",
    ),
    Constant(
        "infrastructure/converters/pdf.py",
        "WORD_GAP",
        "threshold",
        "tools/sensitivity.py --only kerning: a cliff. -179 reads `thetent` and "
        "-180 reads `the tent`, and real fonts put a word space from under 200 to "
        "about 330 thousandths. So it is a setting (`pdf-word-gap`) rather than a "
        "constant, and `pdfium@1` removes the question by reading the font.",
    ),
    Constant(
        "infrastructure/decoding.py",
        "CONFIDENT",
        "threshold",
        "below it a detection is reported and not acted on. Every miss in "
        "tools/encoding_detection.py reported 100% coherence, so this cannot "
        "separate a right reading from a wrong one -- it only excludes a detector "
        "that recognised nothing. Filed as #82.",
    ),
    Constant(
        "infrastructure/screeners/entropy.py",
        "MINIMUM_RUN",
        "threshold",
        "opt-in tier only (ADR-0017), whose published precision is 21.1%. The tier "
        "carries its own measurement in `EntropyScreener.MEASURED`.",
    ),
    Constant(
        "infrastructure/screeners/entropy.py",
        "BASE64_BITS",
        "threshold",
        "the same opt-in tier as MINIMUM_RUN above (ADR-0017), and covered by the "
        "same published 21.1% precision in `EntropyScreener.MEASURED`.",
    ),
    Constant(
        "infrastructure/screeners/entropy.py",
        "HEX_BITS",
        "threshold",
        "the same opt-in tier as MINIMUM_RUN above (ADR-0017), and covered by the "
        "same published 21.1% precision in `EntropyScreener.MEASURED`.",
    ),
    Constant(
        "infrastructure/sources/filesystem.py",
        "MAXIMUM_BYTES",
        "bound",
        "a larger file is skipped with a reason, and the cap is printed in every "
        "report's `cap:` lines rather than being silent.",
    ),
    Constant(
        "infrastructure/sources/notion.py",
        "MAXIMUM_DEPTH",
        "bound",
        "an archive nested deeper is skipped as `too_deep`. An archive that "
        "contains itself is a thing a downloaded file can be.",
    ),
    Constant(
        "infrastructure/sources/notion.py",
        "MAXIMUM_ENTRY_BYTES",
        "bound",
        "refuses rather than trusting the size the archive declares.",
    ),
    Constant(
        "infrastructure/sources/notion.py",
        "NESTED_BUDGET",
        "bound",
        "past it the run degrades to re-inflating: correct, and slow, with a bound "
        "somebody chose rather than none. tools/scaling.py --only archive.",
    ),
)

BY_MODULE = {(entry.module, entry.name): entry for entry in REGISTER}

#: Names that are data rather than dials -- a version string, a table of bytes,
#: an index. Listed so that the sweep below stays about numbers that decide
#: something.
NOT_A_DIAL = frozenset({"VERSION"})


def _module_constants(path: Path) -> list[str]:
    """Module-level names bound to a plain number."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in tree.body:
        targets = [node.target] if isinstance(node, ast.AnnAssign) else getattr(node, "targets", [])
        value = getattr(node, "value", None)
        # `64 * 1024` is a BinOp and `-180.0` a UnaryOp; both are numbers, and
        # the first version of this missed the second, so a threshold added as a
        # negative literal would have walked straight past the register.
        if value is None or not _is_numeric(value):
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                found.append(target.id)
    return found


def _is_numeric(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, int | float) and not isinstance(node.value, bool)
    if isinstance(node, ast.BinOp):
        return _is_numeric(node.left) and _is_numeric(node.right)
    if isinstance(node, ast.UnaryOp):
        return _is_numeric(node.operand)
    return False


def _modules() -> list[Path]:
    found = sorted(SOURCE.rglob("*.py"))
    assert found, "no modules found; this whole file would be checking nothing"
    return found


def test_every_numeric_constant_in_the_source_is_registered() -> None:
    """The guard that keeps this file honest after everybody has moved on.

    A new constant is a new decision, and one that arrives unclassified is
    exactly the kind nobody revisits -- it was obviously right on the day, and
    the day is the only corpus it was ever checked against.
    """
    unregistered: list[str] = []
    for module in _modules():
        relative = module.relative_to(SOURCE).as_posix()
        for name in _module_constants(module):
            if name in NOT_A_DIAL or (relative, name) in BY_MODULE:
                continue
            unregistered.append(f"{relative}:{name}")

    assert not unregistered, (
        f"{unregistered} gate behaviour and are not in tests/test_thresholds.py. "
        f"Classify each as a bound, a measurement or a threshold, and say what "
        f"backs it. A threshold nobody swept is a number fitted to one corpus."
    )


def test_the_register_names_no_constant_that_has_gone() -> None:
    """The other direction. An entry for a deleted constant is a claim about
    code that is not there, and it makes the register look more thorough than
    it is."""
    stale: list[str] = []
    for entry in REGISTER:
        module = SOURCE / entry.module
        if not module.is_file() or entry.name not in _module_constants(module):
            stale.append(f"{entry.module}:{entry.name}")
    assert not stale, f"{stale} are registered and no longer exist"


@pytest.mark.parametrize("entry", REGISTER, ids=lambda e: f"{e.module}:{e.name}")
def test_every_entry_says_what_kind_it_is_and_what_backs_it(entry: Constant) -> None:
    assert entry.kind in {"bound", "measured", "threshold"}, entry
    assert len(entry.basis) > 40, f"{entry.name} has no real basis written down"


@pytest.mark.parametrize(
    "entry", [e for e in REGISTER if e.kind == "threshold"], ids=lambda e: e.name
)
def test_every_threshold_cites_a_sweep_a_measurement_or_a_filed_issue(entry: Constant) -> None:
    """A threshold is the kind that has to answer for itself.

    Three acceptable answers: a sweep showing it is on a plateau, a published
    measurement of the tier it belongs to, or an issue saying it is known to be
    unresolved. Silence is not one of them.
    """
    assert re.search(r"tools/\w+\.py|ADR-\d{4}|#\d+|MEASURED", entry.basis), (
        f"{entry.module}:{entry.name} is a threshold whose basis cites nothing. "
        f"Sweep it with tools/sensitivity.py, or file it."
    )


def test_the_kerning_cut_is_gone_rather_than_registered() -> None:
    """The one this audit removed instead of classifying.

    `pdf_text@1` inserted a space when a `TJ` kerning value was at least -180
    thousandths of an em. The sweep found a **cliff**: -179 reads `thetent` and
    -180 reads `the tent`, and real fonts put a word space anywhere from under
    200 to about 330 -- so documents land on both sides of it and there is no
    value that is right for all of them.

    Word spacing is a property of the font, which this converter does not read.
    So the number moved out of the code and into a setting, with `pdfium@1`
    named as the answer for anybody who does not want to choose one.
    """
    body = (SOURCE / "infrastructure" / "converters" / "pdf.py").read_text(encoding="utf-8")
    assert "<= -180" not in body, "the kerning cut is back as a literal in the comparison"
    assert "kerning: float" in body, "the value is no longer a parameter"

    from musubi.config import OPTIONS

    assert any(option.name == "pdf-word-gap" for option in OPTIONS), (
        "the threshold left the code and did not arrive in the settings, which "
        "would make it less reachable than before rather than more"
    )
