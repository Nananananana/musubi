"""Cleansing rule packs. Data, not code (ADR-0009).

Adding a source's quirks is an entry in a pack and a fixture, never a branch in
the cleanser.
"""

from __future__ import annotations

from .core import CORE, VERSION

__all__ = ["CORE", "VERSION"]
