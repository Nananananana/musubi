"""A cleansing rule, and the record of what it took.

[ADR-0009] Rules are data, and every one names its evidence -- a rule with no
stated reason for existing cannot be reviewed by anyone who was not there when
it was written, and every rule outlives that person.

[ADR-0016] A rule matches a parsed parameter name by ``exact`` or ``prefix``.
There is no regular expression: Python's engine backtracks, has no timeout, and
would be running patterns a user may edit over documents nobody vetted, inside
an unattended loop. The reference catalogue turned out to be a list of literals
and prefixes, so restricting the language removes the failure class instead of
mitigating it.

[ADR-0005] Every firing produces a :class:`RemovalRecord` carrying the rule, the
span and a hash -- **never the value**. The removed thing is usually the
sensitive thing, and a manifest that quoted it would re-publish, into a file
people commit, exactly what the run was for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .hashing import content_hash
from .span import Span

__all__ = ["Match", "RemovalRecord", "Rule", "Ruleset"]

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Match(Enum):
    """How a rule recognises a name. Both are linear and neither backtracks."""

    EXACT = "exact"
    PREFIX = "prefix"


@dataclass(frozen=True, slots=True)
class Rule:
    """One thing musubi removes, and the reason it is allowed to."""

    id: str
    kind: str
    match: Match
    value: str
    #: Why this is noise. Required. A URL, a citation, a sentence -- but
    #: something, because this is the field a security reviewer reads.
    evidence: str
    #: When it was last reviewed, ``YYYY-MM-DD``. Required, so that staleness is
    #: measurable rather than assumed.
    since: str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("a rule with no id cannot be reported when it fires")
        if not self.kind:
            raise ValueError(f"rule {self.id!r} has no kind")
        if not self.value:
            raise ValueError(f"rule {self.id!r} matches nothing")
        if not self.evidence:
            raise ValueError(
                f"rule {self.id!r} states no evidence; a rule nobody can review is a "
                f"rule that will be broken for good reasons of somebody else's"
            )
        if not _DATE.match(self.since):
            raise ValueError(f"rule {self.id!r} has a since of {self.since!r}, not YYYY-MM-DD")

    def matches(self, name: str) -> bool:
        if self.match is Match.EXACT:
            return name == self.value
        return name.startswith(self.value)

    @property
    def _precedence(self) -> tuple[int, int, str]:
        """Exact beats prefix; a longer prefix beats a shorter one; then the id.

        Total and deterministic. Two rules can both match, and which one is
        reported has to be the same on every run rather than a property of the
        order they were declared in ([ADR-0003]).
        """
        return (0 if self.match is Match.EXACT else 1, -len(self.value), self.id)


@dataclass(frozen=True, slots=True)
class Ruleset:
    """A named, versioned pack of rules. The unit that gets vendored."""

    id: str
    version: str
    rules: tuple[Rule, ...]

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for rule in self.rules:
            if rule.id in seen:
                raise ValueError(f"rule id {rule.id!r} appears twice in ruleset {self.id!r}")
            seen.add(rule.id)

    def matching(self, name: str) -> Rule | None:
        """The rule that claims this parameter name, or ``None``."""
        candidates = [rule for rule in self.rules if rule.matches(name)]
        if not candidates:
            return None
        return min(candidates, key=lambda rule: rule._precedence)

    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted({rule.kind for rule in self.rules}))


@dataclass(frozen=True, slots=True)
class RemovalRecord:
    """One firing: what was taken, by which rule, from where.

    Carries a hash of the removed text and never the text
    ([ADR-0005](../../docs/adr/0005-say-what-was-removed-and-by-which-rule.md)).
    The hash still does the work that matters -- two runs can be shown to have
    removed the same thing, a rule can be shown to have fired on the same value
    forty times, and a suspected false positive can be confirmed by hashing the
    candidate.
    """

    rule: str
    kind: str
    #: Where it was, in the text the rule ran over.
    span: Span
    removed_characters: int
    removed_hash: str

    @classmethod
    def of(cls, rule: Rule, span: Span, removed: str) -> RemovalRecord:
        return cls(
            rule=rule.id,
            kind=rule.kind,
            span=span,
            removed_characters=len(removed),
            removed_hash=content_hash(removed),
        )
