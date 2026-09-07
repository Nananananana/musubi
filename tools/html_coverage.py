"""What each HTML converter keeps, what it drops, and what it can still trace.

[ADR-0028] takes a dependency in exchange for extraction quality, and this is
the exchange rate. Two things are measured, and they pull in opposite
directions:

```text
**boilerplate rejected**  of the navigation, footers and cookie banners
                          planted in the fixture, how much is gone
**traceable coverage**    of the emitted text, how much resolves to a place
                          in the source
```

The second is the one that could have made this a bad trade. musubi's own
`html@1` builds its map *while* converting, so its coverage is high by
construction; `trafilatura@1` is handed a string with no offsets and the map is
**recovered by alignment**. If recovery lost most of it, the better text would
have cost the guarantee, and the honest answer would have been not to take the
dependency.

The fixture is generated here rather than collected. That is a real limitation
and it is stated in the output: synthetic HTML has the right *shape* -- a nav,
an article, a footer, entities, inline markup -- and none of the mess of a real
page. What it can answer is the relative question, which is the one being asked.

    uv run python tools/html_coverage.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from html_fixtures import BOILERPLATE, CONTENT, page
from musubi.infrastructure.converters import known_converters
from musubi.ports.converter import Converted


def main() -> int:
    document = page()
    candidates = [c for c in known_converters() if "text/html" in c.media_types]

    print(
        f"one generated page, {len(document):,} bytes, "
        f"{len(BOILERPLATE)} planted boilerplate strings, {len(CONTENT)} planted paragraphs"
    )
    print()
    header = (
        f"{'converter':16s} {'text':>8s} {'boilerplate':>12s} {'content':>9s} {'traceable':>10s}"
    )
    print(header)
    print("-" * len(header))

    for converter in sorted(candidates, key=lambda c: c.name):
        result = converter.convert(document, "text/html")
        if not isinstance(result, Converted):
            print(f"{converter.name:16s} refused: {result.reason}")
            continue
        rejected = sum(1 for phrase in BOILERPLATE if phrase not in result.text)
        kept = sum(1 for phrase in CONTENT if phrase in result.text)
        print(
            f"{converter.name:16s} {len(result.text):8,d} "
            f"{rejected:>7d}/{len(BOILERPLATE):<4d} {kept:>4d}/{len(CONTENT):<4d} "
            f"{result.trace.traceable_coverage:>9.1%}"
        )

    print()
    print("boilerplate: planted strings that are gone.  content: planted paragraphs that survived.")
    print("traceable:   share of emitted characters resolving to a place in the source.")
    print()
    print("The fixture is generated, not collected: it has the shape of a real page and none")
    print("of the mess. What it answers is the relative question.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
