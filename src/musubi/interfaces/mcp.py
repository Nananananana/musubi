"""musubi as an MCP server, so an agent can cite what it read.

## Why this is the surface that matters

An agent that reads a document gets a string, and a string cannot be checked. It
summarises, the summary enters an answer, and the answer says *your notes say
the tent weighs 2.4kg* with nothing behind it.

musubi's whole product is the thing that closes that: `trace` takes a range of
converted text and returns a place in the file the owner already has. Exposed
over the Model Context Protocol, an agent can **convert a document and then cite
it back to the byte, in the same session**, which is the shortest demonstration
of what this library is for.

```text
convert(path)                 -> text, coverage, answer_width, converter
trace(path, start, end)       -> characters [13:18] of ~/notes/gear.md, verbatim
plan(folder)                  -> what a sync would do, writing nothing
```

## What it refuses, which is most of the design

**It is rooted.** The server takes a folder on the command line and refuses every
path outside it — resolved, so `../` does not help. [ADR-0007] says musubi reads
*a folder the owner named*, and an MCP server is the one place where a program
somebody else is driving asks for paths. Without the root this would be a
file-reading tool for whatever is on the machine.

**It writes nothing.** `convert` and `trace` and `plan` are all read-only, and
`sync` is deliberately not exposed. A tool that builds a corpus is a tool an
agent can be talked into pointing somewhere; the person who wants that runs
`musubi sync` and watches it.

**A credential still stops it.** [ADR-0008] applies here as it does everywhere:
`convert` returns an error naming the rule, never the text and never the value.

## The wire

JSON-RPC 2.0 over stdio, on the standard library. Two protocol generations are
answered, because both are deployed:

- `initialize` / `tools/list` / `tools/call` — the handshake every current
  client speaks;
- `server/discover` — the 2026-07-28 revision, which removed the handshake and
  made every request self-describing.

A server that spoke only the newer one would be unusable by the clients that
exist, and one that spoke only the older one would be obsolete on a schedule
somebody else controls. Answering both costs one method.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import __version__, api
from ..errors import MusubiError

__all__ = ["PROTOCOL", "OutsideRootError", "Server", "serve"]

#: The revision this speaks. Reported in `initialize`, and echoed for a client
#: that declares a different one rather than being argued about: the transport
#: is stdio and there is exactly one peer.
PROTOCOL = "2026-07-28"

#: Answered for older clients too, because that is what is deployed.
FALLBACK = "2025-06-18"


@dataclass(frozen=True, slots=True)
class Tool:
    """One thing an agent may ask for."""

    name: str
    description: str
    schema: Mapping[str, Any]
    run: Callable[[Server, Mapping[str, Any]], str]


class OutsideRootError(MusubiError):
    """A path outside the folder this server was given."""


class Server:
    """The tools, and the root they are confined to."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise MusubiError(f"{self.root} is not a folder; an MCP server is rooted at one")

    # -- the boundary ------------------------------------------------------

    def inside(self, given: str) -> Path:
        """Resolve a path the client sent, or refuse it.

        Resolved before comparison, so `../` and a symbolic link are both
        answered by the same line. This is the only place a caller-supplied
        path becomes a file, deliberately.
        """
        asked = Path(given)
        candidate = (asked if asked.is_absolute() else self.root / asked).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError:
            raise OutsideRootError(
                f"{given!r} is outside {self.root}. This server reads one folder "
                f"(ADR-0007); start another one if you meant a different tree."
            ) from None
        return candidate

    # -- the tools ---------------------------------------------------------

    def convert(self, arguments: Mapping[str, Any]) -> str:
        document = api.convert(self.inside(str(arguments["path"])))
        return json.dumps(
            {
                "text": document.text,
                "converter": document.converter,
                "media_type": document.media_type,
                "encoding": document.encoding,
                "traceable_coverage": round(document.coverage, 4),
                # Published beside coverage, never instead of it: an alignment
                # that matched nothing reports 100% coverage and a large answer
                # width (ADR-0033).
                "answer_width": round(document.trace.answer_width, 2),
                "removed": [
                    {"rule": record.rule, "characters": record.removed_characters}
                    for record in document.removals
                ],
            },
            ensure_ascii=False,
            indent=2,
        )

    def trace(self, arguments: Mapping[str, Any]) -> str:
        path = self.inside(str(arguments["path"]))
        start, end = int(arguments["start"]), int(arguments["end"])
        document = api.convert(path)
        where = document.where(start, end)
        return json.dumps(
            {
                "excerpt": document.text[start:end],
                "where": str(where),
                "source": str(path),
                "unit": where.unit,
                "span": [where.span.start, where.span.end],
                "exact": where.is_exact,
                "kinds": [kind.value for kind in where.kinds],
                "rules": list(where.rules),
            },
            ensure_ascii=False,
            indent=2,
        )

    def plan(self, arguments: Mapping[str, Any]) -> str:
        from ..application.pipeline import run
        from ..config import load, settings_from, source_from
        from ..infrastructure.emitters import DocumentEmitter

        folder = self.inside(str(arguments.get("folder", ".")))
        configuration = load(folder)
        outcome = run(
            source_from(configuration, folder),
            settings_from(configuration, musubi_version=__version__, created_at=""),
            DocumentEmitter(folder / ".musubi-plan-only"),
            write=False,
        )
        coverage = outcome.manifest.coverage
        return json.dumps(
            {
                "would_emit": coverage.emitted,
                "would_skip": coverage.skipped,
                "traceable_coverage": round(coverage.traceable_coverage, 4),
                "skipped": [
                    {"unit": skip.origin, "reason": skip.reason}
                    for skip in outcome.manifest.skipped
                ],
                "nothing_was_written": True,
            },
            ensure_ascii=False,
            indent=2,
        )


TOOLS: tuple[Tool, ...] = (
    Tool(
        name="musubi_convert",
        description=(
            "Convert one document to clean text and report how much of it can be traced "
            "back to the source. Reads; writes nothing. Refuses a file holding a credential."
        ),
        schema={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "relative to the root"}},
            "required": ["path"],
        },
        run=lambda server, arguments: server.convert(arguments),
    ),
    Tool(
        name="musubi_trace",
        description=(
            "Say where a range of the converted text came from: a character range of the "
            "original file, or a page for a PDF. Use this to cite a document rather than "
            "quoting it."
        ),
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start": {"type": "integer"},
                "end": {"type": "integer"},
            },
            "required": ["path", "start", "end"],
        },
        run=lambda server, arguments: server.trace(arguments),
    ),
    Tool(
        name="musubi_plan",
        description=(
            "Report what building a corpus from a folder would do -- what would be read, "
            "skipped and removed -- without writing anything."
        ),
        schema={
            "type": "object",
            "properties": {"folder": {"type": "string"}},
        },
        run=lambda server, arguments: server.plan(arguments),
    ),
)

_BY_NAME = {tool.name: tool for tool in TOOLS}


def _descriptor() -> dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "musubi", "version": __version__},
        "instructions": (
            "musubi converts documents and keeps a map back to the original bytes. "
            "After musubi_convert, use musubi_trace to cite a range rather than "
            "quoting it: the answer names a place in the user's own file."
        ),
    }


def handle(server: Server, message: Mapping[str, Any]) -> dict[str, Any] | None:
    """One request in, one response out, or ``None`` for a notification."""
    method = str(message.get("method", ""))
    identifier = message.get("id")

    if identifier is None:
        return None  # a notification; `notifications/initialized` is the usual one

    def answer(result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": identifier, "result": result}

    def failed(code: int, text: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": text}}

    if method in {"initialize", "server/discover"}:
        return answer(_descriptor())
    if method == "ping":
        return answer({})
    if method == "tools/list":
        return answer(
            {
                "tools": [
                    {"name": t.name, "description": t.description, "inputSchema": t.schema}
                    for t in TOOLS
                ]
            }
        )
    if method == "tools/call":
        parameters = message.get("params") or {}
        tool = _BY_NAME.get(str(parameters.get("name", "")))
        if tool is None:
            return failed(-32602, f"no tool called {parameters.get('name')!r}")
        try:
            body = tool.run(server, parameters.get("arguments") or {})
        except MusubiError as refusal:
            # Reported as a tool result rather than as a protocol error, because
            # a refusal is an answer: the model should read "this file holds a
            # credential" and stop, not see the transport fail.
            return answer({"content": [{"type": "text", "text": str(refusal)}], "isError": True})
        except (OSError, KeyError, ValueError) as error:
            return answer(
                {
                    "content": [{"type": "text", "text": f"{type(error).__name__}: {error}"}],
                    "isError": True,
                }
            )
        return answer({"content": [{"type": "text", "text": body}], "isError": False})

    return failed(-32601, f"unknown method {method!r}")


def _writer(out: Any) -> Callable[[str], None]:
    """Write a protocol line as **UTF-8 bytes**, whatever the console is.

    [ADR-0020] records this failure for `--json`: passing a document through the
    terminal's codec produced a file that was not valid UTF-8, with exit 0 and
    no error. It is worse here. `--json` is read by a person who might notice; a
    protocol stream is read by a parser, and on a `cp932` console this wrote
    JSON a client cannot decode — or, with the `errors="replace"` the CLI puts
    in front of every stream, JSON it *can* decode with the document mangled
    inside it.

    JSON-RPC is UTF-8 by definition. So the bytes go to the buffer beneath the
    stream when there is one, and a caller that handed in a text sink gets text.
    """
    buffer = getattr(out, "buffer", None)
    if buffer is None:

        def write_text(line: str) -> None:
            out.write(line)
            out.flush()

        return write_text

    def write_bytes(line: str) -> None:
        out.flush()
        buffer.write(line.encode("utf-8"))
        buffer.flush()

    return write_bytes


def serve(root: Path, stream: Any = None, out: Any = None) -> int:
    """Read JSON-RPC from stdin and answer on stdout, one line each.

    Line-delimited rather than the framed transport: that is what stdio clients
    send, and a framing layer would be code with no second reader.
    """
    server = Server(root)
    source = sys.stdin if stream is None else stream
    write = _writer(sys.stdout if out is None else out)

    for line in source:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as error:
            write(
                json.dumps(
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(error)}}
                )
                + "\n"
            )
            continue
        response = handle(server, message)
        if response is not None:
            write(json.dumps(response, ensure_ascii=False) + "\n")
    return 0
