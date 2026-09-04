"""What a credential looks like, and what musubi says when it finds one.

[ADR-0008] A hit stops the whole run. Nothing is promoted, including the units
that already converted cleanly, because a skipped unit is a hole in a corpus
nobody reads the log of and a stopped run is a person looking at the problem
before the data moves.

[ADR-0017] The default tier is **signatures**: a prefix, an alphabet and a
minimum length. Not entropy -- entropy-only detection scores 21.1% precision on
the CredData benchmark, and under a stop-the-run policy four false stops in five
is not a gate but an obstacle course. Meanwhile the industry has spent five
years adopting identifiable token prefixes precisely so that scanners work, and
``AKIA`` followed by sixteen uppercase alphanumerics is an AWS access key id and
very little else.

No regular expressions, for [ADR-0016]'s reason: this runs unattended over
arbitrary documents, and a linear scan cannot be made to hang.

A :class:`Finding` carries where and what kind, and **never the value**. The
whole point of stopping is that the secret does not travel; putting it in the
error message would send it to a log file instead of a corpus.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .hashing import content_hash
from .span import Span

__all__ = [
    "BASE32",
    "BASE62",
    "BASE64URL",
    "HEX",
    "Finding",
    "Signature",
    "shannon_entropy",
]

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: The alphabets vendors actually use after a prefix.
BASE62 = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
BASE64URL = BASE62 | frozenset("-_")
BASE32 = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") | frozenset("0123456789")
HEX = frozenset("0123456789abcdefABCDEF")


@dataclass(frozen=True, slots=True)
class Signature:
    """One credential format: a prefix, what may follow it, and how much.

    ``minimum=0`` means the prefix *is* the finding -- a PEM header names itself
    and has no fixed body.
    """

    id: str
    #: What to call it when the run stops. "a GitHub personal access token" is
    #: an actionable message; "signature 14 matched" is not.
    label: str
    prefix: str
    alphabet: frozenset[str]
    minimum: int
    #: Why this shape is a credential. Required, as it is for a cleansing rule
    #: (ADR-0009): a vendor's token format is a fact somebody has to be able to
    #: check.
    evidence: str
    #: When it was last reviewed, ``YYYY-MM-DD``. Signature lists go stale
    #: faster than tracking-parameter lists, because vendors rotate formats.
    since: str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("a signature with no id cannot be reported when it fires")
        if not self.label:
            raise ValueError(f"signature {self.id!r} has no label to put in the message")
        if not self.prefix:
            raise ValueError(
                f"signature {self.id!r} has no prefix; a signature without one is an "
                f"entropy filter wearing a signature's clothes"
            )
        if self.minimum < 0:
            raise ValueError(f"signature {self.id!r} has a negative minimum")
        if self.minimum and not self.alphabet:
            raise ValueError(f"signature {self.id!r} expects a body but allows no characters")
        if not self.evidence:
            raise ValueError(f"signature {self.id!r} states no evidence")
        if not _DATE.match(self.since):
            raise ValueError(f"signature {self.id!r} has a since of {self.since!r}, not YYYY-MM-DD")

    def find(self, text: str) -> list[Span]:
        """Every place this signature matches, left to right.

        A linear scan: find the prefix, then count how far the alphabet runs.
        Nothing here can backtrack.

        **The bound, stated rather than gestured at.** Every iteration leaves
        `at` strictly greater than it found it: the boundary and minimum-length
        branches set `at = start + 1` where `start >= at`, and the matching
        branch sets `at = end` where `end >= start + len(prefix)` and the prefix
        is **never empty** -- `__post_init__` refuses one. So the loop runs at
        most `len(text) + 1` times, and the whole scan is linear.

        That the prefix cannot be empty is therefore not a nicety about
        signature quality. It is what buys termination, and
        `tests/test_the_scan_cannot_run_away.py` checks both halves: the
        validation that guarantees it, and a worst-case input in a subprocess
        with a deadline, so that losing the property fails a test instead of
        hanging one.

        **The prefix has to start something.** A match whose preceding character
        the body alphabet would have accepted is not a token that begins with
        the prefix -- it is a longer run of the same alphabet with the prefix
        somewhere in the middle of it, which is what a base64 blob is. See
        [ADR-0026] for the measurement; under [ADR-0008] a hit stops the run, so
        this is the difference between a gate and an obstacle.

        A signature with no body -- a PEM header names itself -- has no alphabet
        to test against and is unaffected.
        """
        found: list[Span] = []
        at = 0
        while (start := text.find(self.prefix, at)) != -1:
            if start and text[start - 1] in self.alphabet:
                at = start + 1
                continue
            end = start + len(self.prefix)
            while end < len(text) and text[end] in self.alphabet:
                end += 1
            body = end - start - len(self.prefix)
            if body >= self.minimum:
                found.append(Span(start, end))
                at = end
            else:
                at = start + 1
        return found


@dataclass(frozen=True, slots=True)
class Finding:
    """Something that looks like a credential, and where it is.

    Carries a hash and never the value. The run stops so that the secret does
    not travel; an error message quoting it would send it to a log file instead
    of to a corpus, which is not an improvement.
    """

    rule: str
    label: str
    span: Span
    matched_characters: int
    matched_hash: str

    @classmethod
    def of(cls, rule: str, label: str, span: Span, matched: str) -> Finding:
        return cls(
            rule=rule,
            label=label,
            span=span,
            matched_characters=len(matched),
            matched_hash=content_hash(matched),
        )

    def describe(self, unit_key: str) -> str:
        """A line somebody can act on, naming nothing they should not see."""
        return f"{self.label} in {unit_key} at {self.span} ({self.rule})"


def shannon_entropy(text: str) -> float:
    """Bits per character. Zero for an empty string.

    Used by the opt-in entropy tier only (ADR-0017). It is here rather than in
    the tier because it is a pure function of a string and the domain is where
    those live -- and because publishing it makes the tier's threshold
    something a reader can check rather than take on trust.
    """
    if not text:
        return 0.0
    total = len(text)
    return -sum((count / total) * math.log2(count / total) for count in Counter(text).values())
