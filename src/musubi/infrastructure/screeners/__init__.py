"""Screeners, and which one you get without asking.

[ADR-0017] The default is signatures only. The entropy tier is a deliberate
choice with a published false-stop rate, not a default somebody inherits.
"""

from __future__ import annotations

from collections.abc import Sequence

from ...domain.screening import Finding
from .entropy import EntropyScreener
from .patterns import SignatureScreener
from .signatures import SIGNATURES, VERSION

__all__ = [
    "SIGNATURES",
    "VERSION",
    "CompositeScreener",
    "EntropyScreener",
    "SignatureScreener",
    "default_screener",
]


class CompositeScreener:
    """Every tier, in order, reported as one list."""

    def __init__(self, *screeners: object) -> None:
        if not screeners:
            # Fail closed: a screener that screens nothing would let a run
            # proceed unscreened while looking like it had been checked.
            raise ValueError("a composite with no tiers would screen nothing")
        self._tiers = screeners
        self.name = "+".join(getattr(tier, "name", "?") for tier in screeners)

    def screen(self, text: str) -> Sequence[Finding]:
        findings: list[Finding] = []
        for tier in self._tiers:
            findings.extend(tier.screen(text))  # type: ignore[attr-defined]
        return sorted(findings, key=lambda f: (f.span.start, f.span.end, f.rule))


def default_screener(*, entropy: bool = False) -> SignatureScreener | CompositeScreener:
    """What a sync gets when nobody has said otherwise.

    Signatures only. Pass ``entropy=True`` to add the opt-in tier, and print
    ``EntropyScreener.MEASURED`` where you do.
    """
    signatures = SignatureScreener()
    if not entropy:
        return signatures
    return CompositeScreener(signatures, EntropyScreener())
