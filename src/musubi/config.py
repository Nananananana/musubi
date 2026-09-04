"""Settings from a file, and where every one of them came from.

## Where it looks

The convention every recent Python tool has converged on, and musubi follows it
rather than inventing a fifth one: a dedicated file, or a `[tool.musubi]` table
in `pyproject.toml`, searched from the working directory upward.

```text
./musubi.toml                    a folder of notes is not a Python project
./.musubi.toml                   the same file, hidden
./pyproject.toml [tool.musubi]   when it is
```

**The nearest file wins whole.** Not merged with the ones above it: a setting
that is the sum of four files is a setting nobody can predict from any one of
them, and the question *why is this on* then has no answer shorter than the
whole tree. `ruff` and `uv` both default to this, and both offer explicit
inheritance for the case that needs it; musubi does not have that case yet and
does not guess at its shape.

## Precedence

```text
--flag                 what you typed now
MUSUBI_SCREENER        what this shell is set up for
musubi.toml            what this folder is
default                what musubi thinks
```

## What is different here

**Every effective value says where it came from**, and `musubi config` prints
the origin next to the value along with the files that were *found and not
used*. A configuration system's whole failure mode is a setting arriving from
somewhere the reader is not looking, and this project's entire claim is about
knowing where a thing came from. Applying that to its own settings costs one
field.

## What it refuses

An unrecognised key. Not a warning: a typo in a setting name is silent
otherwise, and the setting the typist meant to change is still at its default
while the file plainly says it is not. The message names the nearest known key.

There is no `screener = "none"`. [ADR-0008] stops a run on a credential and a
corpus that was never screened looks exactly like one that was; a switch for
that is not a setting, it is a different program.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path
from typing import Any

from .application.pipeline import Settings
from .errors import ContractError
from .infrastructure.algorithms import chooser, ruleset_named, screener_named
from .infrastructure.sources import FilesystemSource, NotionSource, ObsidianSource
from .ports.source import Source

__all__ = [
    "DEFAULTS",
    "FILENAMES",
    "OPTIONS",
    "SOURCES",
    "Configuration",
    "Option",
    "Setting",
    "describe",
    "destination",
    "load",
    "settings_from",
    "source_from",
]

#: The three ways a folder can be read, by the name a setting uses. Here rather
#: than in the CLI because this module is the composition root: what an
#: interface does with a configuration is print it or run it, and neither should
#: require knowing which class implements `notion`.
#:
#: Typed as a factory rather than as `type[Source]`, because `Source` is a
#: structural protocol ([ADR-0004]'s shape, `kiseki`'s ADR-0004's reason) and a
#: protocol says nothing about a constructor. What these have in common is that
#: they can be called with a root; that is the only thing this needs.
SOURCES: Mapping[str, Callable[..., Source]] = {
    "filesystem": FilesystemSource,
    "notion": NotionSource,
    "obsidian": ObsidianSource,
}

#: Searched in this order within one directory. The first that exists is the
#: one used, and the rest of the directory is not consulted.
FILENAMES: tuple[str, ...] = ("musubi.toml", ".musubi.toml", "pyproject.toml")

#: What an origin says when nothing said otherwise.
DEFAULT = "default"


@dataclass(frozen=True, slots=True)
class Option:
    """One recognised setting: its type, its default, and what it is for."""

    name: str
    kind: type
    default: Any
    help: str
    #: When non-empty, the only accepted values. Printed by `musubi config`, so
    #: that the alternatives to an algorithm are visible where it is set rather
    #: than only in a manual.
    choices: tuple[str, ...] = ()

    @property
    def environment(self) -> str:
        return f"MUSUBI_{self.name.replace('-', '_').upper()}"


OPTIONS: tuple[Option, ...] = (
    Option(
        "source",
        str,
        "obsidian",
        "what kind of folder the root is",
        ("filesystem", "notion", "obsidian"),
    ),
    Option("into", str, "synced", "where the corpus goes"),
    Option(
        "screener",
        str,
        "signatures",
        "which credential tiers run (ADR-0017)",
        ("signatures", "signatures+entropy"),
    ),
    Option(
        "rules",
        str,
        "core",
        "which cleansing pack runs (ADR-0016)",
        ("core", "none"),
    ),
    Option(
        "converters",
        dict,
        {},
        "media type -> converter name, overriding the built-in claim",
    ),
    Option("allow", list, [], "credential hits already looked at, as rule:unit_key"),
)

DEFAULTS: Mapping[str, Any] = {option.name: option.default for option in OPTIONS}

_BY_NAME = {option.name: option for option in OPTIONS}


@dataclass(frozen=True, slots=True)
class Setting:
    """A value, and the thing that decided it."""

    value: Any
    origin: str

    @property
    def is_default(self) -> bool:
        return self.origin == DEFAULT


@dataclass(frozen=True, slots=True)
class Configuration:
    """Every recognised setting, resolved, with its origin."""

    settings: Mapping[str, Setting]
    #: The file that was read, if any.
    read: Path | None = None
    #: Files that were found further up and not read, because a nearer one won.
    passed_over: tuple[Path, ...] = ()

    def __getitem__(self, name: str) -> Any:
        return self.settings[name].value

    def origin(self, name: str) -> str:
        return self.settings[name].origin

    def overridden_by(self, flags: Mapping[str, Any]) -> Configuration:
        """The same configuration with command-line values on top.

        A flag whose value is ``None`` was not given. A flag equal to its own
        default cannot be told apart from an absent one by `argparse`, which is
        why the caller passes only what it knows was typed.
        """
        merged = dict(self.settings)
        for name, value in flags.items():
            if value is None or name not in _BY_NAME:
                continue
            merged[name] = Setting(_checked(_BY_NAME[name], value, "--" + name), f"--{name}")
        return Configuration(merged, self.read, self.passed_over)


def load(start: Path | None = None, environ: Mapping[str, str] | None = None) -> Configuration:
    """Resolve the settings for a run started in `start`.

    Reads exactly one file -- the nearest -- and reports the ones above it that
    it did not read, because *which file is in effect* is the question a reader
    of four repositories actually has.
    """
    here = (start or Path.cwd()).resolve()
    environment = os.environ if environ is None else environ

    found = _candidates(here)
    read, from_file = (found[0], _read(found[0])) if found else (None, {})

    settings: dict[str, Setting] = {}
    for option in OPTIONS:
        if option.name in from_file:
            where = f"{read.name}:{option.name}" if read else DEFAULT
            settings[option.name] = Setting(_checked(option, from_file[option.name], where), where)
        else:
            settings[option.name] = Setting(option.default, DEFAULT)

    for option in OPTIONS:
        raw = environment.get(option.environment)
        if raw is None:
            continue
        settings[option.name] = Setting(
            _checked(option, _parse(option, raw), option.environment), option.environment
        )

    return Configuration(
        settings=settings,
        read=read,
        passed_over=tuple(found[1:]),
    )


def _candidates(here: Path) -> list[Path]:
    """Every configuration file at or above `here`, nearest first."""
    found: list[Path] = []
    for directory in (here, *here.parents):
        for name in FILENAMES:
            path = directory / name
            if not path.is_file():
                continue
            if name == "pyproject.toml" and not _has_table(path):
                continue
            found.append(path)
            break
    return found


def _has_table(pyproject: Path) -> bool:
    """A `pyproject.toml` with no `[tool.musubi]` is not a musubi config file.

    Without this, the first `pyproject.toml` above a notes folder -- somebody
    else's project, or musubi's own during development -- would win the search
    and silence every file above it while setting nothing.
    """
    try:
        with pyproject.open("rb") as handle:
            body = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    tool = body.get("tool")
    return isinstance(tool, dict) and isinstance(tool.get("musubi"), dict)


def _read(path: Path) -> Mapping[str, Any]:
    try:
        with path.open("rb") as handle:
            body = tomllib.load(handle)
    except OSError as error:
        raise ContractError(f"{path} could not be read: {error}") from error
    except tomllib.TOMLDecodeError as error:
        raise ContractError(f"{path} is not valid TOML: {error}") from error

    table = body
    if path.name == "pyproject.toml":
        tool = body.get("tool", {})
        table = tool.get("musubi", {}) if isinstance(tool, dict) else {}
    if not isinstance(table, dict):
        raise ContractError(f"{path} has a [tool.musubi] that is not a table")

    unknown = sorted(set(table) - set(_BY_NAME))
    if unknown:
        raise ContractError(
            f"{path} sets {unknown[0]!r}, which musubi does not "
            f"recognise.{_did_you_mean(unknown[0])}"
        )
    return table


def _did_you_mean(name: str) -> str:
    near = get_close_matches(name, list(_BY_NAME), n=1)
    if near:
        return f" Did you mean {near[0]!r}?"
    return f" The settings are: {', '.join(sorted(_BY_NAME))}."


def _parse(option: Option, raw: str) -> Any:
    """An environment variable is a string; a setting may not be.

    Only the shapes that have a spelling a shell can produce without ambiguity.
    A list is comma-separated; a table is not offered, because
    `MUSUBI_CONVERTERS='text/html=x,application/pdf=y'` is a syntax nobody would
    guess and getting it wrong is silent.
    """
    if option.kind is list:
        return [item.strip() for item in raw.split(",") if item.strip()]
    if option.kind is dict:
        raise ContractError(
            f"{option.environment} cannot be set from the environment: {option.name!r} is a "
            f"table, and a table flattened into a string is a syntax nobody can read back. "
            f"Set it in musubi.toml."
        )
    return raw


def _checked(option: Option, value: Any, where: str) -> Any:
    if option.kind is list and isinstance(value, list):
        if not all(isinstance(item, str) for item in value):
            raise ContractError(f"{where} must be a list of strings")
        return list(value)
    if option.kind is dict and isinstance(value, dict):
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
            raise ContractError(f"{where} must be a table of strings")
        return dict(value)
    if option.kind is str and isinstance(value, str):
        if option.choices and value not in option.choices:
            raise ContractError(f"{where} is {value!r}; musubi knows {', '.join(option.choices)}")
        return value
    raise ContractError(
        f"{where} is {type(value).__name__}, and {option.name!r} is {option.kind.__name__}"
    )


def describe(configuration: Configuration) -> Sequence[tuple[str, str, str, str]]:
    """Every setting as (name, value, origin, alternatives), for printing."""
    rows = []
    for option in OPTIONS:
        setting = configuration.settings[option.name]
        value = setting.value
        if isinstance(value, dict):
            shown = ", ".join(f"{k}={v}" for k, v in sorted(value.items())) or "(none)"
        elif isinstance(value, list):
            shown = ", ".join(str(item) for item in value) or "(none)"
        else:
            shown = str(value)
        alternatives = ", ".join(c for c in option.choices if c != value)
        rows.append((option.name, shown, setting.origin, alternatives))
    return rows


# -- turning settings into the objects a run needs --------------------------


def source_from(configuration: Configuration, root: Path, source_id: str | None = None) -> Source:
    """The reader this configuration names, pointed at `root`."""
    made = SOURCES[configuration["source"]]
    return made(root, source_id=source_id) if source_id else made(root)


def settings_from(
    configuration: Configuration, *, musubi_version: str, created_at: str
) -> Settings:
    """Everything the pipeline needs, chosen by name.

    Each of the three is resolved **here**, before a run rather than during one:
    a name nothing registers otherwise produces a corpus missing exactly one
    format, reported per file as `no_converter`, which reads as a sentence about
    the input rather than about the settings.
    """
    return Settings(
        ruleset=ruleset_named(configuration["rules"]),
        screener=screener_named(configuration["screener"]),
        converter_for=chooser(configuration["converters"]),
        musubi_version=musubi_version,
        allowed=frozenset(configuration["allow"]),
        created_at=created_at,
    )


def destination(configuration: Configuration) -> Path:
    return Path(configuration["into"])
