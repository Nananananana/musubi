"""Sources: the formats musubi reads, and what each one calls a unit.

Every source declares how it derives a key ([ADR-0006]) and the declaration
reaches the manifest, so a reader can see which sources have the weak `path`
form without having to know the implementation.
"""

from __future__ import annotations

from .filesystem import (
    MACHINERY,
    MAXIMUM_BYTES,
    MEDIA_TYPES,
    FilesystemSource,
    ObsidianSource,
)
from .notion import NotionSource

__all__ = [
    "MACHINERY",
    "MAXIMUM_BYTES",
    "MEDIA_TYPES",
    "FilesystemSource",
    "NotionSource",
    "ObsidianSource",
]
