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

from musubi.domain.reading_order import STRATEGIES
from musubi.infrastructure.converters import known_converters
from musubi.infrastructure.converters.pdf import STREAM, PdfConverter
from musubi.ports.converter import Converted
from pdf_fixtures import (
    COLUMNS_READ,
    OUT_OF_ORDER_READ,
    TABLE_READ,
    a_table,
    composite,
    out_of_order,
    scanned,
    two_columns,
)

PDF = "application/pdf"

#: Fixture, what a person reads, and what the fixture is about. ``None`` for an
#: answer means there is no correct text and the only correct behaviour is to
#: refuse.
CASES: tuple[tuple[str, bytes, str | None, str], ...] = (
    ("two columns", two_columns(), COLUMNS_READ, "laid out by baseline, read by column"),
    ("a table", a_table(), TABLE_READ, "written down columns, read across rows"),
    (
        "one line, out of order",
        out_of_order(),
        OUT_OF_ORDER_READ,
        "three runs on one baseline, shown middle-first",
    ),
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
    # The registry's converters, plus one `pdf_text@1` per geometric strategy.
    # Built here rather than registered, because a strategy is a setting and
    # the registry holds the default: measuring only what the registry has
    # would be measuring the setting being switched off ([ADR-0042]).
    from musubi.infrastructure.converters.external import PAGE_EXTRACTORS, PagedConverter

    readers = [c for c in known_converters() if PDF in getattr(c, "media_types", ())]
    for order in sorted(STRATEGIES):
        readers.append(PdfConverter(reading_order_name=order))
        readers += [
            PagedConverter(extractor, order)
            for extractor in PAGE_EXTRACTORS
            if extractor.load() is not None and extractor.place is not None
        ]
    if not readers:  # pragma: no cover - the registry always claims PDFs
        print("no converter claims application/pdf")
        return 1

    print("== reading order: is the text the document's text, in its order ==\n")
    print(f"  The default is {STREAM!r}; the rest are `pdf-reading-order` settings.\n")
    print(f"  {'fixture':24s} {'converter':20s} {'answer':>8s}  what it did")
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
                if read == answer:
                    verdict = "exact"
                elif ratio == 1.0:
                    # Every word in the right order and the lines drawn
                    # elsewhere. Worth separating from a reordering: it is a
                    # disagreement about what a line is, not about the text.
                    verdict = "the words in order, lines drawn differently"
                else:
                    verdict = f"{ratio:.0%} of the words, reordered"
                score = f"{ratio:6.2f}"
            print(f"  {label:24s} {reader.name:20s} {score:>8s}  {verdict}")
        print(f"  {'':24s} {about}")

    print("\nBuilt fixtures with stated answers, so these are answers and not impressions.")
    print("A ratio near 1 with 'reordered' is the failure worth knowing about: every")
    print("word present, the order wrong, and every offset still resolving.")
    print()
    print("Every answer above is reachable by some strategy, and a test asserts it.")
    print("Two of them were not: a fixture stating an answer nothing can produce is")
    print("a red that can never go green, so it never tells anybody (ADR-0042).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
