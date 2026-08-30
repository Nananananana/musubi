"""The outer ring: everything that knows about a format, a file or a vendor.

ADR-0001. The domain is handed strings; this is where the strings come from and
where the rules that run over them are written down.
"""

from __future__ import annotations
