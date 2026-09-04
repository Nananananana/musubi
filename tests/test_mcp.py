"""The agent-facing surface, and the boundary that makes it safe to expose.

An MCP server is the one place a program somebody else is driving hands musubi
paths. Most of these are therefore about **refusal**: what the server will not
read, will not write, and will not return.

The one that is not about refusal is the last: convert, then trace, in one
session. That is the whole reason to expose musubi to an agent rather than a
`bytes -> str` converter, and if it stops working the server has no purpose.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from musubi.interfaces.mcp import PROTOCOL, TOOLS, OutsideRootError, Server, serve

NOTE = "# ギア設計\n\nテントは 2.4kg。https://example.test/a?utm_source=x\n"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "gear.md").write_text(NOTE, encoding="utf-8")
    return tmp_path


def talk(root: Path, *messages: dict[str, Any]) -> list[dict[str, Any]]:
    """Drive the server the way a client does: one JSON object per line."""
    written = io.StringIO()
    serve(root, stream=io.StringIO("\n".join(json.dumps(m) for m in messages) + "\n"), out=written)
    return [json.loads(line) for line in written.getvalue().splitlines()]


def call(root: Path, tool: str, **arguments: Any) -> dict[str, Any]:
    (answer,) = talk(
        root,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        },
    )
    result: dict[str, Any] = answer["result"]
    return result


def body(result: dict[str, Any]) -> Any:
    return json.loads(result["content"][0]["text"])


# -- the wire ---------------------------------------------------------------


def test_both_protocol_generations_are_answered(root: Path) -> None:
    """`initialize` is what every deployed client sends; `server/discover` is
    the 2026-07-28 revision, which removed the handshake.

    A server speaking only the newer one is unusable today and one speaking only
    the older one is obsolete on somebody else's schedule.
    """
    for method in ("initialize", "server/discover"):
        (answer,) = talk(root, {"jsonrpc": "2.0", "id": 1, "method": method, "params": {}})
        assert answer["result"]["protocolVersion"] == PROTOCOL
        assert answer["result"]["serverInfo"]["name"] == "musubi"


def test_a_notification_is_not_answered(root: Path) -> None:
    """JSON-RPC: no `id`, no response. A server that replied to
    `notifications/initialized` would desynchronise a client counting them."""
    assert talk(root, {"jsonrpc": "2.0", "method": "notifications/initialized"}) == []


def test_an_unknown_method_is_an_error_and_not_a_crash(root: Path) -> None:
    (answer,) = talk(root, {"jsonrpc": "2.0", "id": 9, "method": "tools/invent"})
    assert answer["error"]["code"] == -32601


def test_broken_json_does_not_end_the_session(root: Path) -> None:
    """A stream is long-lived. One bad line is a parse error and the next
    request still has to work."""
    written = io.StringIO()
    serve(
        root,
        stream=io.StringIO(
            "{not json\n" + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}) + "\n"
        ),
        out=written,
    )
    first, second = (json.loads(line) for line in written.getvalue().splitlines())
    assert first["error"]["code"] == -32700
    assert second["result"] == {}


def test_every_tool_is_listed_with_a_schema(root: Path) -> None:
    (answer,) = talk(root, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    listed = answer["result"]["tools"]

    assert {tool["name"] for tool in listed} == {tool.name for tool in TOOLS}
    for tool in listed:
        assert tool["inputSchema"]["type"] == "object"
        assert tool["description"].strip()


# -- what it refuses --------------------------------------------------------


@pytest.mark.parametrize("path", ["../outside.md", "../../etc/passwd", "notes/../../escape.md"])
def test_a_path_outside_the_root_is_refused(root: Path, path: str) -> None:
    """[ADR-0007]: musubi reads a folder the owner named. An MCP server is the
    one place that folder is chosen by somebody else's program, so the root is
    the whole safety property.

    Resolved before comparison, so `..` and a symbolic link are answered by the
    same line rather than by a list of tricks.
    """
    (root.parent / "outside.md").write_text("secrets\n", encoding="utf-8")

    with pytest.raises(OutsideRootError, match="outside"):
        Server(root).inside(path)


def test_an_absolute_path_inside_the_root_is_allowed(root: Path) -> None:
    """The refusal is about the tree, not about the spelling."""
    inside = Server(root).inside(str(root / "notes" / "gear.md"))
    assert inside.name == "gear.md"


def test_the_refusal_arrives_as_a_tool_result_not_a_transport_error(root: Path) -> None:
    """So that the model reads *this file is outside the folder* and stops,
    rather than seeing the connection fail and retrying."""
    result = call(root, "musubi_convert", path="../../../etc/passwd")
    assert result["isError"] is True
    assert "outside" in result["content"][0]["text"]


def test_no_tool_writes_anything(root: Path) -> None:
    """`sync` is deliberately absent. A tool that builds a corpus is a tool an
    agent can be talked into pointing somewhere."""
    assert {tool.name for tool in TOOLS} == {"musubi_convert", "musubi_trace", "musubi_plan"}

    before = {path for path in root.rglob("*") if path.is_file()}
    call(root, "musubi_convert", path="notes/gear.md")
    call(root, "musubi_plan", folder=".")
    assert {path for path in root.rglob("*") if path.is_file()} == before


def test_a_credential_refuses_here_too(root: Path) -> None:
    """[ADR-0008] does not stop applying because the caller is a model. The
    error names the rule and the text never leaves."""
    (root / "notes" / "config.md").write_text(
        "aws_access_key_id = AKIAIOSFODNN7EXAMPLE\n", encoding="utf-8"
    )
    result = call(root, "musubi_convert", path="notes/config.md")

    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "aws.access-key" in text
    assert "AKIAIOSFODNN7EXAMPLE" not in text


def test_a_root_that_is_not_a_folder_is_refused(tmp_path: Path) -> None:
    from musubi.errors import MusubiError

    lonely = tmp_path / "one.md"
    lonely.write_text(NOTE, encoding="utf-8")
    with pytest.raises(MusubiError, match="rooted at one"):
        Server(lonely)


# -- what it is for ---------------------------------------------------------


def test_convert_reports_coverage_and_its_companion(root: Path) -> None:
    """`answer_width` beside `traceable_coverage`, never instead of it: an
    alignment that matched nothing reports 100% coverage ([ADR-0033]), and an
    agent reading only the first number would be reading the failure as a
    success."""
    found = body(call(root, "musubi_convert", path="notes/gear.md"))

    assert found["converter"] == "markdown@1"
    assert found["traceable_coverage"] == 1.0
    assert found["removed"] == [{"rule": "tracking.utm-family", "characters": 12}]

    # Close to 1, not equal to it. On a CRLF checkout each line ending is a
    # transformed run answering one output character with two source
    # characters, so a faithful map here reads about 1.07 rather than 1.00 --
    # and asserting equality would have been asserting the line endings.
    assert 1.0 <= found["answer_width"] < 1.5, (
        "a map that answers a character with about a character is what a "
        "near-identity conversion should produce"
    )


def test_convert_then_trace_in_one_session_cites_the_source(root: Path) -> None:
    """The reason to expose musubi to an agent at all.

    A string cannot be checked. This turns *the notes say the tent weighs
    2.4kg* into a range of a named file, in the same conversation, without the
    agent holding anything but what the tools returned.
    """
    converted = body(call(root, "musubi_convert", path="notes/gear.md"))
    at = converted["text"].index("2.4kg")

    cited = body(call(root, "musubi_trace", path="notes/gear.md", start=at, end=at + 5))

    assert cited["excerpt"] == "2.4kg"
    assert cited["exact"] is True
    assert cited["unit"] == "characters"
    assert Path(cited["source"]).name == "gear.md"

    source = Path(cited["source"]).read_bytes().decode("utf-8")
    assert source[cited["span"][0] : cited["span"][1]] == "2.4kg"


def test_plan_reports_and_writes_nothing(root: Path) -> None:
    found = body(call(root, "musubi_plan", folder="."))
    assert found["nothing_was_written"] is True
    assert found["would_emit"] >= 1
    assert not (root / ".musubi-plan-only").exists()


@pytest.fixture(autouse=True)
def _no_stray_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    import os

    for name in list(dict(os.environ)):
        if name.startswith("MUSUBI_"):
            monkeypatch.delenv(name)
    yield
