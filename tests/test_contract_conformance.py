"""The two contracts, checked against what musubi actually writes.

**Against real output, and never against a document assembled in a test.** The
`tsumugi` project shipped a frozen contract and a reference producer, and had
never once validated its own real output against its own schema -- the test
helpers built packages by hand and validated those. The first run over genuine
output found a genuine bug: a default that was the empty string where the
contract said `minLength: 1`, so every package built through the library API was
non-conformant and nobody had looked. So the fixtures here come off a disk that
the real emitter wrote to, and the manifest comes out of the real command.

**And the schema is not the contract.** JSON Schema 2020-12 cannot compare two
properties of one object, so `end >= start` is beyond it -- and the invariant a
trace map exists for, that the segments cover every character of the artefact
exactly once, is far beyond it. Those live in `tests/test_trace_map.py` and in
the invariants of #12. `docs/contracts.md` says so where a consumer will read it,
because a schema handed over as "the contract" is read as the whole of it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from musubi import __version__
from musubi.application.pipeline import Settings, run
from musubi.domain.manifest import render
from musubi.domain.trace import Kind
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.emitters import DOCUMENTS, MANIFEST, TRACES, DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import ObsidianSource
from musubi.interfaces.cli import main
from musubi.schemas import path_to, schemas

ROOT = Path(__file__).resolve().parent.parent
#: Loaded the way `docs/contracts.md` tells a consumer to load them, so the
#: published instruction is exercised rather than only published (ADR-0023).
SCHEMAS = schemas()
CONTRACTS = Path(__file__).resolve().parent / "contracts"

TRACE_MAP = path_to("musubi.trace-map/1")
SYNC_MANIFEST = path_to("musubi.sync-manifest/1")

#: A note with everything a document can have: its own front matter, a heading,
#: CJK text whose characters are not its bytes, a tracking parameter to remove,
#: and CRLF line endings from whichever machine wrote it.
NOTE = (
    "---\r\n"
    "tags: [camping]\r\n"
    "---\r\n"
    "\r\n"
    "# テント設計メモ\r\n"
    "\r\n"
    "テントは 2.4kg。\r\n"
    "\r\n"
    "参考: https://example.com/gear?utm_source=newsletter&id=7\r\n"
)


def validator(schema: Path) -> Draft202012Validator:
    body = json.loads(schema.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(body)
    return Draft202012Validator(body)


def corpus(tmp_path: Path) -> Path:
    """A real sync, end to end: the emitter writes and promotes to a disk."""
    root = tmp_path / "vault"
    (root / "design").mkdir(parents=True)
    (root / "design" / "gear.md").write_text(NOTE, encoding="utf-8", newline="")
    (root / "plain.txt").write_text("just text\n", encoding="utf-8")
    (root / "photo.png").write_bytes(b"x")

    destination = tmp_path / "synced"
    emitter = DocumentEmitter(destination)
    emitter.begin()
    settings = Settings(
        ruleset=CORE,
        screener=default_screener(),
        converter_for=converter_for,
        musubi_version=__version__,
        created_at="2026-08-30T00:00:00+00:00",
    )
    outcome = run(ObsidianSource(root), settings, emitter, write=True)
    emitter.stage_manifest(render(outcome.manifest))
    emitter.promote()
    return destination


# -- the schemas themselves -------------------------------------------------


@pytest.mark.parametrize("schema", [TRACE_MAP, SYNC_MANIFEST], ids=lambda p: p.name)
def test_the_schema_is_a_schema(schema: Path) -> None:
    validator(schema)


@pytest.mark.parametrize("schema", [TRACE_MAP, SYNC_MANIFEST], ids=lambda p: p.name)
def test_the_schema_says_it_describes_shape_only(schema: Path) -> None:
    """A schema handed over as "the contract" is read as the whole of it, and
    the most important invariant of each of these is not in it."""
    body = json.loads(schema.read_text(encoding="utf-8"))
    assert "SHAPE ONLY" in body["description"]
    assert "docs/contracts.md" in body["description"]


# -- against what the emitter actually wrote --------------------------------


def test_every_trace_map_the_emitter_wrote_conforms(tmp_path: Path) -> None:
    check = validator(TRACE_MAP)
    written = sorted((corpus(tmp_path) / TRACES).rglob("*.json"))
    assert written, "the fixture produced no maps, so this test measures nothing"
    for path in written:
        check.validate(json.loads(path.read_text(encoding="utf-8")))


def test_the_manifest_the_emitter_wrote_conforms(tmp_path: Path) -> None:
    check = validator(SYNC_MANIFEST)
    body = json.loads((corpus(tmp_path) / MANIFEST).read_text(encoding="utf-8"))
    check.validate(body)
    assert body["kind"] == "sync"


def test_the_manifest_the_command_printed_conforms(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other surface a consumer meets, and the one `tsumugi` had never
    checked: the document that comes out of the real command."""
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "vault"
    root.mkdir()
    (root / "a.md").write_text(NOTE, encoding="utf-8", newline="")

    assert main(["plan", str(root), "--json"]) == 0
    body = json.loads(capsys.readouterr().out)
    validator(SYNC_MANIFEST).validate(body)
    assert body["kind"] == "plan"


def test_a_manifest_with_nothing_in_it_still_conforms(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty folder is a real input, and a contract that only accepts the
    happy shape is a contract that breaks on the first quiet day."""
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "empty"
    root.mkdir()
    assert main(["plan", str(root), "--json"]) == 0
    validator(SYNC_MANIFEST).validate(json.loads(capsys.readouterr().out))


def test_the_real_output_carries_the_things_the_schema_cannot_check(tmp_path: Path) -> None:
    """Conformance is not enough, so this asserts the parts a schema cannot: the
    segments tile the artefact, and the coverage totals agree with them."""
    for path in sorted((corpus(tmp_path) / TRACES).rglob("*.json")):
        body = json.loads(path.read_text(encoding="utf-8"))
        at = 0
        traceable = 0
        for segment in body["segments"]:
            assert segment["out"][0] == at, f"{path.name}: a gap or an overlap at {at}"
            assert segment["out"][1] >= segment["out"][0], f"{path.name}: a backwards span"
            assert segment["src"][1] >= segment["src"][0], f"{path.name}: a backwards span"
            if segment["kind"] in {"verbatim", "transformed"}:
                traceable += segment["out"][1] - segment["out"][0]
            at = segment["out"][1]
        assert at == body["coverage"]["characters"], f"{path.name}: the tiling stops short"
        assert traceable == body["coverage"]["traceable"]


def test_a_removal_in_the_real_manifest_carries_a_hash_and_not_a_value(tmp_path: Path) -> None:
    """ADR-0005 made machine-checkable at the seam: the schema refuses a
    manifest carrying a removed value, and this checks the real one has none."""
    body = (corpus(tmp_path) / MANIFEST).read_text(encoding="utf-8")
    assert "newsletter" not in body, "the removed value must not reach the manifest"
    assert "removed_sha256" in body


# -- and the fixtures a third party can read --------------------------------


@pytest.mark.parametrize(
    ("fixture", "schema"),
    [
        ("trace-map-valid.json", TRACE_MAP),
        ("sync-manifest-valid.json", SYNC_MANIFEST),
    ],
)
def test_the_published_example_conforms(fixture: str, schema: Path) -> None:
    """Committed real output, so that somebody writing a consumer has a document
    to write it against rather than a docstring to write it from."""
    validator(schema).validate(json.loads((CONTRACTS / fixture).read_text(encoding="utf-8")))


def test_a_document_with_an_added_field_cannot_pass_as_this_contract(tmp_path: Path) -> None:
    """The executable form of the versioning rule (ADR-0024).

    `additionalProperties: false` means a field added inside `/1` is refused by
    every consumer holding the older schema -- and refused with the same
    `ValidationError` a malformed document produces. Those need opposite
    responses, refresh or refuse, and one exception cannot carry both.

    So an addition takes a new identifier, and this is what makes that the only
    coherent rule: the schema itself will not let a wider document pass as `/1`,
    so there is no version of "add it quietly" that works.
    """
    body = json.loads(_real_manifest(tmp_path).read_text(encoding="utf-8"))
    assert validator(SYNC_MANIFEST).is_valid(body), "a real manifest should validate"

    widened = {**body, "corpus_bytes": 1234}
    assert not validator(SYNC_MANIFEST).is_valid(widened), (
        "a field added inside /1 validated against /1. `additionalProperties: false` "
        "is what makes 'additions take a new identifier' enforceable rather than "
        "merely written down."
    )


def test_being_out_of_date_is_reported_before_validation(tmp_path: Path) -> None:
    """The identifier check is the signal that says *refresh me*.

    A consumer's first step is to check `contract` and refuse what it does not
    recognise -- and that happens before any validator runs, which is what keeps
    it distinguishable from a document that is simply wrong.
    """
    body = json.loads(_real_manifest(tmp_path).read_text(encoding="utf-8"))
    future = {**body, "contract": "musubi.sync-manifest/2"}
    pattern = json.loads(SYNC_MANIFEST.read_text(encoding="utf-8"))["properties"]["contract"]
    assert not re.match(pattern["pattern"], future["contract"]), (
        "the /1 schema accepts a /2 identifier, so the two signals collapse again"
    )

    # And the document it appears in is refused, so a consumer that skipped
    # step 1 still does not read a /2 as though it were a /1.
    assert not validator(SYNC_MANIFEST).is_valid(future)


def _real_manifest(tmp_path: Path) -> Path:
    """A manifest a real sync wrote, not one a test assembled."""
    import contextlib
    import io

    from musubi.interfaces.cli.main import main

    root, into = tmp_path / "vault", tmp_path / "synced"
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.md").write_text("# a\n", encoding="utf-8", newline="\n")
    with contextlib.redirect_stdout(io.StringIO()):
        main(["sync", str(root), "--into", str(into)])
    return into / "manifest.json"


def test_the_layout_the_contract_promises_is_the_layout_the_emitter_writes() -> None:
    """`docs/contracts.md` names three paths and a consumer depends on them.

    They are part of `musubi.sync-manifest/1` rather than a separate thing to
    check, so moving one is a contract change (ADR-0024). Nothing enforced the
    document against the code, which means a rename would have left the contract
    describing a layout musubi no longer writes -- and the consumer discovering
    it as a missing file rather than as a version it does not recognise.
    """
    from musubi.infrastructure.emitters import DOCUMENTS, MANIFEST, TRACES

    said = (Path(__file__).resolve().parent.parent / "docs" / "contracts.md").read_text(
        encoding="utf-8"
    )
    for name, value in (("documents", DOCUMENTS), ("traces", TRACES), ("manifest", MANIFEST)):
        assert f"`<destination>/{value}" in said or f"`{value}`" in said, (
            f"the emitter writes {value!r} for {name} and docs/contracts.md does not "
            f"say so. A consumer reading the contract would look in the wrong place."
        )


def test_an_artefact_path_is_documents_plus_its_unit_key(tmp_path: Path) -> None:
    """The relationship the whole downstream chain rests on, and nothing pinned it.

    `kiseki-notes` hashes the corpus-relative path to make a note's stable
    reference, so that reference is a *function of* `unit_key` rather than a
    second thing that could break independently. There is one degree of freedom
    in the chain and it is musubi's key -- which is only true while this holds.

    Break it, by putting a source's name or a date into the output path, and a
    consumer's references move for a reason `key_derivation` does not describe
    and nothing announces.
    """
    manifest = _real_manifest(tmp_path)
    body = json.loads(manifest.read_text(encoding="utf-8"))
    assert body["artefacts"], "the fixture should have produced an artefact"
    for artefact in body["artefacts"]:
        expected = f"{DOCUMENTS}/{artefact['source']['unit_key']}"
        assert artefact["path"] == expected, (
            f"the manifest puts it at {artefact['path']!r}, not {expected!r}. A consumer "
            f"identifying documents by path no longer inherits key_derivation."
        )
        # And on the disk, not only in the manifest's own account of itself.
        # Checking the manifest against the manifest would pass with the file
        # written somewhere else entirely -- measured.
        assert (manifest.parent / expected).is_file(), (
            f"the manifest says {expected!r} and nothing is there"
        )


def _refusals(prefix: str) -> list[Path]:
    found = sorted(CONTRACTS.glob(f"{prefix}-invalid-*.json"))
    assert found, f"no {prefix} counter-examples; a schema nothing fails is a schema"
    return found


@pytest.mark.parametrize("fixture", _refusals("trace-map"), ids=lambda p: p.stem)
def test_a_trace_map_counter_example_is_refused(fixture: Path) -> None:
    body: Any = json.loads(fixture.read_text(encoding="utf-8"))
    assert not validator(TRACE_MAP).is_valid(body), f"{fixture.name} should not validate"


@pytest.mark.parametrize("fixture", _refusals("sync-manifest"), ids=lambda p: p.stem)
def test_a_sync_manifest_counter_example_is_refused(fixture: Path) -> None:
    body: Any = json.loads(fixture.read_text(encoding="utf-8"))
    assert not validator(SYNC_MANIFEST).is_valid(body), f"{fixture.name} should not validate"


# -- the schema and the code, kept in step ----------------------------------


def test_the_segment_kinds_have_not_drifted_apart() -> None:
    """There is no pydantic here (ADR-0001), so the schema and the enum are two
    statements of one fact and a test is what keeps them one."""
    body = json.loads(TRACE_MAP.read_text(encoding="utf-8"))
    declared = set(body["$defs"]["segment"]["properties"]["kind"]["enum"])
    assert declared == {kind.value for kind in Kind}


def test_the_layers_musubi_will_emit_have_not_drifted_apart() -> None:
    """ADR-0010, made machine-checkable: `interpretation` is not in the schema,
    so a manifest claiming one is refused by the contract and not only by the
    code."""
    body = json.loads(SYNC_MANIFEST.read_text(encoding="utf-8"))
    declared = set(body["$defs"]["artefact"]["properties"]["layer"]["enum"])
    assert declared == {"fact", "measure"}
    assert "interpretation" not in declared


def test_the_contract_strings_in_the_code_are_the_ones_the_schemas_accept() -> None:
    from musubi.domain.manifest import CONTRACT
    from musubi.infrastructure.emitters import TRACE_CONTRACT

    manifest_schema = json.loads(SYNC_MANIFEST.read_text(encoding="utf-8"))
    trace_schema = json.loads(TRACE_MAP.read_text(encoding="utf-8"))

    import re

    assert re.match(manifest_schema["properties"]["contract"]["pattern"], CONTRACT)
    assert re.match(trace_schema["properties"]["contract"]["pattern"], TRACE_CONTRACT)


def test_a_source_unit_the_schema_does_not_know_is_refused() -> None:
    """ADR-0018 kept the field so that an old reader can *see* a locator it does
    not understand. Refusing is the intended behaviour, not a gap."""
    body = json.loads((CONTRACTS / "trace-map-valid.json").read_text(encoding="utf-8"))
    body["source_unit"] = "opaque"
    assert not validator(TRACE_MAP).is_valid(body)
