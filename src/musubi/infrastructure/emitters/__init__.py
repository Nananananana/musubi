"""Emitters: where a converted, cleansed unit ends up.

One implementation, on purpose ([ADR-0013]). musubi publishes documents, a
manifest and a trace map, and adaptation into a consumer's own records lives
with the consumer -- `kiseki` already ships `kiseki-notes` and `kiseki-ingest`
for exactly that, and `kiseki-notes` reads the folder this writes.
"""

from __future__ import annotations

from .documents import (
    DOCUMENTS,
    MANIFEST,
    STAGING,
    TRACE_CONTRACT,
    TRACES,
    DocumentEmitter,
)

__all__ = [
    "DOCUMENTS",
    "MANIFEST",
    "STAGING",
    "TRACES",
    "TRACE_CONTRACT",
    "DocumentEmitter",
]
