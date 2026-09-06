"""Did each converter read the document, on fixtures whose answer is known.

Everything else musubi measures answers *did it read at all*. `traceable_coverage`
says an offset resolves; `answer_width` says how tightly; the conformance suite
says the map is structurally honest. None of them looks at whether the text is
the document's text in the document's order (#85).

These fixtures state their correct reading, so this compares output against an
answer. It is the only measurement that can tell `pdf_text@1` from `pdfium@1` on
anything other than *did it open*, and the only one that can go red when a
converter starts producing worse text while its coverage stays flat -- which is
what #84's floors need to be set against.

    uv run python tools/reading_order.py

Built fixtures, not collected ones. A PDF whose right answer nobody can state
measures nothing, and this repository has the machinery to write one byte by
byte.
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from musubi.infrastructure.converters import known_converters
from musubi.ports.converter import Converted
from pdf_fixtures import (
    COLUMNS_READ,
    TABLE_READ,
    VERTICAL_READ,
    a_table,
    composite,
    scanned,
    two_columns,
    vertical,
)

PDF = "application/pdf"

#: Fixture, what a person reads, and what the fixture is about. ``None`` for an
#: answer means there is no correct text and the only correct behaviour is to
#: refuse.
CASES: tuple[tuple[str, bytes, str | None, str], ...] = (
    ("two columns", two_columns(), COLUMNS_READ, "laid out by baseline, read by column"),
    ("a table", a_table(), TABLE_READ, "written down columns, read across rows"),
    ("right-to-left columns", vertical(), VERTICAL_READ, "the geometry of 縦書き"),
    ("a composite font", composite(), None, "glyph indices; no reader without the CMap"),
    ("a scan", scanned(), None, "no text layer; a refusal must stay one"),
)


def agreement(answer: str, read: str) -> float:
    """How much of the answer this reading is, between 0 and 1.

    A ratio rather than a pass or a fail, because these fail by *degree*: a
    converter that interleaves two columns has every word and the wrong order,
    and one that drops a column has neither. `difflib`'s ratio separates them
    and nothing simpler does.
    """
    return difflib.SequenceMatcher(None, answer.split(), read.split()).ratio()


def main() -> int:
    readers = [c for c in known_converters() if PDF in getattr(c, "media_types", ())]
    if not readers:  # pragma: no cover - the registry always claims PDFs
        print("no converter claims application/pdf")
        return 1

    print("== reading order: is the text the document's text, in its order ==\n")
    print(f"  {'fixture':24s} {'converter':14s} {'answer':>8s}  what it did")
    for label, made, answer, about in CASES:
        for reader in readers:
            got = reader.convert(made, PDF)
            read = got.text.strip() if isinstance(got, Converted) else None

            if answer is None:
                verdict = "refused" if read is None else "READ IT"
                score = "  --  "
            elif read is None:
                verdict = f"refused: {got.reason}"  # type: ignore[union-attr]
                score = " 0.00 "
            else:
                ratio = agreement(answer, read)
                verdict = "exact" if read == answer else f"{ratio:.0%} of the words, reordered"
                score = f"{ratio:6.2f}"
            print(f"  {label:24s} {reader.name:14s} {score:>8s}  {verdict}")
        print(f"  {'':24s} {about}")

    print("\nBuilt fixtures with stated answers, so these are answers and not impressions.")
    print("A ratio near 1 with 'reordered' is the failure worth knowing about: every")
    print("word present, the order wrong, and every offset still resolving.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
