"""The domain: values and pure services, and nothing outside the standard library.

ADR-0001. Nothing here opens a file, knows what a path is, or knows that Notion
exists. It is handed strings and hands back values, which is what lets the whole
conversion be tested with no filesystem -- and what makes ADR-0003's
reproducibility claim something that can be asserted rather than hoped for.

The domain raises built-in exceptions rather than importing ``musubi.errors``,
so that its dependency set is genuinely empty.
"""

from __future__ import annotations
