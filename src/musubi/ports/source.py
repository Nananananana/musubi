"""Where units come from, in two stages.

A source is asked twice: once for what is there, and once for the bytes of one
thing. The split is `kiseki-notes`' and it is worth copying -- *finding* the
notes opens nothing, so the account of what will be skipped and why can be
produced before a single private file has been read, and `musubi plan`
([ADR-0012]) has something to say without loading a corpus into memory.

**A source declares how it derives a key** ([ADR-0006]) and the declaration goes
in the manifest. `path` is the weak form: the key is where the file sits, so
moving a file looks like a delete plus an add. A reader can see which sources
have that weakness rather than having to know.

An implementer never imports this module. It only has to have the right shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

__all__ = ["Discovery", "Found", "Skipped", "Source"]


@dataclass(frozen=True, slots=True)
class Found:
    """Something that exists, before anybody has read a word of it."""

    #: The parts of its key, unnormalized. ``unit_key`` does the rest.
    key_parts: tuple[str, ...]
    media_type: str
    size_bytes: int
    #: How the source will find it again. Opaque above this layer: a path for a
    #: filesystem source, an entry name for an archive. Never parsed by anything
    #: except the source that produced it.
    origin: str


@dataclass(frozen=True, slots=True)
class Skipped:
    """Something that was seen and not read, and why.

    Every discarding path carries its reason to the end. A run that says
    "412 documents" and nothing else cannot be told apart from one that quietly
    excluded half the folder.
    """

    origin: str
    reason: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class Discovery:
    """What is there, and what will not be read."""

    found: tuple[Found, ...] = ()
    skipped: tuple[Skipped, ...] = ()
    #: Every cap that bounded this discovery, so that it appears in the
    #: manifest rather than being inferred from a shortfall.
    caps: tuple[str, ...] = field(default=())

    def summary(self) -> str:
        return f"{len(self.found)} to read, {len(self.skipped)} skipped"


class Source(Protocol):
    """Satisfied by anything that can list units and hand over their bytes."""

    #: Names this source in keys and in the manifest. One library may read a
    #: vault and a Notion export, and a unit's identity is (source_id, key).
    source_id: str
    #: What implementation, and which version of it: ``obsidian@1``.
    adapter: str
    #: How a key is derived, stated for the manifest ([ADR-0006]).
    key_derivation: str

    def discover(self) -> Discovery:
        """Everything here, without opening any of it."""
        ...

    def read(self, found: Found) -> bytes:
        """The bytes of one thing that ``discover`` reported."""
        ...
