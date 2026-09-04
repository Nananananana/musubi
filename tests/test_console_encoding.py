"""The console's encoding is not the contract's, and cannot fail a run.

ADR-0020, from a bug the `seam` session found on Japanese Windows: `musubi sync`
returned 1 with the corpus fully written, because a `cp932` console could not
encode an em dash in a heading. The exit code said nothing was written and the
destination was full — the shape of a violation of ADR-0008's central promise,
while being its opposite.

Looking for the same fault elsewhere found a worse one: `--json` did not crash,
it emitted a document that was not valid UTF-8, with exit 0 and no error.

**These tests are the reason this class of bug does not need a Japanese machine
to find.** They are invisible on a UTF-8 developer box, which is why the bug
reached a user before a test.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from musubi.infrastructure.emitters import DOCUMENTS, MANIFEST, TRACES
from musubi.interfaces.cli import main

#: A note whose text a `cp932` console genuinely cannot show.
#:
#: The comment that stood here said *enough to be unencodable in cp932*, and
#: that was true of the em dash **musubi** prints and false of the note itself.
#: A claim about the fixture that the fixture did not have.
#:
#: The previous fixture was `設計メモ` and `テントは 2.4kg。`, and **every
#: character in it round-trips through cp932** -- so this whole file would have
#: passed with musubi's encoding handling deleted. Measured, and the same shape
#: `seam`, `kiseki`, `mamori` and `tsumugi` each found in their own fixtures on
#: the same day: Japanese text is *usually* representable in cp932, which is
#: exactly what makes it a comfortable and useless sample.
#:
#: `𩸽` is U+29E3D, a fish, outside cp932's repertoire and outside the basic
#: multilingual plane. It is a real character a real note can contain.
NOTE = "# 設計メモ 𩸽\n\nテントは 2.4kg。\n"


def beyond_cp932(text: str) -> set[str]:
    """The characters in `text` that cp932 cannot represent."""
    unrepresentable = set()
    for character in text:
        try:
            if character.encode("cp932").decode("cp932") != character:
                unrepresentable.add(character)
        except (UnicodeEncodeError, UnicodeDecodeError):
            unrepresentable.add(character)
    return unrepresentable


def test_the_fixture_can_actually_break_a_cp932_console() -> None:
    """The guard `seam` put in front of its own suite, and the reason for it.

    Every other test in this file narrows a console and asserts musubi survives.
    **All of them pass on a fixture cp932 can represent**, because then there is
    nothing for the encoding handling to do -- and the previous fixture here was
    exactly that: `設計メモ` and `テントは 2.4kg。` round-trip through cp932
    without a mark.

    So this asserts the population has teeth, and it comes *first* in the file
    on purpose. `seam`'s reason: printing nine passes and then a caveat means the
    reader takes the number.
    """
    doomed = beyond_cp932(NOTE)
    assert doomed, (
        "every character in NOTE survives a cp932 round trip, so every test below "
        "would pass with musubi's encoding handling removed"
    )
    assert "𩸽" in doomed, "the fixture lost the character chosen to break cp932"


class Narrow(io.TextIOWrapper):
    """A stream with a codec that cannot hold what musubi is about to print.

    A real one: `cp932` is the console default on every un-reconfigured Japanese
    Windows, and it has no em dash.
    """

    def __init__(self) -> None:
        self.raw_buffer = io.BytesIO()
        super().__init__(self.raw_buffer, encoding="cp932", newline="")

    def written(self) -> bytes:
        self.flush()
        return self.raw_buffer.getvalue()


def narrow_console(monkeypatch: pytest.MonkeyPatch) -> Narrow:
    """Put a narrow console in front of the CLI, from inside the test body.

    Deliberately not a fixture. pytest suspends its capture for fixture setup
    and **resumes it for the call phase**, which reinstates its own object as
    `sys.stdout` -- so a patch made during setup is silently undone, the tests
    pass under `-s` and fail without it, and what is being measured is pytest
    rather than musubi.
    """
    stream = Narrow()
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", stream)
    return stream


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "vault"
    root.mkdir()
    (root / "設計メモ.md").write_text(NOTE, encoding="utf-8")
    return root


# -- the exit code reports the run ------------------------------------------


def test_a_sync_that_wrote_everything_returns_zero(
    tmp_path: Path, vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bug, exactly. The corpus was complete and the exit code said it was
    not, because a heading would not print."""
    narrow_console(monkeypatch)
    into = tmp_path / "corpus"
    code = main(["sync", str(vault), "--into", str(into)])

    assert code == 0
    assert (into / DOCUMENTS / "設計メモ.md").is_file()
    assert (into / TRACES / "設計メモ.md.json").is_file()
    assert (into / MANIFEST).is_file()


def test_a_plan_still_reports_on_a_console_that_cannot_show_it(
    vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    console = narrow_console(monkeypatch)
    assert main(["plan", str(vault)]) == 0
    assert b"musubi plan" in console.written()


def test_a_trace_still_answers_on_a_console_that_cannot_show_it(
    tmp_path: Path, vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    console = narrow_console(monkeypatch)
    into = tmp_path / "corpus"
    main(["sync", str(vault), "--into", str(into)])
    artefact = into / DOCUMENTS / "設計メモ.md"
    at = artefact.read_text(encoding="utf-8").index("2.4kg")

    assert main(["trace", f"{artefact}:{at}-{at + 5}"]) == 0
    assert b"verbatim" in console.written()


def test_a_verify_still_reports_on_a_console_that_cannot_show_it(
    tmp_path: Path, vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`verify` landed after ADR-0020 and was not covered by any of this.

    It survives -- `_readable()` reconfigures the streams for every command, so
    the em dash in its heading is substituted rather than fatal -- but nothing
    here said so, and a guard that does not cover the newest command is the
    shape this repository keeps finding. Measured before writing it: exit 0,
    and the heading arrives as `musubi verify ? ...`.
    """
    console = narrow_console(monkeypatch)
    into = tmp_path / "corpus"
    main(["sync", str(vault), "--into", str(into)])

    assert main(["verify", str(into)]) == 0
    shown = console.written().decode("cp932")
    assert "musubi verify" in shown
    assert "—" not in shown, "the em dash could not be encoded and was substituted"


def test_a_config_still_reports_on_a_console_that_cannot_show_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fifth command, and the first one the guard below caught.

    `verify` was added after ADR-0020 and nothing here narrowed a console at it;
    that was found by hand and the guard was written afterwards. `config` was
    added after the guard, and the guard turned red on the commit that added it
    -- which is the whole of what it was for.

    The path is printed, so a settings file under a Japanese folder name is
    exactly the case: the value is a path this console cannot spell.
    """
    console = narrow_console(monkeypatch)
    folder = tmp_path / "設計 𩸽"
    folder.mkdir()
    (folder / "musubi.toml").write_text('into = "corpus"\n', encoding="utf-8")
    monkeypatch.chdir(folder)

    assert main(["config"]) == 0
    assert b"musubi config" in console.written()


def test_an_export_still_writes_a_document_on_a_console_that_cannot_show_it(
    tmp_path: Path, vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sixth command, and the guard's second catch.

    `export` writes a *document*, so the failure it can have is the worse of the
    two ADR-0020 names: not a crash, but a file that is not valid UTF-8 with
    exit 0 and no error anywhere. The report goes to standard error and the
    document to the buffer beneath standard output, so a narrow console costs a
    glyph in the report and nothing at all in the file.
    """
    console = narrow_console(monkeypatch)
    into = tmp_path / "corpus"
    main(["sync", str(vault), "--into", str(into)])
    console.flush()
    console.raw_buffer.truncate(0)
    console.raw_buffer.seek(0)

    assert main(["export", str(into)]) == 0
    written = console.written()
    document, _, report = written.partition(b"musubi export")
    assert document, "nothing was written"
    body = json.loads(document.decode("utf-8"))
    assert body["text"].endswith(NOTE), "the document did not survive the console"
    assert report, "the report was not printed at all"


def test_the_mcp_server_speaks_utf8_whatever_the_console_is(
    tmp_path: Path, vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seventh command, and the guard's third catch.

    `mcp` is the worst case ADR-0020 describes rather than the mild one. A
    protocol stream that lost a character is not a glyph missing from a report
    -- it is JSON a client cannot parse, or worse, JSON it *can* parse with a
    document quietly mangled inside it. The server writes to the stream it is
    handed, so this hands it one that cannot encode the note.
    """
    console = narrow_console(monkeypatch)
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "musubi_convert", "arguments": {"path": "設計メモ.md"}},
    }
    # Through `main`, with a real stdin, rather than by calling `serve`: the
    # guard below asks whether the **command** was exercised, and a test that
    # reached past the command would satisfy the letter of it while leaving
    # `_readable()` and the argument parsing uncovered.
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request) + "\n"))
    assert main(["mcp", str(vault)]) == 0

    answer = json.loads(console.written().decode("utf-8"))
    body = json.loads(answer["result"]["content"][0]["text"])
    assert NOTE.strip() in body["text"], "the document did not survive the round trip"


def test_a_log_names_files_a_narrow_console_cannot_show(
    tmp_path: Path, vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`log` prints filenames, which is a harder case than a heading.

    An em dash is musubi's own character and could in principle be avoided. A
    path is the owner's, and this one is `𩸽.md` -- so the guarantee being
    tested is the one ADR-0020 actually makes, that a console cannot fail a run
    over *other people's* text.
    """
    (vault / "𩸽.md").write_text(NOTE, encoding="utf-8")
    into = tmp_path / "corpus"
    assert main(["sync", str(vault), "--into", str(into)]) == 0

    stream = narrow_console(monkeypatch)
    assert main(["log", str(into)]) == 0

    shown = stream.written().decode("cp932")
    assert "runs" in shown
    assert ".md" in shown, "the report named no file at all"


def test_a_diff_reports_on_a_console_that_cannot_show_it(
    tmp_path: Path, vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (vault / "𩸽.md").write_text(NOTE, encoding="utf-8")
    into = tmp_path / "corpus"
    assert main(["sync", str(vault), "--into", str(into)]) == 0
    (vault / "𩸽.md").unlink()
    assert main(["sync", str(vault), "--into", str(into)]) == 0

    stream = narrow_console(monkeypatch)
    assert main(["diff", str(into)]) == 0
    assert "removed" in stream.written().decode("cp932")


def test_a_log_as_a_document_is_utf8_whatever_the_console_is(
    tmp_path: Path, vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worse half of ADR-0020: `--json` did not crash, it wrote a document
    that was not valid UTF-8, with exit 0 and nothing in the report."""
    (vault / "𩸽.md").write_text(NOTE, encoding="utf-8")
    into = tmp_path / "corpus"
    assert main(["sync", str(vault), "--into", str(into)]) == 0

    stream = narrow_console(monkeypatch)
    assert main(["log", str(into), "--json"]) == 0

    body = json.loads(stream.written().decode("utf-8"))
    assert any("𩸽" in path for path in body[0]["added"]), (
        "the document lost the character that a cp932 console cannot hold"
    )


def test_every_command_the_parser_knows_is_exercised_here() -> None:
    """The drift guard, and the reason this file needs one.

    ADR-0020 is about *the console never failing a run*, which is a promise
    about musubi and not about the three commands that happened to exist when it
    was written. A fourth was added and this file did not notice. So the
    subcommands are read out of the parser rather than remembered, and adding a
    fifth turns this red until somebody points a narrow console at it.
    """
    from musubi.interfaces.cli.main import COMMANDS

    assert COMMANDS, "found no subcommands; this guard is measuring nothing"
    known = set(COMMANDS)

    source = Path(__file__).read_text(encoding="utf-8")
    missing = sorted(name for name in known if f'main(["{name}"' not in source)
    assert not missing, (
        f"{missing} print to a console this file never narrows. ADR-0020 promises the "
        f"console cannot fail a run, and that promise is per command."
    )


def test_what_cannot_be_shown_is_replaced_rather_than_fatal(
    vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Losing a glyph is a smaller failure than losing the report, and the
    manifest carries the exact name for anybody who needs it."""
    console = narrow_console(monkeypatch)
    assert main(["plan", str(vault)]) == 0
    shown = console.written().decode("cp932")
    assert "musubi plan" in shown
    assert "—" not in shown, "the em dash could not be encoded and was substituted"


# -- a document is UTF-8, whatever the console is ---------------------------


def a_document(stream: Narrow) -> dict[str, object]:
    """What a caller piping the output gets, decoded as JSON says it must be."""
    body: dict[str, object] = json.loads(stream.written().decode("utf-8"))
    return body


def test_a_manifest_is_utf8_on_a_console_that_is_not(
    vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It used to be encoded in whatever the console happened to be, with exit 0
    and no error: no warning, and a file full of plausible nonsense."""
    console = narrow_console(monkeypatch)
    assert main(["plan", str(vault), "--json"]) == 0
    body = a_document(console)
    artefacts = body["artefacts"]
    assert isinstance(artefacts, list)
    assert artefacts[0]["source"]["unit_key"] == "設計メモ.md"


def test_a_sync_manifest_is_utf8_on_a_console_that_is_not(
    tmp_path: Path, vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    console = narrow_console(monkeypatch)
    assert main(["sync", str(vault), "--into", str(tmp_path / "corpus"), "--json"]) == 0
    assert a_document(console)["kind"] == "sync"


def test_a_trace_answer_is_utf8_on_a_console_that_is_not(
    tmp_path: Path, vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    console = narrow_console(monkeypatch)
    into = tmp_path / "corpus"
    main(["sync", str(vault), "--into", str(into)])
    console.flush()
    console.raw_buffer.truncate(0)
    console.raw_buffer.seek(0)

    artefact = into / DOCUMENTS / "設計メモ.md"
    at = artefact.read_text(encoding="utf-8").index("テントは")
    assert main(["trace", f"{artefact}:{at}-{at + 4}", "--json"]) == 0

    body = a_document(console)
    assert body["excerpt"] == "テントは"


def test_the_document_and_the_report_do_not_get_mixed_up(
    vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--json` writes to the buffer beneath the stream, so anything the report
    already wrote has to be flushed first or it arrives after."""
    console = narrow_console(monkeypatch)
    assert main(["plan", str(vault), "--json"]) == 0
    raw = console.written()
    assert raw.startswith(b"{"), raw[:40]
    assert raw.rstrip().endswith(b"}")


# -- and a stream that cannot be reconfigured at all ------------------------


def test_a_stream_with_no_reconfigure_does_not_stop_the_run(
    tmp_path: Path, vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not every stdout is a TextIOWrapper. Something that cannot be told to
    substitute is left alone rather than being an error in its own right."""

    class Plain(io.StringIO):
        buffer = io.BytesIO()

    monkeypatch.setattr(sys, "stdout", Plain())
    monkeypatch.setattr(sys, "stderr", Plain())
    assert main(["plan", str(vault)]) == 0
