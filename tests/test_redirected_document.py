"""The path no other test in this repository takes: a real process, redirected.

`tests/test_console_encoding.py` patches `sys.stdout` with a narrow wrapper, which
exercises the *console* path — the one ADR-0020 was written for. **A redirect is a
different path.** Python picks the locale encoding for a redirected stream, not
the console's, and the two are configured separately.

`akashi` found the difference the expensive way: `akashi audit --json > report.json`
wrote `cp932`, which is not valid JSON by RFC 8259, and its own `recheck` and
`explain` refused the file. **It wrote a document it could not read**, because the
rule lived in the reading side's docstring and nobody had written one for the
writing side.

musubi does not have that bug — `_document()` writes UTF-8 bytes to
`stdout.buffer` and never touches a codec. **Nothing here said so**, because
nothing here started a process. These tests do.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

NOTE = "# 見出し — an em dash and 日本語\n\nhttps://x.test/p?utm_source=z\n"


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "設計メモ.md").write_text(NOTE, encoding="utf-8", newline="\n")
    return root


def legacy() -> dict[str, str]:
    """An environment that does *not* force UTF-8, the way a user's shell is.

    `PYTHONUTF8` and `PYTHONIOENCODING` are cleared because this repository's own
    tooling sets them, and a test that inherited them would be measuring the
    harness. `PYTHONLEGACYWINDOWSSTDIO` takes the locale path on Windows and is
    ignored elsewhere.
    """
    environment = dict(os.environ)
    environment.pop("PYTHONUTF8", None)
    environment.pop("PYTHONIOENCODING", None)
    environment["PYTHONLEGACYWINDOWSSTDIO"] = "1"
    return environment


def redirected(arguments: list[str], into: Path) -> tuple[int, bytes]:
    """Run the installed command with stdout going to a file, not a terminal."""
    with into.open("wb") as sink:
        code = subprocess.call(  # noqa: S603 - every argument here is this test's own
            [
                sys.executable,
                "-c",
                "from musubi.interfaces.cli.main import main; raise SystemExit(main())",
                *arguments,
            ],
            stdout=sink,
            stderr=subprocess.PIPE,
            env=legacy(),
        )
    return code, into.read_bytes()


# -- a document is UTF-8 wherever it is sent --------------------------------


@pytest.mark.parametrize("command", ["plan", "sync"])
def test_a_redirected_manifest_is_utf8_and_parses(
    tmp_path: Path, vault: Path, command: str
) -> None:
    """RFC 8259: JSON is UTF-8. A file that is not is not a manifest, however
    plausible it looks and whatever exit code was returned."""
    out = tmp_path / "manifest.json"
    arguments = [command, str(vault), "--json"]
    if command == "sync":
        arguments += ["--into", str(tmp_path / "synced")]

    code, raw = redirected(arguments, out)

    assert code == 0, "the run itself must succeed before the bytes mean anything"
    assert raw, "nothing was written, so this test is measuring nothing"
    body = json.loads(raw.decode("utf-8"))
    assert body["contract"].startswith("musubi.sync-manifest/1")


def test_the_japanese_in_a_redirected_document_survives(tmp_path: Path, vault: Path) -> None:
    """The characters that a `cp932` console replaces with `?`. In a document
    they must arrive intact, because the reader is a program."""
    code, raw = redirected(["plan", str(vault), "--json"], tmp_path / "out.json")

    assert code == 0
    assert "設計メモ".encode() in raw, "the unit key was written through a codec"
    assert b"\xef\xbf\xbd" not in raw, "a replacement character reached the document"


def test_a_redirected_trace_answer_is_utf8(tmp_path: Path, vault: Path) -> None:
    into = tmp_path / "synced"
    code, _ = redirected(["sync", str(vault), "--into", str(into)], tmp_path / "report.txt")
    assert code == 0

    artefact = into / "documents" / "設計メモ.md"
    at = artefact.read_text(encoding="utf-8").index("見出し")
    code, raw = redirected(
        ["trace", f"{artefact}:{at}-{at + 3}", "--json"], tmp_path / "trace.json"
    )

    assert code == 0
    assert json.loads(raw.decode("utf-8"))["excerpt"] == "見出し"


# -- and the corpus on the disk ---------------------------------------------


def test_every_file_a_sync_writes_is_utf8_with_lf(tmp_path: Path, vault: Path) -> None:
    """What `docs/contracts.md` promises under *What encoding these are in*.

    A corpus written in the producing machine's locale would have offsets that
    mean different things on different machines, and every map in it would still
    validate.
    """
    into = tmp_path / "synced"
    code, _ = redirected(["sync", str(vault), "--into", str(into)], tmp_path / "report.txt")
    assert code == 0

    written = sorted(p for p in into.rglob("*") if p.is_file())
    assert written, "the sync wrote nothing, so this test is measuring nothing"
    for path in written:
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as error:
            pytest.fail(f"{path.name} is not UTF-8: {error}")
        assert b"\r\n" not in raw, f"{path.name} carries CRLF"
        assert not raw.startswith(b"\xef\xbb\xbf"), f"{path.name} starts with a byte-order mark"
