"""musubi -- local-first ingestion for generative AI.

Turn the exports and folders somebody already has -- an Obsidian vault, a Notion
zip, a Slack archive, a shelf of PDFs -- into clean, normalized documents that
can still point back at the byte they came from. No network, no service
credentials, no model.

``musubi plan``, ``sync``, ``trace``, ``verify``, ``export`` and ``config``
work. ``docs/README.md`` is the list of what does and does not exist and is the
one to trust; ``docs/adr/`` holds the decisions behind it.
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
