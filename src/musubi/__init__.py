"""musubi -- local-first ingestion for generative AI.

Turn the exports and folders somebody already has -- an Obsidian vault, a Notion
zip, a Slack archive, a shelf of PDFs -- into clean, normalized documents that
can still point back at the byte they came from. No network, no service
credentials, no model.

    >>> import musubi
    >>> converted = musubi.convert("notes/gear.md")
    >>> converted.text[:20]
    '# ギア設計

テントは 2.4kg'
    >>> converted.where(11, 16)          # and this is the part nothing else does
    Where(span=Span(start=8, end=13), unit='characters', ...)

``musubi plan``, ``sync``, ``trace``, ``verify``, ``export`` and ``config``
work on the command line. ``docs/README.md`` is the list of what does and does
not exist and is the one to trust; ``docs/adr/`` holds the decisions behind it.
"""

from __future__ import annotations

__version__ = "0.1.0.dev0"

from .api import Document, Where, convert, media_type_of, sync
from .errors import (
    ContractError,
    ConversionError,
    CredentialFoundError,
    MusubiError,
    SourceError,
    TraceError,
)

__all__ = [
    "ContractError",
    "ConversionError",
    "CredentialFoundError",
    "Document",
    "MusubiError",
    "SourceError",
    "TraceError",
    "Where",
    "__version__",
    "convert",
    "media_type_of",
    "sync",
]
