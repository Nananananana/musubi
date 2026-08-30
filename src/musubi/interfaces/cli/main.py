"""The command line. `plan` first, because `plan` is the posture ([ADR-0012]).

A misclassified photograph can be looked at again; a corpus built from rules
that had not yet met this particular vault cannot be un-built without noticing
first. So the command that writes nothing is the one that exists, and it prints
what a sync *would* do -- every removal, every refusal, every skip, and the
coverage it would achieve.

The report leads with what would **not** happen. That is a deliberate reversal
of what every ingestion tool prints, and it is why the page can be handed to
somebody deciding whether to trust this with their notes.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from ... import __version__
from ...application.pipeline import Outcome, Settings, run
from ...domain.manifest import render
from ...errors import MusubiError
from ...infrastructure.converters import converter_for
from ...infrastructure.emitters import DocumentEmitter
from ...infrastructure.rules import CORE
from ...infrastructure.screeners import EntropyScreener, default_screener
from ...infrastructure.sources import FilesystemSource, ObsidianSource

__all__ = ["main"]

_SOURCES = {"obsidian": ObsidianSource, "filesystem": FilesystemSource}


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    if arguments.command is None:
        parser.print_help()
        return 2
    try:
        return _plan(arguments)
    except MusubiError as error:
        print(f"musubi: {error}", file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="musubi", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"musubi {__version__}")
    commands = parser.add_subparsers(dest="command")

    plan = commands.add_parser(
        "plan",
        help="say what a sync would do, and write nothing",
        description=(
            "Reads everything a sync would read and writes nothing. The first run over "
            "a real folder is the one most likely to be wrong, because it is the run "
            "where none of the rules have met this corpus yet."
        ),
    )
    plan.add_argument("root", type=Path, help="the folder you are naming")
    plan.add_argument(
        "--as",
        dest="kind",
        choices=sorted(_SOURCES),
        default="obsidian",
        help="what kind of folder this is (default: obsidian)",
    )
    plan.add_argument(
        "--into",
        type=Path,
        default=Path("synced"),
        help="where a sync would write (nothing is written by plan)",
    )
    plan.add_argument(
        "--source-id",
        default=None,
        help="what to call this source in keys and in the manifest",
    )
    plan.add_argument(
        "--screen-entropy",
        action="store_true",
        # argparse expands `%` in a help string, and the number this tier
        # exists to publish contains two of them.
        help="add the opt-in entropy tier. " + EntropyScreener.MEASURED.replace("%", "%%"),
    )
    plan.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="RULE:UNIT_KEY",
        help="a credential hit you have looked at and decided against",
    )
    plan.add_argument(
        "--show-removals",
        action="store_true",
        help="print the values that would be removed, to the terminal and never to a file",
    )
    plan.add_argument("--json", action="store_true", help="print the manifest instead")
    return parser


def _plan(arguments: argparse.Namespace) -> int:
    source_class = _SOURCES[arguments.kind]
    source = (
        source_class(arguments.root, source_id=arguments.source_id)
        if arguments.source_id
        else source_class(arguments.root)
    )
    settings = Settings(
        ruleset=CORE,
        screener=default_screener(entropy=arguments.screen_entropy),
        converter_for=converter_for,
        musubi_version=__version__,
        allowed=frozenset(arguments.allow),
        created_at=datetime.now(UTC).isoformat(),
    )
    outcome = run(source, settings, DocumentEmitter(arguments.into), write=False)

    if arguments.json:
        print(render(outcome.manifest), end="")
    else:
        _report(outcome, show_removals=arguments.show_removals)
    return 1 if outcome.refused else 0


def _report(outcome: Outcome, *, show_removals: bool) -> None:
    manifest = outcome.manifest
    coverage = manifest.coverage

    print(f"musubi plan — {manifest.summary()}")
    print(f"  nothing was written. run id {manifest.run_id}")

    if outcome.refusals:
        print("\nWould refuse, and stop the whole run")
        for key, finding in outcome.refusals:
            print(f"  {finding.describe(key)}")

    if manifest.skipped:
        print("\nWould not be read")
        for skip in manifest.skipped:
            detail = f" ({skip.detail})" if skip.detail else ""
            print(f"  {skip.origin}  {skip.reason}{detail}")

    if manifest.removals:
        print("\nWould be removed")
        for rule, count in sorted(Counter(r.rule for _, r in manifest.removals).items()):
            print(f"  {rule}  {count}x")
        if show_removals:
            # The one place a removed value is printed. To the terminal, never
            # to a file ([ADR-0005]) -- the removed thing is usually the
            # sensitive thing.
            print("\n  values (terminal only, never written)")
            for key, removal in manifest.removals:
                print(f"    {key} {removal.span}  {removal.rule}")

    print("\nCoverage")
    print(f"  {coverage.emitted} documents would be written, {coverage.skipped} skipped")
    print(
        f"  {coverage.traceable_characters} of {coverage.characters} characters traceable "
        f"({coverage.traceable_coverage:.1%})"
    )
    for source_record in manifest.sources:
        for cap in source_record.caps:
            print(f"  cap: {cap}")

    print("\nLimits")
    for limit in manifest.limits:
        print(f"  {limit}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
