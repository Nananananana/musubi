"""The invariants no schema can express, asserted against real generated corpora.

`docs/contracts.md` enumerates what neither schema checks — starting with the
property the trace map exists for, that its segments cover every character of
the artefact exactly once, which JSON Schema 2020-12 cannot express in any form.
**This file is the executable form of that list**, and not a later
reinforcement of it: a schema handed over as "the contract" gets read as the
whole of it, and an enumeration nobody runs hands a consumer "written down but
never checked".

Everything here runs against a **real sync**: a generated vault on a disk, read
by the real source, converted, cleansed, screened, staged and promoted, and then
the files that landed are what is checked. Not a document assembled in a test —
`tsumugi` shipped a frozen contract and a reference producer and had never once
validated its own real output, and the first run against genuine output found a
real bug.

The corpora are generated to be awkward on purpose: CJK whose characters are not
its bytes, byte-order marks, CRLF, UTF-16, front matter the owner wrote, URLs
that lose a parameter and URLs that lose a whole query, empty files, and
filenames in two scripts.

The naming is load-bearing. `test_trace_N_...` and `test_manifest_N_...`
correspond to the numbered entries in `docs/contracts.md`, and
`test_every_enumerated_invariant_has_a_test` fails if the list grows an entry
that nothing runs.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from musubi import __version__
from musubi.application.pipeline import Settings
from musubi.application.sync import Synced, sync
from musubi.domain.hashing import content_hash, hash_of
from musubi.domain.span import Span
from musubi.domain.text import decode
from musubi.domain.trace import CHARACTERS, Kind, Segment, TraceMap
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.emitters import MANIFEST, TRACES, DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import ObsidianSource

CONTRACTS = Path(__file__).resolve().parent.parent / "docs" / "contracts.md"

#: Fragments chosen for what they do to offsets, not for what they say.
FRAGMENTS = (
    "# 見出し\n",
    "テントは 2.4kg。\n",
    "plain ascii, nothing interesting\n",
    "a\r\nb\r\n",
    "\n",
    "参考: https://example.com/g?utm_source=news&id=7\n",
    "see https://x.example/?utm_source=only\n",
    "https://en.wikipedia.org/wiki/Knot_(mathematics)\n",
    "---\ntags: [camping]\n---\n",
    "末尾に改行なし",
)

NAMES = ("gear", "設計メモ", "notes", "写真", "a")
FOLDERS = ("", "design", "設計")


@st.composite
def a_vault(draw: st.DrawFn) -> dict[str, bytes]:
    """A folder awkward enough to be worth syncing."""
    files: dict[str, bytes] = {}
    for name in draw(st.lists(st.sampled_from(NAMES), min_size=1, max_size=3, unique=True)):
        folder = draw(st.sampled_from(FOLDERS))
        suffix = draw(st.sampled_from((".md", ".txt")))
        body = "".join(draw(st.lists(st.sampled_from(FRAGMENTS), min_size=0, max_size=4)))

        codec, mark = draw(
            st.sampled_from(
                (("utf-8", b""), ("utf-8", b"\xef\xbb\xbf"), ("utf-16-le", b"\xff\xfe"))
            )
        )
        key = f"{folder}/{name}{suffix}" if folder else f"{name}{suffix}"
        files[key] = mark + body.encode(codec)
    return files


def build(files: dict[str, bytes]) -> tuple[Path, Path, Synced]:
    """A real sync of a real folder, promoted to a real disk."""
    work = Path(tempfile.mkdtemp())
    root = work / "vault"
    root.mkdir()
    for key, raw in files.items():
        path = root.joinpath(*key.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    into = work / "synced"
    result = sync(
        ObsidianSource(root),
        Settings(
            ruleset=CORE,
            screener=default_screener(),
            converter_for=converter_for,
            musubi_version=__version__,
            created_at="2026-08-30T00:00:00+00:00",
        ),
        DocumentEmitter(into),
    )
    return root, into, result


def maps(into: Path) -> list[dict[str, Any]]:
    found = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((into / TRACES).rglob("*.json"))
    ]
    return found


def manifest_of(into: Path) -> dict[str, Any]:
    body: dict[str, Any] = json.loads((into / MANIFEST).read_text(encoding="utf-8"))
    return body


CORPUS = settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])


# -- the trace map -----------------------------------------------------------


@CORPUS
@given(a_vault())
def test_trace_1_the_segments_cover_every_character_exactly_once(
    files: dict[str, bytes],
) -> None:
    """The property the map exists for, and the one JSON Schema cannot express
    in any form. A map with a gap answers a query with silence; one with an
    overlap answers it twice."""
    _, into, _ = build(files)
    try:
        for body in maps(into):
            at = 0
            for segment in body["segments"]:
                assert segment["out"][0] == at, f"a gap or an overlap at {at}"
                at = segment["out"][1]
            assert at == body["coverage"]["characters"], "the tiling stops short"
    finally:
        shutil.rmtree(into.parent, ignore_errors=True)


@CORPUS
@given(a_vault())
def test_trace_2_every_span_runs_forwards(files: dict[str, bytes]) -> None:
    """`end >= start`. Not expressible: JSON Schema 2020-12 cannot compare two
    members of the same array."""
    _, into, _ = build(files)
    try:
        for body in maps(into):
            for segment in body["segments"]:
                assert segment["out"][1] >= segment["out"][0]
                assert segment["src"][1] >= segment["src"][0]
    finally:
        shutil.rmtree(into.parent, ignore_errors=True)


@CORPUS
@given(a_vault())
def test_trace_3_a_verbatim_segment_reads_the_same_on_both_sides(
    files: dict[str, bytes],
) -> None:
    """The round trip. If this fails, `musubi trace` points readers at the wrong
    place in their own files. Checking it needs the artefact *and* the source; a
    schema has neither."""
    root, into, _ = build(files)
    try:
        for body in maps(into):
            artefact = (into / body["artefact"]["path"]).read_text(encoding="utf-8")
            source = decode(root.joinpath(*body["source"]["unit_key"].split("/")).read_bytes())
            for segment in body["segments"]:
                if segment["kind"] != Kind.VERBATIM.value:
                    continue
                out = artefact[segment["out"][0] : segment["out"][1]]
                src = source.text[segment["src"][0] : segment["src"][1]]
                assert out == src
    finally:
        shutil.rmtree(into.parent, ignore_errors=True)


@CORPUS
@given(a_vault())
def test_trace_4_a_removal_occupies_no_output(files: dict[str, bytes]) -> None:
    """`out[0] == out[1]` — two members of one array, which is exactly what
    cannot be compared."""
    _, into, _ = build(files)
    try:
        for body in maps(into):
            for segment in body["segments"]:
                if segment["kind"] == Kind.REMOVAL.value:
                    assert segment["out"][0] == segment["out"][1]
                    assert segment["src"][1] > segment["src"][0], "and a real stretch of source"
    finally:
        shutil.rmtree(into.parent, ignore_errors=True)


@CORPUS
@given(a_vault())
def test_trace_5_traceable_is_the_sum_of_the_traceable_segments(
    files: dict[str, bytes],
) -> None:
    _, into, _ = build(files)
    try:
        for body in maps(into):
            traceable = sum(
                segment["out"][1] - segment["out"][0]
                for segment in body["segments"]
                if segment["kind"] in {Kind.VERBATIM.value, Kind.TRANSFORMED.value}
            )
            assert traceable == body["coverage"]["traceable"]
            assert traceable <= body["coverage"]["characters"]
    finally:
        shutil.rmtree(into.parent, ignore_errors=True)


def test_trace_6_a_reader_must_not_assume_the_source_ranges_are_monotonic() -> None:
    """The one entry in the list that is a warning rather than a property.

    No converter reflows yet, so no real corpus produces a map whose source
    ranges jump — a PDF read in reading order will. What can be asserted today
    is that musubi's *own* reader does not assume it, which is the executable
    form of the warning.
    """
    reflowed = TraceMap(
        artefact_length=6,
        source_length=6,
        segments=(
            Segment(out=Span(0, 3), src=Span(3, 6), kind=Kind.VERBATIM),
            Segment(out=Span(3, 6), src=Span(0, 3), kind=Kind.VERBATIM),
        ),
    )
    assert reflowed.source_span_of(Span(0, 3)) == Span(3, 6)
    assert reflowed.source_span_of(Span(3, 6)) == Span(0, 3)
    assert reflowed.source_span_of(Span(0, 6)) == Span(0, 6), "the union covers both jumps"


def test_trace_7_a_range_that_straddles_runs_resolves_by_the_four_rules() -> None:
    """Reported by the `seam` session, whose resolver had to guess this and
    guessed the dangerous way: it treated a straddling range as *did not
    resolve* and printed it with the same `ok` as a range musubi had answered.

    musubi's own reader already behaved correctly. What was missing was the
    contract saying so, which is why a consumer had no way to know. So this
    pins the behaviour rather than changing it — and the fourth rule is the one
    that matters, because folding *musubi wrote this* and *this did not
    resolve* into one return value turns an abstention into a pass.
    """
    #        0    5    10   15   20
    #        [verbatim][transformed][synthetic]
    mixed = TraceMap(
        artefact_length=18,
        source_length=12,
        segments=(
            Segment(out=Span(0, 6), src=Span(0, 6), kind=Kind.VERBATIM),
            Segment(
                out=Span(6, 12), src=Span(6, 12), kind=Kind.TRANSFORMED, rule="tracking.utm-family"
            ),
            Segment(out=Span(12, 18), src=Span(12, 12), kind=Kind.SYNTHETIC, rule="front-matter"),
        ),
    )

    # Beginning inside a verbatim run: the corresponding position within it.
    assert mixed.source_span_of(Span(2, 5)) == Span(2, 5)

    # Touching a transformed run: the whole of it. Not just from its start --
    # measured, and a correction to the rule as first proposed. A transformation
    # has no correspondence inside it, so the run is the smallest answerable
    # thing.
    assert mixed.source_span_of(Span(8, 10)) == Span(6, 12)

    # Crossing runs: the first resolvable run's start to the last one's end.
    assert mixed.source_span_of(Span(3, 9)) == Span(3, 12)

    # All synthetic: musubi wrote this. The span is empty, and `is_synthetic` on
    # a Resolution is what separates it from "did not resolve" — the two must
    # not arrive as one value.
    assert mixed.source_span_of(Span(13, 17)).is_empty
    assert all(
        segment.kind is Kind.SYNTHETIC for segment in mixed.segments if segment.out.start >= 12
    )


@CORPUS
@given(a_vault())
def test_trace_7_straddling_is_the_normal_case_in_a_real_corpus(
    files: dict[str, bytes],
) -> None:
    """The rule above, against output rather than a fixture.

    Every artefact with front matter already straddles: musubi's own synthetic
    header meets the verbatim body, and any anchor covering the first line of a
    document crosses that boundary. So this is not an edge case waiting for a
    PDF -- it is what a consumer hits on its first query.
    """
    _, into, _ = build(files)
    try:
        for body in maps(into):
            segments = body["segments"]
            if len(segments) < 2:
                continue
            trace = TraceMap(
                artefact_length=body["coverage"]["characters"],
                source_length=max((s["src"][1] for s in segments), default=0),
                segments=tuple(
                    Segment(
                        out=Span(*s["out"]),
                        src=Span(*s["src"]),
                        kind=Kind(s["kind"]),
                        rule=s.get("rule"),
                    )
                    for s in segments
                ),
            )
            resolvable = [s for s in trace.segments if s.kind in {Kind.VERBATIM, Kind.TRANSFORMED}]
            if not resolvable:
                continue

            # A range across the whole artefact spans every resolvable run.
            whole = trace.source_span_of(Span(0, trace.artefact_length))
            assert whole.start <= min(s.src.start for s in resolvable)
            assert whole.end >= max(s.src.end for s in resolvable)

            # A range inside one synthetic run answers with an empty span --
            # `musubi wrote this`, which a reader must not read as a failure.
            for segment in trace.segments:
                if segment.kind is Kind.SYNTHETIC and len(segment.out) > 1:
                    inside = Span(segment.out.start, segment.out.start + 1)
                    assert trace.source_span_of(inside).is_empty
                    break
    finally:
        shutil.rmtree(into.parent, ignore_errors=True)


# -- the sync manifest -------------------------------------------------------


@CORPUS
@given(a_vault())
def test_manifest_1_the_run_id_re_derives(files: dict[str, bytes]) -> None:
    """It is a hash over the canonical form of exactly the inputs; confirming it
    means re-deriving it, which no schema can do."""
    _, into, result = build(files)
    try:
        body = manifest_of(into)
        assert body["run_id"] == hash_of(result.manifest.identity())
        assert body["run_id"] == result.manifest.run_id
    finally:
        shutil.rmtree(into.parent, ignore_errors=True)


@CORPUS
@given(a_vault())
def test_manifest_2_the_coverage_totals_agree(files: dict[str, bytes]) -> None:
    _, into, _ = build(files)
    try:
        coverage = manifest_of(into)["coverage"]
        assert coverage["units_read"] == coverage["emitted"] + coverage["skipped"]
        assert coverage["traceable_characters"] <= coverage["characters"]
    finally:
        shutil.rmtree(into.parent, ignore_errors=True)


@CORPUS
@given(a_vault())
def test_manifest_3_every_record_names_a_unit_the_run_saw(files: dict[str, bytes]) -> None:
    _, into, _ = build(files)
    try:
        body = manifest_of(into)
        seen = {artefact["source"]["unit_key"] for artefact in body["artefacts"]}
        seen |= {skip["origin"] for skip in body["skipped"]}
        for record in body["removals"] + body["findings"]:
            assert record["unit_key"] in seen, record["unit_key"]
    finally:
        shutil.rmtree(into.parent, ignore_errors=True)


@CORPUS
@given(a_vault())
def test_manifest_4_every_artefact_has_a_map_that_is_about_it(
    files: dict[str, bytes],
) -> None:
    """The pairing a schema cannot check, and the one that matters: a map
    carries `artefact.content_hash`, so a reader holding the artefact can
    confirm the map is about the bytes in front of them."""
    _, into, _ = build(files)
    try:
        for artefact in manifest_of(into)["artefacts"]:
            sidecar = into / artefact["trace_map"]
            assert sidecar.is_file(), artefact["trace_map"]
            body = json.loads(sidecar.read_text(encoding="utf-8"))
            assert body["artefact"]["content_hash"] == artefact["content_hash"]
            written = (into / artefact["path"]).read_text(encoding="utf-8")
            assert content_hash(written) == artefact["content_hash"]
    finally:
        shutil.rmtree(into.parent, ignore_errors=True)


# -- and the one the issue named that is not in the list ---------------------


@CORPUS
@given(a_vault())
def test_two_syncs_over_the_same_folder_are_byte_identical(files: dict[str, bytes]) -> None:
    """ADR-0003, at the level a user can see it. This is the property that
    catches an unordered iteration reaching an output, or a wall clock in an id,
    on the commit that introduces it rather than in a confusing diff months
    later."""
    root, first, _ = build(files)
    try:
        second = first.parent / "again"
        sync(
            ObsidianSource(root),
            Settings(
                ruleset=CORE,
                screener=default_screener(),
                converter_for=converter_for,
                musubi_version=__version__,
                created_at="2027-01-01T00:00:00+00:00",
            ),
            DocumentEmitter(second),
        )

        def contents(where: Path) -> dict[str, bytes]:
            return {
                path.relative_to(where).as_posix(): path.read_bytes()
                for path in sorted(where.rglob("*"))
                if path.is_file() and path.name != MANIFEST
            }

        assert contents(first) == contents(second)
        assert manifest_of(first)["run_id"] == manifest_of(second)["run_id"], (
            "the clock differs and the id must not"
        )
    finally:
        shutil.rmtree(first.parent, ignore_errors=True)


@CORPUS
@given(a_vault())
def test_every_key_is_normalized_and_every_artefact_is_lf(files: dict[str, bytes]) -> None:
    """ADR-0014 and ADR-0003 where they meet the disk. A key that is not NFC
    makes one vault into two corpora; an artefact carrying CR makes its bytes
    depend on which machine built it."""
    _, into, _ = build(files)
    try:
        for artefact in manifest_of(into)["artefacts"]:
            key = artefact["source"]["unit_key"]
            assert key == unicodedata.normalize("NFC", key)
            assert "\\" not in key
            assert b"\r" not in (into / artefact["path"]).read_bytes()
    finally:
        shutil.rmtree(into.parent, ignore_errors=True)


@CORPUS
@given(a_vault())
def test_a_map_always_says_what_its_offsets_index(files: dict[str, bytes]) -> None:
    """ADR-0018. A future locator is a different value, and an old reader
    refusing it is the intended behaviour rather than a gap."""
    _, into, _ = build(files)
    try:
        for body in maps(into):
            assert body["source_unit"] == CHARACTERS
    finally:
        shutil.rmtree(into.parent, ignore_errors=True)


# -- the list and its executable form cannot drift ---------------------------


def _enumerated(heading: str) -> int:
    """How many invariants `docs/contracts.md` enumerates under this heading."""
    body = CONTRACTS.read_text(encoding="utf-8")
    start = body.index(heading) + len(heading)
    section = body[start:]
    end = section.find("\n### ")
    if end == -1:
        end = section.find("\n## ")
    return len(re.findall(r"^\d+\. \*\*", section[:end], re.MULTILINE))


def _tests_named(prefix: str) -> set[int]:
    source = Path(__file__).read_text(encoding="utf-8")
    return {int(n) for n in re.findall(rf"^def {prefix}_(\d+)_", source, re.MULTILINE)}


@pytest.mark.parametrize(
    ("heading", "prefix"),
    [("### The trace map", "test_trace"), ("### The sync manifest", "test_manifest")],
)
def test_every_enumerated_invariant_has_a_test(heading: str, prefix: str) -> None:
    """A schema handed over as "the contract" is read as the whole of it, and
    `docs/contracts.md` says what the schemas do not check. An enumeration
    nobody runs hands a consumer "written down but never checked", so the list
    growing an entry turns this red."""
    enumerated = _enumerated(heading)
    assert enumerated, f"found no numbered invariants under {heading!r}"
    assert _tests_named(prefix) == set(range(1, enumerated + 1)), (
        f"docs/contracts.md enumerates {enumerated} invariants under {heading!r}; "
        f"this file has tests for {sorted(_tests_named(prefix))}"
    )
