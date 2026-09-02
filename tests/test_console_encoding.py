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

#: Enough to be unencodable in `cp932`: the em dash musubi prints in every
#: heading, and a filename in a script the codec does hold.
NOTE = "# 設計メモ\n\nテントは 2.4kg。\n"


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
