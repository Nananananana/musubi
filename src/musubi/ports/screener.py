"""Is there a credential in here?

The port [ADR-0008] hangs on. The default implementation is signatures only
([ADR-0017]); the optional `mamori` adapter is the upgrade, and it is the one
place in musubi allowed to know that `mamori` exists.

A screener is asked about text and answers with findings. It does not decide
what happens next: stopping the run is the application's job, because a screener
that could halt a pipeline would be a screener nobody could test.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ..domain.screening import Finding

__all__ = ["Screener"]


class Screener(Protocol):
    """Satisfied by anything that can look at text and report credentials."""

    #: Named in the manifest, so a reader knows which instrument was used and
    #: can go and look up what it is worth.
    name: str

    def screen(self, text: str) -> Sequence[Finding]:
        """Everything in this text that looks like a credential, in order."""
        ...
