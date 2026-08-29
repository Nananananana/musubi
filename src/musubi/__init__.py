"""musubi -- local-first ingestion for generative AI.

Turn the exports and folders somebody already has -- an Obsidian vault, a Notion
zip, a Slack archive, a shelf of PDFs -- into clean, normalized documents that
can still point back at the byte they came from. No network, no service
credentials, no model.

Nothing is built yet. See ``docs/proposals/0001-the-design.md`` for the design
and ``docs/adr/`` for the decisions behind it.
"""

from __future__ import annotations

from .errors import (
    ContractError,
    ConversionError,
    CredentialFoundError,
    MusubiError,
    SourceError,
    TraceError,
)

__version__ = "0.1.0.dev0"

__all__ = [
    "ContractError",
    "ConversionError",
    "CredentialFoundError",
    "MusubiError",
    "SourceError",
    "TraceError",
    "__version__",
]
