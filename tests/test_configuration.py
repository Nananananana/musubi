"""Settings from a file, and the question *where did this value come from*.

The tests are arranged around the two things a configuration system gets wrong:
**which file is in effect**, and **which layer decided a value**. Both are
invisible failures -- the run succeeds, with settings the operator did not
choose -- so both are asserted on the origin rather than only on the value.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from musubi.config import DEFAULTS, OPTIONS, describe, load
from musubi.errors import ContractError
from musubi.infrastructure.algorithms import EMPTY, RULESETS, SCREENERS, chooser, ruleset_named
from musubi.infrastructure.rules import CORE

NOTHING: dict[str, str] = {}


def written(directory: Path, name: str, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


# -- which file is in effect ------------------------------------------------


def test_with_no_file_anywhere_every_value_is_a_default(tmp_path: Path) -> None:
    configuration = load(tmp_path, NOTHING)
    assert configuration.read is None
    for option in OPTIONS:
        assert configuration.origin(option.name) == "default"
        assert configuration[option.name] == option.default


def test_the_nearest_file_wins_and_the_others_are_named(tmp_path: Path) -> None:
    """Nearest wins **whole**, and the ones passed over are reported.

    Not merged: a setting that is the sum of four files cannot be predicted from
    any one of them. What makes that liveable is saying which files existed and
    were not read, which is the question somebody standing in a subdirectory
    actually has.
    """
    written(tmp_path, "musubi.toml", 'into = "outer"\nrules = "none"\n')
    inner = tmp_path / "a" / "b"
    written(inner, "musubi.toml", 'into = "inner"\n')

    configuration = load(inner, NOTHING)
    assert configuration["into"] == "inner"
    assert configuration["rules"] == "core", (
        "the outer file set rules=none; merging would have carried it down"
    )
    assert configuration.passed_over == (tmp_path / "musubi.toml",)


def test_a_dedicated_file_beats_pyproject_in_the_same_directory(tmp_path: Path) -> None:
    written(tmp_path, "pyproject.toml", '[tool.musubi]\ninto = "from-pyproject"\n')
    written(tmp_path, "musubi.toml", 'into = "from-musubi-toml"\n')
    assert load(tmp_path, NOTHING)["into"] == "from-musubi-toml"


def test_a_pyproject_with_no_tool_table_is_not_a_config_file(tmp_path: Path) -> None:
    """Otherwise the first `pyproject.toml` above a notes folder wins the search
    while setting nothing, and silences every file above it -- including,
    during development, musubi's own."""
    written(tmp_path, "musubi.toml", 'into = "outer"\n')
    inner = tmp_path / "project"
    written(inner, "pyproject.toml", '[project]\nname = "something-else"\n')

    configuration = load(inner, NOTHING)
    assert configuration["into"] == "outer"
    assert configuration.read == tmp_path / "musubi.toml"


# -- which layer decided ----------------------------------------------------


def test_the_environment_beats_the_file_and_says_so(tmp_path: Path) -> None:
    written(tmp_path, "musubi.toml", 'into = "from-file"\n')
    configuration = load(tmp_path, {"MUSUBI_INTO": "from-environment"})
    assert configuration["into"] == "from-environment"
    assert configuration.origin("into") == "MUSUBI_INTO"


def test_a_flag_beats_the_environment_and_says_so(tmp_path: Path) -> None:
    written(tmp_path, "musubi.toml", 'into = "from-file"\n')
    configuration = load(tmp_path, {"MUSUBI_INTO": "from-environment"}).overridden_by(
        {"into": "from-a-flag"}
    )
    assert configuration["into"] == "from-a-flag"
    assert configuration.origin("into") == "--into"


def test_a_flag_that_was_not_given_does_not_override_anything(tmp_path: Path) -> None:
    """`None` means absent. This is why every flag a file can also set has
    `default=None` in the parser: an `argparse` default is indistinguishable
    from a typed value, so without it the file could never win."""
    written(tmp_path, "musubi.toml", 'into = "from-file"\n')
    configuration = load(tmp_path, NOTHING).overridden_by({"into": None, "rules": None})
    assert configuration["into"] == "from-file"
    assert configuration.origin("into") == "musubi.toml:into"


def test_every_option_can_be_set_from_the_environment_or_says_why_not() -> None:
    """A guard on the layer, not on one setting.

    An option that can be set in a file and not in the environment is a hole
    somebody discovers at deployment. There is exactly one here -- a table --
    and it refuses out loud rather than being ignored.
    """
    for option in OPTIONS:
        if option.kind is dict:
            with pytest.raises(ContractError, match="cannot be set from the environment"):
                load(Path.cwd(), {option.environment: "anything"})
        else:
            # A sample the option can actually take. The first version handed
            # every non-table option the string `"x"`, which a float refuses --
            # so the guard was about to start failing for the right reason on a
            # setting it was supposed to be checking.
            if option.choices:
                value = option.choices[0]
            elif option.kind is float:
                value = str(option.default)
            else:
                value = "x"
            assert load(Path.cwd(), {option.environment: value})[option.name] is not None


# -- what it refuses --------------------------------------------------------


def test_an_unrecognised_key_stops_and_names_the_nearest(tmp_path: Path) -> None:
    """A typo in a setting name is otherwise silent, and the setting the typist
    meant to change is still at its default while the file plainly says it is
    not."""
    written(tmp_path, "musubi.toml", 'screner = "signatures"\n')
    with pytest.raises(ContractError, match="Did you mean 'screener'"):
        load(tmp_path, NOTHING)


def test_a_value_outside_the_choices_stops_and_lists_them(tmp_path: Path) -> None:
    written(tmp_path, "musubi.toml", 'screener = "entropy"\n')
    with pytest.raises(ContractError, match="signatures, signatures\\+entropy"):
        load(tmp_path, NOTHING)


def test_a_value_of_the_wrong_type_stops(tmp_path: Path) -> None:
    written(tmp_path, "musubi.toml", "allow = 3\n")
    with pytest.raises(ContractError, match="'allow' is list"):
        load(tmp_path, NOTHING)


def test_there_is_no_way_to_turn_the_screener_off() -> None:
    """[ADR-0008] stops a run on a credential, and a corpus that was never
    screened looks exactly like one that was. Every tier in `SCREENERS` includes
    the signature tier; a switch for *no screening* is not a setting."""
    assert SCREENERS, "an empty table would make this assertion vacuous"
    assert all(name.startswith("signatures") for name in SCREENERS)


def test_broken_toml_is_reported_as_the_file_it_is_in(tmp_path: Path) -> None:
    written(tmp_path, "musubi.toml", "into = \n")
    with pytest.raises(ContractError, match="is not valid TOML"):
        load(tmp_path, NOTHING)


# -- the algorithms a setting names -----------------------------------------


def test_every_choice_an_option_offers_resolves_to_something() -> None:
    """The two lists are kept in different files and have no reason to stay in
    step on their own: a choice the parser accepts and the registry cannot
    resolve is an error at the moment of a run rather than at the moment of a
    setting."""
    by_name = {option.name: option for option in OPTIONS}
    assert set(by_name["rules"].choices) == set(RULESETS)
    assert set(by_name["screener"].choices) == set(SCREENERS)


def test_the_empty_pack_is_a_choice_rather_than_an_absence() -> None:
    """A corpus built with nothing removed still names a ruleset and a version,
    in the same manifest field as one built with sixty-five rules."""
    assert ruleset_named("none") is EMPTY
    assert EMPTY.rules == ()
    assert EMPTY.version == CORE.version
    assert ruleset_named("core") is CORE


def test_a_converter_override_is_resolved_before_the_run_not_during_it() -> None:
    """A name nothing registers would otherwise produce a corpus missing exactly
    one format, reported as `no_converter` on every file of it -- which reads as
    a sentence about the input."""
    with pytest.raises(ContractError, match="not registered"):
        chooser({"text/html": "a-converter-nobody-wrote@1"})


def test_an_override_changes_only_the_media_type_it_names() -> None:
    pick = chooser({"text/html": "plaintext@1"})
    assert pick("text/html").name == "plaintext@1"  # type: ignore[union-attr]
    assert pick("application/pdf").name == "pdf_text@1"  # type: ignore[union-attr]
    assert pick("application/x-nothing") is None


def test_choosing_does_not_change_the_registry() -> None:
    """The registry is module state. A process running two syncs with different
    settings would otherwise have the second one's choices leaking backwards
    into the first."""
    from musubi.infrastructure.converters import converter_for

    chooser({"text/html": "plaintext@1"})
    assert converter_for("text/html").name == "html@1"  # type: ignore[union-attr]


# -- what the command prints ------------------------------------------------


def test_every_setting_is_printed_with_an_origin(tmp_path: Path) -> None:
    rows = describe(load(tmp_path, NOTHING))
    assert len(rows) == len(OPTIONS)
    assert all(origin for _, _, origin, _ in rows), "a row with no origin is the failure"


def test_the_alternatives_are_printed_beside_the_value(tmp_path: Path) -> None:
    """So that the algorithms are visible where one is set, rather than only in
    a manual somebody has to know exists."""
    rows = {name: alternatives for name, _, _, alternatives in describe(load(tmp_path, NOTHING))}
    assert rows["rules"] == "none"
    assert rows["screener"] == "signatures+entropy"


def test_the_defaults_table_agrees_with_the_options() -> None:
    assert {option.name: option.default for option in OPTIONS} == DEFAULTS
