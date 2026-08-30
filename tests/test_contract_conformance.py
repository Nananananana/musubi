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
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from musubi import __version__
from musubi.application.pipeline import Settings, run
from musubi.domain.manifest import render
from musubi.domain.trace import Kind
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.emitters import MANIFEST, TRACES, DocumentEmitter
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
