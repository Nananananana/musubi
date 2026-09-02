"""The command line. `plan` first, because `plan` is the posture ([ADR-0012]).

A misclassified photograph can be looked at again; a corpus built from rules
that had not yet met this particular vault cannot be un-built without noticing
first. So the command that writes nothing comes first and is the one to reach
for, and `sync` is the same run with the writing switched on.

Both reports lead with what did **not** happen. That is a deliberate reversal of
what every ingestion tool prints, and it is why the page can be handed to
somebody deciding whether to trust this with their notes.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ... import __version__
from ...application.pipeline import Outcome, Settings, run
from ...application.sync import Synced, empties_the_corpus, sync, withdrawals
from ...application.trace import Resolution, resolve
from ...application.verify import Verified, verify
from ...domain.manifest import Manifest, render
from ...domain.span import Span
from ...domain.trace import CHARACTERS
from ...errors import MusubiError, TraceError
from ...infrastructure.converters import converter_for
from ...infrastructure.corpus import Corpus
from ...infrastructure.emitters import DOCUMENTS, MANIFEST, TRACES, DocumentEmitter
from ...infrastructure.rules import CORE
from ...infrastructure.screeners import EntropyScreener, default_screener
from ...infrastructure.sources import FilesystemSource, NotionSource, ObsidianSource

__all__ = ["main"]

_SOURCES = {"obsidian": ObsidianSource, "filesystem": FilesystemSource, "notion": NotionSource}


def main(argv: Sequence[str] | None = None) -> int:
    _readable()
    parser = _parser()
    arguments = parser.parse_args(argv)
    if arguments.command is None:
        parser.print_help()
        return 2
    commands = {"plan": _plan, "sync": _sync, "trace": _trace, "verify": _verify}
    try:
        return commands[arguments.command](arguments)
    except MusubiError as error:
        print(f"musubi: {error}", file=sys.stderr)
        return 1


def _readable() -> None:
    """Make the report streams incapable of failing a run ([ADR-0020]).

    A `cp932` console -- the default on Japanese Windows -- cannot encode an em
    dash, and `musubi sync` returned 1 with the corpus fully written because a
    heading would not print. The exit code said nothing was written; the
    destination was full.

    The stream is configured rather than each string sanitised, because musubi's
    subject is other people's documents: a skip line naming a file, an excerpt in
    `trace`, a rule id somebody added. Avoiding non-ASCII in musubi's own strings
    would fix one em dash and none of those.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


def _document(body: str) -> None:
    """Write a machine-facing document, in UTF-8, whatever the console is.

    JSON is UTF-8 by definition, and `--json` exists to be redirected or piped.
    Passing it through the terminal's codec produced a file that was not valid
    UTF-8, with exit 0 and no error anywhere ([ADR-0020]).
    """
    sys.stdout.flush()
    sys.stdout.buffer.write(body.encode("utf-8"))
    sys.stdout.buffer.flush()


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
    _shared(plan)
    plan.add_argument(
        "--show-removals",
        action="store_true",
        help="print the values that would be removed, to the terminal and never to a file",
    )

    synchronise = commands.add_parser(
        "sync",
        help="build the corpus, or refuse and build nothing",
        description=(
            "The same run as `plan`, with the writing switched on. Everything is staged "
            "and promoted together: a credential means nothing is written at all, not "
            "the offending unit skipped. An artefact whose unit is no longer in the "
            "source is taken back out, because a corpus that keeps a document its owner "
            "deleted goes on answering questions from it."
        ),
    )
    _shared(synchronise)

    following = commands.add_parser(
        "trace",
        help="say where a range of a synced document came from",
        description=(
            "The command the whole design is for. Give it a range of a document musubi "
            "built and it resolves back through every transformation to a place in the "
            "file you actually have -- in characters, and in bytes when the file is "
            "still there to measure against."
        ),
    )
    following.add_argument(
        "target",
        help="a document and a range: synced/documents/design/gear.md:1204-1231",
    )
    following.add_argument(
        "--into",
        type=Path,
        default=None,
        help="the destination, when the target is given as a key rather than a path",
    )
    following.add_argument("--json", action="store_true", help="print the answer as a document")

    checking = commands.add_parser(
        "verify",
        help="check a corpus that is already on a disk",
        description=(
            "Every other command checks a corpus while writing it. This one checks a "
            "folder, with no run in sight: a corpus is written once and read for years, "
            "and in between it is copied, synced, restored from a backup and opened by "
            "editors. It checks what the published schemas cannot say, and the one thing "
            "no test can -- that each document still hashes to what the manifest recorded."
        ),
    )
    checking.add_argument(
        "destination",
        type=Path,
        nargs="?",
        default=Path("synced"),
        help="the corpus to check (default: ./synced)",
    )
    checking.add_argument("--json", action="store_true", help="print the findings as a document")

    return parser


def _shared(command: argparse.ArgumentParser) -> None:
    """The options both commands take.

    One function rather than two lists, so that a flag cannot exist on the dry
    run and not on the real one -- which is the one way the shared pipeline
    cannot stop a plan from ceasing to predict a sync.
    """
    command.add_argument("root", type=Path, help="the folder you are naming")
    command.add_argument(
        "--as",
        dest="kind",
        choices=sorted(_SOURCES),
        default="obsidian",
        help="what kind of folder this is (default: obsidian)",
    )
    command.add_argument(
        "--into",
        type=Path,
        default=Path("synced"),
        help="where the corpus goes (default: ./synced)",
    )
    command.add_argument(
        "--source-id",
        default=None,
        help="what to call this source in keys and in the manifest",
    )
    command.add_argument(
        "--screen-entropy",
        action="store_true",
        # argparse expands `%` in a help string, and the number this tier
        # exists to publish contains two of them.
        help="add the opt-in entropy tier. " + EntropyScreener.MEASURED.replace("%", "%%"),
    )
    command.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="RULE:UNIT_KEY",
        help="a credential hit you have looked at and decided against",
    )
    # In _shared() and not only on `sync`: a flag that exists on the real run
    # and not on the dry one is the way a plan stops predicting a sync.
    command.add_argument(
        "--withdraw-all",
        action="store_true",
        help="proceed when the source is empty and the whole corpus would be taken back out",
    )
    command.add_argument("--json", action="store_true", help="print the manifest instead")


def _prepare(arguments: argparse.Namespace) -> tuple[FilesystemSource, Settings, DocumentEmitter]:
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
    return source, settings, DocumentEmitter(arguments.into)


def _plan(arguments: argparse.Namespace) -> int:
    source, settings, emitter = _prepare(arguments)
    held = emitter.previously_written()
    outcome = run(source, settings, emitter, write=False)

    # A dry run that reports what would be written and stays silent about what
    # would be deleted is not a dry run of the same command.
    taken = withdrawals(held, outcome.manifest)
    stops = empties_the_corpus(held, outcome.manifest) and not arguments.withdraw_all

    if arguments.json:
        _document(render(replace(outcome.manifest, withdrawn=taken)))
    else:
        _report_plan(outcome, show_removals=arguments.show_removals)
        _report_withdrawals(taken, stops=stops)
    return 1 if outcome.refused or stops else 0


def _sync(arguments: argparse.Namespace) -> int:
    source, settings, emitter = _prepare(arguments)
    result = sync(source, settings, emitter, withdraw_all=arguments.withdraw_all)

    if arguments.json:
        _document(render(result.manifest))
    else:
        _report_sync(result, arguments.into)
    return 0


def _verify(arguments: argparse.Namespace) -> int:
    checked = verify(Corpus(arguments.destination))

    if arguments.json:
        _document(json.dumps(_checked(checked), ensure_ascii=False, indent=2) + "\n")
    else:
        _report_verify(checked)
    return 0 if checked.holds else 1


def _checked(checked: Verified) -> dict[str, Any]:
    return {
        "destination": checked.destination,
        "run_id": checked.run_id,
        "artefacts": checked.artefacts,
        "checks": checked.checks,
        "holds": checked.holds,
        "faults": [
            {"invariant": fault.invariant, "subject": fault.subject, "detail": fault.detail}
            for fault in checked.faults
        ],
    }


def _report_verify(checked: Verified) -> None:
    print(f"musubi verify — {checked.summary()}")
    print(f"  {checked.destination}. run id {checked.run_id}")
    if checked.holds:
        return
    print()
    print("Did not hold")
    for fault in checked.faults:
        print(f"  {fault.describe()}")
    print()
    print("Each name is an entry in docs/contracts.md under")
    print("  'What these schemas cannot say', which says why it matters.")


def _trace(arguments: argparse.Namespace) -> int:
    target, _, offsets = arguments.target.rpartition(":")
    if not target or "-" not in offsets:
        raise TraceError(
            f"{arguments.target!r} is not a document and a range. Write it as "
            f"path/to/document.md:1204-1231"
        )
    start, _, end = offsets.partition("-")
    try:
        span = Span(int(start), int(end))
    except ValueError as error:
        raise TraceError(f"{offsets!r} is not a range of two offsets: {error}") from error

    if arguments.into is None:
        corpus, key = Corpus.holding(Path(target))
    else:
        corpus, key = Corpus(arguments.into), Path(target).as_posix()
    found = resolve(corpus, key, span)
    if arguments.json:
        _document(json.dumps(_traced(found), ensure_ascii=False, indent=2) + "\n")
    else:
        _report_trace(found)
    return 0


def _report_trace(found: Resolution) -> None:
    kinds = ", ".join(kind.value for kind in found.kinds) or "nothing"
    print(f"{found.artefact} {found.out}  {kinds}")
    print(f"  {found.excerpt!r}")

    if found.is_synthetic:
        # The honest answer, and the one a naive resolver would get wrong by
        # reporting a source range for text that has no source.
        print(f"\n  musubi wrote this. It came from nothing in {found.source.unit_key}.")
        if found.rules:
            print(f"  ({', '.join(found.rules)})")
        return

    print(f"\n  {found.source.source_id}:{found.source.unit_key}")
    if found.source_unit == CHARACTERS:
        print(f"    characters {found.source_span}")
        if found.source_bytes is not None:
            mark = f", a {found.source.bom_bytes}-byte mark" if found.source.bom_bytes else ""
            print(f"    bytes      {found.source_bytes}  ({found.source.encoding}{mark})")
        else:
            print("    bytes      unknown: the source is not where the manifest said it was")
    else:
        # `[1:2]` is one page or one character and the two look identical, so
        # the unit is printed rather than assumed. There is no byte offset to
        # offer: a PDF has no decoded text for a character to index into.
        print(f"    pages      {found.source_span}  ({found.source_unit} locator)")
        print("    bytes      none: this map locates a page, not a character")
    if found.source_path is not None:
        print(f"    {found.source_path}")
    if found.rules:
        print(f"    through: {', '.join(found.rules)}")

    if found.source_excerpt is not None:
        print(f"\n  {found.source_excerpt!r}")
    if found.changed:
        print(
            "\n  The source has changed since the sync. These offsets are about the "
            "document musubi read, which is not the one on the disk now."
        )


def _traced(found: Resolution) -> dict[str, object]:
    return {
        "artefact": found.artefact,
        "out": [found.out.start, found.out.end],
        "excerpt": found.excerpt,
        "kinds": [kind.value for kind in found.kinds],
        "rules": list(found.rules),
        "converter": found.converter,
        "source": {
            "source_id": found.source.source_id,
            "unit_key": found.source.unit_key,
            "encoding": found.source.encoding,
            "bom_bytes": found.source.bom_bytes,
            "characters": [found.source_span.start, found.source_span.end],
            "bytes": (
                None
                if found.source_bytes is None
                else [found.source_bytes.start, found.source_bytes.end]
            ),
            "path": None if found.source_path is None else str(found.source_path),
            "excerpt": found.source_excerpt,
            "changed": found.changed,
        },
    }


def _report_plan(outcome: Outcome, *, show_removals: bool) -> None:
    manifest = outcome.manifest

    print(f"musubi plan — {manifest.summary()}")
    print(f"  nothing was written. run id {manifest.run_id}")

    if outcome.refusals:
        print("\nWould refuse, and stop the whole run")
        for key, finding in outcome.refusals:
            print(f"  {finding.describe(key)}")

    _account(manifest, "Would not be read", "Would be removed")
    if manifest.removals and show_removals:
        # The one place a removed value is printed. To the terminal, never to a
        # file ([ADR-0005]) -- the removed thing is usually the sensitive thing.
        print("\n  values (terminal only, never written)")
        for key, removal in manifest.removals:
            print(f"    {key} {removal.span}  {removal.rule}")

    _coverage(manifest, "would be written")
    _limits(manifest)


def _report_withdrawals(taken: tuple[str, ...], *, stops: bool) -> None:
    """What a sync would take back out, and whether it would refuse to."""
    if not taken:
        return
    print()
    if stops:
        print(f"This would take back out all {len(taken)} files in the corpus, and")
        print("the source produced nothing, so `musubi sync` will refuse to run.")
        print("An empty source and an unreadable one look the same from here.")
        print("Look at the source, then pass --withdraw-all if it really is empty.")
    else:
        print("Would be taken back out, because the source no longer has them")
    for path in taken:
        print(f"  {path}")


def _report_sync(result: Synced, destination: Path) -> None:
    manifest = result.manifest

    print(f"musubi sync — {manifest.summary()}")
    print(f"  {destination}. run id {manifest.run_id}")

    _account(manifest, "Not read", "Removed")

    if result.withdrawn:
        print("\nTaken back out, because the source no longer has them")
        for path in result.withdrawn:
            print(f"  {path}")

    _coverage(manifest, "written")
    # The run that created the ambiguity is the one that can resolve it.
    # Separating the trees makes the correct invocation available; it does not
    # make `ingest <destination>` safe, and that one is silent when it is wrong.
    print(f"\nIngest {destination / DOCUMENTS}")
    print(f"  {destination / TRACES} and {destination / MANIFEST}")
    print("  are musubi's own records, and are not documents to index.")
    _limits(manifest)


def _account(manifest: Manifest, skipped_heading: str, removed_heading: str) -> None:
    if manifest.skipped:
        print(f"\n{skipped_heading}")
        for skip in manifest.skipped:
            detail = f" ({skip.detail})" if skip.detail else ""
            print(f"  {skip.origin}  {skip.reason}{detail}")

    if manifest.removals:
        print(f"\n{removed_heading}")
        for rule, count in sorted(Counter(r.rule for _, r in manifest.removals).items()):
            print(f"  {rule}  {count}x")


def _coverage(manifest: Manifest, verb: str) -> None:
    coverage = manifest.coverage
    print("\nCoverage")
    print(f"  {coverage.emitted} documents {verb}, {coverage.skipped} skipped")
    print(
        f"  {coverage.traceable_characters} of {coverage.characters} characters traceable "
        f"({coverage.traceable_coverage:.1%})"
    )
    for source_record in manifest.sources:
        for cap in source_record.caps:
            print(f"  cap: {cap}")


def _limits(manifest: Manifest) -> None:
    print("\nLimits")
    for limit in manifest.limits:
        print(f"  {limit}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
