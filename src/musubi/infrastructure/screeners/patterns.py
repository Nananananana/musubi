"""The default tier: credential formats their issuers made recognisable.

[ADR-0017]. A signature is a prefix, an alphabet and a minimum length, checked
by a linear scan. No regular expression, for [ADR-0016]'s reason: this runs
unattended over documents nobody vetted.
"""

from __future__ import annotations

from collections.abc import Sequence

from ...domain.screening import Finding, Signature
from .signatures import SIGNATURES, VERSION

__all__ = ["SignatureScreener"]


class SignatureScreener:
    """Satisfies :class:`~musubi.ports.screener.Screener`."""

    def __init__(self, signatures: Sequence[Signature] = SIGNATURES) -> None:
        self._signatures = tuple(signatures)
        self.name = f"signatures@{VERSION}"

    @property
    def signatures(self) -> tuple[Signature, ...]:
        return self._signatures

    def screen(self, text: str) -> Sequence[Finding]:
        findings: list[Finding] = []
        for signature in self._signatures:
            for span in signature.find(text):
                findings.append(Finding.of(signature.id, signature.label, span, span.slice(text)))
        # Ordered by where they are, then by rule id: two signatures can claim
        # the same place, and which is reported first must not depend on the
        # order the pack happened to be written in (ADR-0003).
        return sorted(findings, key=lambda f: (f.span.start, f.span.end, f.rule))
