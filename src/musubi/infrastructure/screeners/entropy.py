"""The opt-in tier, and the numbers that say why it is opt-in.

[ADR-0017]. On the public CredData benchmark, entropy-only detection scores
**21.1% precision and 70.4% recall**. Under [ADR-0008]'s stop-the-run policy
that is four false stops in five, which makes `--allow` reflexive inside a week
and leaves the gate protecting nothing.

So this is off by default, and the number travels with it: `describe()` is what
the CLI prints beside the flag, because somebody switching this on is choosing
to trade stopped runs for coverage and should be told the rate they are buying.

The thresholds are the long-standing ones -- 4.5 bits per character for base64,
3.0 for hex -- and they are a starting point rather than a measured optimum for
this corpus. musubi measures its own screener in v0.4.
"""

from __future__ import annotations

from collections.abc import Sequence

from ...domain.screening import BASE64URL, HEX, Finding, shannon_entropy
from ...domain.span import Span

__all__ = ["EntropyScreener"]

#: Shorter than this and a high-entropy run is a word, a hash prefix or an id.
MINIMUM_RUN = 20

BASE64_BITS = 4.5
HEX_BITS = 3.0


class EntropyScreener:
    """Satisfies :class:`~musubi.ports.screener.Screener`. Off by default."""

    name = "entropy@1"

    #: Printed wherever this tier is switched on. A measurement that stays in
    #: the documentation is a measurement nobody reads at the moment it matters.
    MEASURED = (
        "entropy-only detection scores 21.1% precision and 70.4% recall on the "
        "CredData benchmark: roughly four stops in five will be a base64 fixture, "
        "a checksum table or a minified bundle"
    )

    def screen(self, text: str) -> Sequence[Finding]:
        findings: list[Finding] = []
        for span in _runs(text, HEX):
            run = span.slice(text)
            if shannon_entropy(run) >= HEX_BITS:
                findings.append(Finding.of("entropy.hex", "a high-entropy hex run", span, run))
        for span in _runs(text, BASE64URL):
            run = span.slice(text)
            if any(f.span == span for f in findings):
                continue
            if shannon_entropy(run) >= BASE64_BITS:
                findings.append(Finding.of("entropy.base64", "a high-entropy run", span, run))
        return sorted(findings, key=lambda f: (f.span.start, f.span.end, f.rule))

    def describe(self) -> str:
        return f"{self.name}: {self.MEASURED}"


def _runs(text: str, alphabet: frozenset[str]) -> list[Span]:
    """Maximal runs of the alphabet, long enough to be worth measuring."""
    found: list[Span] = []
    start: int | None = None
    for index, character in enumerate(text):
        if character in alphabet:
            if start is None:
                start = index
        elif start is not None:
            if index - start >= MINIMUM_RUN:
                found.append(Span(start, index))
            start = None
    if start is not None and len(text) - start >= MINIMUM_RUN:
        found.append(Span(start, len(text)))
    return found
