"""The choices a configuration can make, in one place, with their names.

Clean architecture buys the ability to swap an implementation without the
callers noticing. That is worth nothing until somebody can *name* the
alternative, so this is the table of names: what each family is, what is in it,
and what the manifest will record when it is used.

```text
family      names                          decided by
----------  -----------------------------  --------------------------
source      filesystem, notion, obsidian   how a folder is read
screener    signatures, signatures+entropy  ADR-0017
rules       core, none                     ADR-0016
converter   markdown@1, text@1, html@1,    ADR-0004; per media type
            pdf_text@1
```

**A family is not a plugin system.** Nothing here loads code by name from
outside the package: ADR-0001 is about musubi being pointed at everything its
owner has ever written, and a settings file that can name an arbitrary import
path is a settings file that can run anything. The names resolve against a
table that ships in the wheel; a third-party converter is registered by a
program that imported musubi deliberately, through `register_converter`, and
`musubi config` will then list it because the table is read at the moment of
the question rather than at import.

**Every name is recorded.** The manifest already carries the converter per
artefact and the ruleset with its version; what is chosen here is therefore
visible in the corpus afterwards, not only in the shell history of whoever ran
it. An algorithm that can be switched and not seen is worse than one that
cannot be switched.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from ..domain.removal import Ruleset
from ..errors import ContractError
from ..ports.converter import Converter
from ..ports.screener import Screener
from .converters import converter_for, known_converters
from .decoding import Decoding
from .rules import CORE
from .screeners import default_screener

__all__ = [
    "EMPTY",
    "RULESETS",
    "SCREENERS",
    "chooser",
    "ruleset_named",
    "screener_named",
]

#: A pack with no rules. Not the absence of cleansing but the choice of it, so
#: that a manifest still names a ruleset and a version, and a corpus built with
#: nothing removed says so in the same field as one built with sixty-five rules.
EMPTY = Ruleset(id="none", version=CORE.version, rules=())

RULESETS: Mapping[str, Ruleset] = {"core": CORE, "none": EMPTY}

#: Built on call rather than stored: a screener holds no state worth sharing,
#: and a table of instances would be one more thing to reset between tests.
SCREENERS: Mapping[str, bool] = {"signatures": False, "signatures+entropy": True}


def ruleset_named(name: str) -> Ruleset:
    if name not in RULESETS:
        raise ContractError(f"no cleansing pack called {name!r}; musubi has {_known(RULESETS)}")
    return RULESETS[name]


def screener_named(name: str) -> Screener:
    if name not in SCREENERS:
        raise ContractError(f"no screener called {name!r}; musubi has {_known(SCREENERS)}")
    return default_screener(entropy=SCREENERS[name])


def chooser(
    overrides: Mapping[str, str], *, detect: bool = False
) -> Callable[[str], Converter | None]:
    """A `converter_for` that consults the overrides first.

    Returned as a callable rather than by mutating the registry: the registry is
    module state, so a process running two syncs with different settings would
    otherwise have the second one's choices leaking backwards into the first.

    Resolved here rather than at the first file, so that a name nothing
    registers fails *before* the run. Otherwise a configuration naming a
    converter that is not there produces a corpus missing exactly one format,
    reported as `no_converter` on every file of it -- which reads as a sentence
    about the input.
    """
    known = {converter.name: converter for converter in known_converters()}
    chosen: dict[str, Converter] = {}
    for media_type, name in sorted(overrides.items()):
        if name not in known:
            raise ContractError(
                f"the converter for {media_type!r} is set to {name!r}, which is not "
                f"registered; musubi has {', '.join(sorted(known))}"
            )
        chosen[media_type] = known[name]

    def pick(media_type: str) -> Converter | None:
        found = chosen.get(media_type) or converter_for(media_type)
        # Wrapped whichever converter it is, so the encoding policy is one
        # decision in one place rather than a parameter every converter has to
        # remember to honour (ADR-0031).
        return None if found is None else Decoding(found, detect=detect)

    return pick


def _known(table: Mapping[str, object]) -> str:
    return ", ".join(sorted(table))
