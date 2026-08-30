"""The seams: what musubi asks for, expressed as Protocols.

An implementer never imports the port it satisfies -- it only has to have the
right shape (`kiseki`'s ADR-0004). That is what lets a source, a converter or a
screener be written outside this repository without a musubi release.
"""

from __future__ import annotations
