"""The published contracts, loadable the way `docs/contracts.md` says to load them.

This module exists so that the instruction musubi gives consumers is one musubi
itself runs. `docs/contracts.md` tells a consumer to reach the schemas through
``importlib.resources.files("musubi") / "schemas"``; before ADR-0023 nothing here
did that, and the instruction was **false in an editable install** — the schemas
lived at the repository root and were copied into the wheel by a build-time
`force-include`, so they resolved for somebody who ran `pip install musubi` and
for nobody working on musubi.

A published instruction nobody runs is the shape this project keeps finding: the
CI job proved the path existed inside a built artefact, which is real coverage
for the documented audience and no coverage at all of the sentence.

Reading them is deliberately not a musubi feature. There is no validator here —
`jsonschema` is a dev dependency and ADR-0001 keeps the runtime at zero. This
hands over bytes and a path; whoever validates brings their own validator.
"""

from __future__ import annotations

import json
from importlib.resources import files
from importlib.resources.abc import Traversable
from typing import Any

__all__ = ["CONTRACTS", "load", "path_to", "schemas"]

#: Contract identifier (without the `-draft` suffix) to the file that defines it.
CONTRACTS: dict[str, str] = {
    "musubi.sync-manifest/1": "musubi-sync-manifest-1.json",
    "musubi.trace-map/1": "musubi-trace-map-1.json",
}


def schemas() -> Traversable:
    """The directory holding the contracts, wherever this musubi is installed."""
    return files("musubi") / "schemas"


def path_to(contract: str) -> Traversable:
    """The file defining one contract, named the way a document names it.

    Accepts the identifier with or without ``-draft``: a consumer reads
    ``musubi.trace-map/1-draft`` out of a document it is holding, and should not
    have to strip a suffix to find the schema for it.
    """
    name = CONTRACTS.get(contract.removesuffix("-draft"))
    if name is None:
        raise KeyError(
            f"{contract!r} is not a contract this musubi publishes. It has "
            f"{sorted(CONTRACTS)}, and a reader that does not recognise a contract "
            f"should refuse the document rather than parse it hopefully."
        )
    return schemas() / name


def load(contract: str) -> dict[str, Any]:
    """One contract, parsed. The bytes are the contract; this is a convenience."""
    body: dict[str, Any] = json.loads(path_to(contract).read_text(encoding="utf-8"))
    return body
