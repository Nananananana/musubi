"""What each PDF converter can read at all, before anything about quality.

The HTML half of [ADR-0028] is about **precision** -- one extractor rejects
boilerplate another keeps. The PDF half is not. It is about **reach**, and reach
is a cruder and more decisive thing: a converter that reports `no_pages` on a
whole class of file has no precision to discuss.

`pdf_text@1` finds objects by scanning for `N 0 obj`. That is every object in a
PDF 1.4. In a PDF 1.5 the catalogue, the page tree and the pages are packed into
a **compressed object stream** and reached through a cross-reference stream, so
none of them is written that way and the scan finds nothing. Following the
cross-reference stream needs a parser for nested dictionaries, which [ADR-0001]
declined to write -- correctly, at the time, when the alternative was a
dependency.

The fixtures come from `tests/pdf_fixtures.py` rather than being copied here.
Two fixtures that are supposed to be the same file and quietly are not is a
worse problem than one unusual import.

    uv run python tools/pdf_coverage.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from musubi.infrastructure.converters import known_converters
from musubi.ports.converter import Converted

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from pdf_fixtures import FIRST_LINE, SECOND_LINE, classic, modern, scanned

#: What each file is, and what the right answer for it is.
CASES: dict[str, tuple[bytes, str]] = {
    "PDF 1.4, objects at the top level": (classic(), "reads both lines"),
    "PDF 1.5, page in an object stream": (modern(), "reads both lines"),
    "PDF 1.4, a page with no text layer": (scanned(), "refuses: no_text_layer"),
}


def outcome(result: Converted | object) -> str:
    if not isinstance(result, Converted):
        return f"refused: {getattr(result, 'reason', '?')}"
    found = sum(line in result.text for line in (FIRST_LINE, SECOND_LINE))
    return f"reads {found}/2 lines"


def main() -> int:
    converters = [c for c in known_converters() if "application/pdf" in c.media_types]
    if not converters:
        print("no PDF converter is registered", file=sys.stderr)
        return 2

    width = max(len(name) for name in CASES)
    print(f"{'':{width}}  " + "  ".join(f"{c.name:>22}" for c in converters))
    print("-" * (width + 2 + 24 * len(converters)))
    for label, (document, _) in CASES.items():
        answers = [outcome(c.convert(document, "application/pdf")) for c in converters]
        print(f"{label:{width}}  " + "  ".join(f"{a:>22}" for a in answers))

    print()
    print("The middle row is the case. It is not an unusual file: a compressed object")
    print("stream is what a PDF 1.5 is, and PDF 1.5 is what almost every current")
    print("producer writes. `no_pages` there is correct and useless.")
    print()
    print("The last row is the one that must NOT change. A page with no text layer is a")
    print("refusal with a reason, in both -- OCR belongs to a program the owner runs")
    print("before musubi (ADR-0007), and a better reader does not make that untrue.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
