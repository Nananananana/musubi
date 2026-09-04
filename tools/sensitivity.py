"""How much does the output move when a threshold does?

A constant in this codebase is one of three things, and only the third is a
problem:

```text
**a bound**        exceeded, it refuses or degrades, loudly. 64 MB, 4 levels deep
**measured**      derived from data, with the script that derived it
**a threshold**   a number that changes what the output *is*, chosen by hand
```

The third kind is fine on the corpus it was written against and is a liability
on every other one, because nobody knows whether it sits on a plateau or on a
cliff. A release meets documents nobody has seen.

So this sweeps each of them and reports what moves. A threshold on a **plateau**
— where a wide range of values gives the same answer — is a threshold that will
survive contact with other people's files. One on a **cliff** is a number that
was fitted, whether or not anybody meant to fit it.

    uv run python tools/sensitivity.py
    uv run python tools/sensitivity.py --only alignment

What this cannot do is tell you the right value. It can only tell you whether
the question is delicate, which is the thing nobody finds out until a bug
report.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from musubi.domain.alignment import align
from musubi.domain.trace import Kind
from musubi.infrastructure.converters import known_converters
from musubi.ports.converter import Converted

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

PARAGRAPHS = [
    "A tent that weighs 2.4kg is a tent you carry all day, and the difference "
    "shows up in the last hour rather than the first.",
    "The stove is the part people get wrong. A remote canister freezes and a "
    "liquid-fuel stove does not, which matters exactly once.",
    "Boots matter more than the pack, because a blister ends a walk and a heavy "
    "pack only slows it down.",
]

PAGE = (
    "<!doctype html><html><body>"
    "<nav>" + "<a href='/x'>Home</a>" * 30 + "</nav>"
    "<article>" + "".join(f"<p>{p}</p>\n" for p in PARAGRAPHS) + "</article>"
    "<footer>Copyright 2026 Example Corporation. All rights reserved.</footer>"
    "</body></html>"
)
EXTRACTED = "\n".join(PARAGRAPHS) + "\n"


def _row(label: str, coverage: float, verbatim: int, removals: int) -> str:
    return f"  {label:>10}  {coverage:>8.1%}  {verbatim:>8}  {removals:>9}"


def alignment_minimum_run() -> None:
    """`MINIMUM_RUN`: how long a run has to be before it is looked for.

    Below it a run is not searched at all, so it can never be verbatim. Above
    it, a chance match anchors the scan to the wrong place and costs every line
    after it. The comment says *about two words*; nothing measured it.
    """
    print(f"  {'value':>10}  {'coverage':>8}  {'verbatim':>8}  {'removals':>9}")
    for value in (1, 4, 8, 12, 16, 24, 40, 80, 200):
        aligned = align(PAGE, EXTRACTED, minimum_run=value)
        kinds = [segment.kind for segment in aligned.trace.segments]
        print(
            _row(
                str(value),
                aligned.trace.traceable_coverage,
                kinds.count(Kind.VERBATIM),
                kinds.count(Kind.REMOVAL),
            )
        )
    print()
    print("  A plateau here means the answer does not depend on the number.")


def alignment_window() -> None:
    """`WINDOW`: how far ahead of the last match a run is looked for.

    This one is a bound rather than a threshold -- past it a run is reported as
    transformed, which is true and less precise. Swept anyway, because a bound
    that bites at ordinary sizes is a threshold wearing a bound's clothes.
    """
    print(f"  {'value':>10}  {'coverage':>8}  {'verbatim':>8}  {'removals':>9}")
    for value in (64, 256, 1024, 4096, 16384, 65536):
        aligned = align(PAGE, EXTRACTED, window=value)
        kinds = [segment.kind for segment in aligned.trace.segments]
        print(
            _row(
                str(value),
                aligned.trace.traceable_coverage,
                kinds.count(Kind.VERBATIM),
                kinds.count(Kind.REMOVAL),
            )
        )
    print()
    print(f"  The source here is {len(PAGE):,} characters; the default is 65,536.")


def pdf_kerning() -> None:
    """The number that decides whether two words get a space between them.

    A `TJ` array carries kerning adjustments in thousandths of an em, and
    `pdf_text@1` inserts a space when one is at least this negative. Word
    spacing is a property of the **font**, which this converter does not read,
    so the number is a guess about every font at once.
    """
    from pdf_fixtures import _stream

    def spaced(kerning: int) -> bytes:
        body = b"BT /F1 12 Tf 72 720 Td [(the)" + str(kerning).encode() + b"(tent)] TJ ET"
        return (
            b"%PDF-1.4\n1 0 obj\n<< /Type /Page /Contents 2 0 R >>\nendobj\n"
            b"2 0 obj\n" + _stream(body) + b"\nendobj\n"
        )

    converter = next(c for c in known_converters() if c.name == "pdf_text@1")
    print(f"  {'kerning':>10}  {'reads as':<24}  what a reader would call it")
    for kerning in (-100, -150, -179, -180, -200, -250, -330, -500):
        result = converter.convert(spaced(kerning), "application/pdf")
        text = result.text.strip() if isinstance(result, Converted) else "(refused)"
        joined = "two words" if " " in text else "**one word**"
        print(f"  {kerning:>10}  {text!r:<24}  {joined}")
    print()
    print("  A word space is 250-330 thousandths for most fonts and under 200 for")
    print("  some condensed ones, so the cut sits inside the range real files use.")


MEASUREMENTS: dict[str, tuple[str, Callable[[], None]]] = {
    "alignment": ("alignment: MINIMUM_RUN", alignment_minimum_run),
    "window": ("alignment: WINDOW", alignment_window),
    "kerning": ("pdf_text@1: the kerning cut", pdf_kerning),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=sorted(MEASUREMENTS), default=None)
    arguments = parser.parse_args()

    for name in [arguments.only] if arguments.only else list(MEASUREMENTS):
        heading, measure = MEASUREMENTS[name]
        print(f"\n== {heading} ==\n", flush=True)
        measure()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
