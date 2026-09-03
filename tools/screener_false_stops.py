"""How often the screener stops a run on a document that holds no secret.

[ADR-0008] a hit stops the whole sync. So the screener's precision is not a
quality score, it is the difference between a gate and an obstacle course, and
the population that matters is **the one a real note actually contains**: a
pasted image, a checksum listing, a lockfile. All three are long runs of the
same alphabet a credential is made of.

This generates those populations rather than collecting them, which is a real
limitation and is stated in `docs/measurements.md`: a synthetic blob has the
right alphabet and the wrong everything else. What it can measure is the thing
the alphabet decides -- how often four characters of prefix turn up inside a
longer run by chance.

    uv run python tools/screener_false_stops.py
    uv run python tools/screener_false_stops.py --without-boundary

`--without-boundary` runs **the scan as it was before [ADR-0026]**, reimplemented
here rather than kept in the library, so the number the ADR states can be
re-derived without checking out an old commit.
"""

from __future__ import annotations

import argparse
import random
import string
from collections.abc import Callable

from musubi.domain.screening import Signature
from musubi.domain.span import Span
from musubi.infrastructure.screeners.signatures import SIGNATURES

#: The alphabets a note's own noise is written in.
POPULATIONS: dict[str, str] = {
    "base64": string.ascii_letters + string.digits + "+/",
    "base64url": string.ascii_letters + string.digits + "-_",
    "hex-lower": "0123456789abcdef",
    "hex-upper": "0123456789ABCDEF",
}


def without_boundary(signature: Signature, text: str) -> list[Span]:
    """`Signature.find` as it stood before [ADR-0026]: no left boundary."""
    found: list[Span] = []
    at = 0
    while (start := text.find(signature.prefix, at)) != -1:
        end = start + len(signature.prefix)
        while end < len(text) and text[end] in signature.alphabet:
            end += 1
        if end - start - len(signature.prefix) >= signature.minimum:
            found.append(Span(start, end))
            at = end
        else:
            at = start + 1
    return found


def measure(
    find: Callable[[Signature, str], list[Span]], trials: int, size: int, seed: int
) -> dict[str, tuple[int, dict[str, int]]]:
    result: dict[str, tuple[int, dict[str, int]]] = {}
    for name, alphabet in POPULATIONS.items():
        rng = random.Random(seed)
        stopped = 0
        by_rule: dict[str, int] = {}
        for _ in range(trials):
            blob = "".join(rng.choice(alphabet) for _ in range(size))
            hit = False
            for signature in SIGNATURES:
                count = len(find(signature, blob))
                if count:
                    hit = True
                    by_rule[signature.id] = by_rule.get(signature.id, 0) + count
            stopped += hit
        result[name] = (stopped, by_rule)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=500)
    parser.add_argument("--size", type=int, default=100_000, help="characters per blob")
    parser.add_argument("--seed", type=int, default=20260904)
    parser.add_argument(
        "--without-boundary", action="store_true", help="the pre-ADR-0026 scan, for the baseline"
    )
    args = parser.parse_args()

    find = (
        without_boundary
        if args.without_boundary
        else (lambda signature, text: signature.find(text))
    )
    print(
        f"{args.trials} blobs of {args.size:,} characters per population, seed {args.seed}, "
        f"{len(SIGNATURES)} signatures, "
        f"{'without' if args.without_boundary else 'with'} the left boundary"
    )
    for name, (stopped, by_rule) in measure(find, args.trials, args.size, args.seed).items():
        share = stopped / args.trials
        print(
            f"  {name:10s} {stopped:4d}/{args.trials}  {share:6.2%} of documents would stop a run"
        )
        for rule, count in sorted(by_rule.items(), key=lambda kv: -kv[1]):
            print(f"      {rule:28s} {count:6d} matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
