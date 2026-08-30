"""The unit of sync: what musubi tracks, and how a re-read tells what changed.

[ADR-0006] A Slack export is one archive holding fifty thousand messages, and
re-exporting the same workspace produces different bytes for an almost identical
archive. A Notion export regenerates a UUID in every filename. File hashing
reports that everything changed, every time, for two of the three formats that
matter. So the unit musubi tracks is the **record**: identity is
``(source_id, unit_key)``, change is ``content_hash``, and neither is a function
of an archive's own bookkeeping.

[ADR-0014] The key is normalized to NFC and the content is not. macOS hands back
decomposed filenames and everything else hands back composed ones; a key derived
from the raw name makes the same vault into two corpora depending on which
machine read it. Normalizing the owner's *text*, on the other hand, would be an
unrequested rewrite of what they wrote -- so identifiers are normalized because
they are musubi's, and content is not because it is theirs.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .hashing import content_hash

__all__ = ["Change", "Unit", "compare", "unit_key"]

_SEPARATORS = ("/", "\\")


def unit_key(*parts: str) -> str:
    """Build a key from its parts: NFC, ``/``-joined, and refusing the rest.

    Parts rather than a path string, so that no separator has to be guessed and
    a key means the same thing on both sides of the platform divide. The caller
    supplies what its own filesystem or export format gave it, split.

    Refuses ``.``, ``..``, an embedded separator and an empty part. A key becomes
    an output filename ([ADR-0013]), so a key that can climb out of its own
    directory is a path traversal waiting for a corpus to be built somewhere
    writable -- checked once here rather than in each emitter, where it would
    eventually be forgotten in one.
    """
    if not parts:
        raise ValueError("a key needs at least one part")
    cleaned = []
    for part in parts:
        if not part:
            raise ValueError("a key part is never empty")
        if part in {".", ".."}:
            raise ValueError(f"a key part may not climb out of its own directory: {part!r}")
        if any(separator in part for separator in _SEPARATORS):
            raise ValueError(
                f"a key part may not contain a separator and forge structure: {part!r}. "
                f"Pass the parts, not the path."
            )
        # NFC and not NFKC. Compatibility normalization would turn ＵＲＬ into
        # URL and ① into 1, and the key names a file the owner has rather than
        # one musubi would have preferred.
        cleaned.append(unicodedata.normalize("NFC", part))
    return "/".join(cleaned)


@dataclass(frozen=True, slots=True)
class Unit:
    """One thing a source found, before anything has been done to it."""

    source_id: str
    unit_key: str
    content_hash: str
    media_type: str

    @classmethod
    def of(
        cls,
        source_id: str,
        key_parts: Sequence[str],
        content: bytes | str,
        media_type: str,
    ) -> Unit:
        """Build a unit, hashing the content exactly as it was read."""
        return cls(
            source_id=source_id,
            unit_key=unit_key(*key_parts),
            content_hash=content_hash(content),
            media_type=media_type,
        )

    @property
    def identity(self) -> tuple[str, str]:
        """What makes this the same thing across two exports."""
        return (self.source_id, self.unit_key)


@dataclass(frozen=True, slots=True)
class Change:
    """What a re-read found, against what was already held.

    Ordered by key throughout. An unordered iteration reaching an output is how
    two runs of the same input stop being the same run ([ADR-0003]).
    """

    added: tuple[Unit, ...]
    changed: tuple[Unit, ...]
    unchanged: tuple[Unit, ...]
    removed: tuple[Unit, ...]

    @property
    def is_empty(self) -> bool:
        """Nothing to do. Not the same as nothing found."""
        return not (self.added or self.changed or self.removed)

    def summary(self) -> str:
        return (
            f"{len(self.added)} new, {len(self.changed)} changed, "
            f"{len(self.unchanged)} unchanged, {len(self.removed)} gone"
        )


def compare(held: Mapping[str, Unit], found: Sequence[Unit]) -> Change:
    """Compare a re-read against what is already held, by key.

    ``held`` is keyed by ``unit_key`` -- one source's worth. A comparison mixing
    two sources would report every unit of one as added and every unit of the
    other as removed, which is a very confident wrong answer, so it is refused.
    """
    sources = {unit.source_id for unit in found} | {unit.source_id for unit in held.values()}
    if len(sources) > 1:
        raise ValueError(
            f"a comparison covers one source at a time, not {sorted(sources)}; "
            f"mixing them reports every unit of each as added and removed"
        )

    seen: dict[str, Unit] = {}
    for unit in found:
        if unit.unit_key in seen:
            # [ADR-0014]'s cost, made loud. On Linux two files can differ only
            # by normalization, and picking one would silently drop a document.
            raise ValueError(
                f"key {unit.unit_key!r} was found twice in one read; two units cannot "
                f"share an identity, and choosing between them would drop a document"
            )
        seen[unit.unit_key] = unit

    added, changed, unchanged = [], [], []
    for key in sorted(seen):
        unit = seen[key]
        previous = held.get(key)
        if previous is None:
            added.append(unit)
        elif previous.content_hash != unit.content_hash:
            changed.append(unit)
        else:
            unchanged.append(unit)

    removed = [held[key] for key in sorted(held) if key not in seen]
    return Change(
        added=tuple(added),
        changed=tuple(changed),
        unchanged=tuple(unchanged),
        removed=tuple(removed),
    )
