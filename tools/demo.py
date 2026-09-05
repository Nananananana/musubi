"""A vault, a corpus, and a citation that comes home. Five minutes.

Builds a small folder of notes -- Japanese, English, a Shift-JIS file, a PDF,
one with a credential in it -- and then walks musubi across it, printing what
each step establishes and what it does not.

    uv run python tools/demo.py

Everything is written under a temporary folder and printed; nothing touches
anything you have. `--keep` leaves it on disk and prints where, so the commands
in the transcript can be run by hand afterwards.

`demo/README.md` is the same walk with the commands written out to type
yourself, against a sample folder that stays where you can look at it. This one
is for *does it work*; that one is for *what does it do*.

This exists because the interesting claim is hard to see from a README. The
last step takes a range of text that has been converted, cleansed, given front
matter and written to a corpus, and turns it back into a byte offset in the
original file -- and then reads that file to check.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from pdf_fixtures import classic

#: How a user runs it. Not `python -m musubi.interfaces.cli.main`: `runpy`
#: imports that module a second time as `__main__`, so the command table
#: populated at its foot belongs to the first copy and the second one is empty.
ENTRY = "import sys; from musubi.interfaces.cli import main; sys.exit(main(sys.argv[1:]))"

GEAR = """# ギア設計

テントは 2.4kg。ブーツのほうが効く。山では軽さがすべて。
出典: https://example.test/gear?utm_source=newsletter&utm_medium=email
"""

STOVE = """# Stove notes

A remote canister freezes and a liquid-fuel stove does not, which matters
exactly once. See https://example.test/stove?fbclid=abc123 for the numbers.
"""

OLD = "# 古いメモ\n\n2009年に書いた。エンコーディングは Shift-JIS のまま。\n"

LEAKY = "# deploy\n\naws_access_key_id = AKIAIOSFODNN7EXAMPLE\n"


def step(number: int, title: str, command: str = "") -> None:
    # ASCII, and no colour. This is a demonstration somebody runs on their own
    # terminal, and a `cp932` console -- the default on Japanese Windows, which
    # ADR-0020 exists because of -- shows a box-drawing rule as mojibake.
    print(f"\n{'-' * 70}\n{number}. {title}")
    if command:
        print(f"   $ {command}\n")


def run(command: list[str], cwd: Path, *, show: int | None = None, quiet: bool = False) -> str:
    """Run a command and print what it said, trimmed to what the step is about.

    Every report ends with a `Limits` block naming what the run does *not*
    establish, which is the posture and is the right thing on a real run. In a
    transcript that repeats it nine times it stops being read, so the steps that
    are not about the limits cut the tail and say how much they cut.
    """
    finished = subprocess.run(
        [sys.executable, "-c", ENTRY, *command],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if not quiet:
        lines = (finished.stdout + finished.stderr).rstrip().splitlines()
        print(textwrap.indent("\n".join(lines if show is None else lines[:show]), "   "))
        if show is not None and len(lines) > show:
            # What was actually cut, rather than what usually is. Most reports
            # end in the Limits block and `blame` does not, and a transcript
            # that describes output it did not print is the one thing a
            # demonstration must not do.
            cut = lines[show:]
            ending = (
                "ending in the Limits block"
                if any(line.strip().startswith("Limits") for line in cut)
                else "more of the same"
            )
            print(f"   ... {len(cut)} more lines, {ending}")
    return finished.stdout


def build(root: Path) -> Path:
    vault = root / "notes"
    (vault / "design").mkdir(parents=True)
    (vault / "design" / "gear.md").write_text(GEAR, encoding="utf-8")
    (vault / "stove.md").write_text(STOVE, encoding="utf-8")
    (vault / "design" / "old.md").write_bytes(OLD.encode("cp932"))
    (vault / "report.pdf").write_bytes(classic())
    return vault


def main() -> int:
    parser = argparse.ArgumentParser(description="Walk musubi across a small vault.")
    parser.add_argument("--keep", action="store_true", help="leave the folder on disk")
    arguments = parser.parse_args()

    root = Path(tempfile.mkdtemp(prefix="musubi-demo-"))
    vault = build(root)
    print(f"A vault at {vault}")
    print("   design/gear.md    Japanese, UTF-8, with tracking parameters in a URL")
    print("   stove.md          English, with a different tracking parameter")
    print("   design/old.md     Japanese, **Shift-JIS**")
    print("   report.pdf        a PDF with a text layer")
    print()
    print("   If the Japanese below looks like mojibake, that is your terminal's")
    print("   codec and not the corpus: musubi writes UTF-8 whatever the console is.")

    step(1, "What would happen. Nothing is written.", "musubi plan notes --as filesystem")
    run(["plan", "notes", "--as", "filesystem"], root, show=10)
    print("\n   The Shift-JIS note was skipped, and the skip says what it is and")
    print("   which setting reads it. That is the difference between a refusal")
    print("   and a dead end.")

    step(2, "Turn that setting on.", "echo 'encoding = \"detect\"' >> musubi.toml")
    (root / "musubi.toml").write_text(
        'source = "filesystem"\nencoding = "detect"\ninto = "corpus"\n', encoding="utf-8"
    )
    run(["config"], root)

    step(3, "Build it.", "musubi sync notes")
    run(["sync", "notes"], root, show=8)

    step(4, "A credential stops the whole run.", "musubi sync notes   # with a leaked key")
    (vault / "deploy.md").write_text(LEAKY, encoding="utf-8")
    run(["sync", "notes"], root)
    print("\n   Nothing was written -- not the offending file, not the four that")
    print("   converted cleanly before it. The message names the rule and never")
    print("   the value.")
    (vault / "deploy.md").unlink()
    run(["sync", "notes"], root, quiet=True)

    step(5, "Follow a sentence back to the file you have.")
    document = root / "corpus" / "documents" / "design" / "gear.md"
    text = document.read_text(encoding="utf-8")
    at = text.index("2.4kg")
    print(f"   $ musubi trace corpus/documents/design/gear.md:{at}-{at + 5}\n")
    run(["trace", f"corpus/documents/design/gear.md:{at}-{at + 5}"], root)
    print("\n   The last line is the excerpt read back out of notes/design/gear.md.")
    print("   Not asserted -- opened and checked.")

    step(6, "The tracking parameters are gone, and recorded.", "musubi plan notes --show-removals")
    run(["plan", "notes", "--show-removals"], root, show=12)

    step(7, "Edit a note, sync again, and ask what changed.", "musubi log corpus")
    gear = vault / "design" / "gear.md"
    gear.write_text(gear.read_text(encoding="utf-8") + "\n2026-09-05 追記。\n", encoding="utf-8")
    said = run(["sync", "notes"], root, quiet=True)
    for line in said.splitlines():
        if "carried forward" in line:
            print(f"   (the sync said: {line.strip()})\n")
    run(["log", "corpus"], root)
    print("\n   Three runs, each naming the one before it. The refusal in step 4 is")
    print("   not among them: a run that stopped wrote nothing, including here.")
    print("   The middle two share a corpus id and differ in their own -- the same")
    print("   folder synced twice is the same corpus and two different runs.")

    print("\n   $ musubi blame corpus\n")
    run(["blame", "corpus"], root, show=8)
    print("\n   Which run put each document where it is. An artefact this history")
    print("   cannot account for prints as unknown rather than being attributed to")
    print("   the oldest run it happens to sit beside.")

    step(8, "One file, three lines of Python.")
    print(
        textwrap.indent(
            "import musubi\ndoc = musubi.convert('notes/design/gear.md')\ndoc.where(13, 18)",
            "   $ ",
        )
    )
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    import musubi

    converted = musubi.convert(vault / "design" / "gear.md")
    inside = converted.text.index("2.4kg")
    print(f"\n   text        {converted.text.splitlines()[0]!r} ...")
    print(f"   coverage    {converted.coverage:.1%}")
    print(f"   answer      {converted.trace.answer_width:.2f} source characters per character")
    print(f"   where       {converted.where(inside, inside + 5)}")
    print(f"   removed     {[record.rule for record in converted.removals]}")

    step(9, "The corpus as one file every framework reads.", "musubi export corpus")
    exported = run(["export", "corpus"], root, quiet=True)
    first = json.loads(exported.splitlines()[0])
    print(f"\n   id          {first['id']}   <- survives a re-sync, so an upsert updates")
    print(f"   trace_map   {first['metadata']['trace_map']}   <- the citation can come back")

    step(10, "And the same thing over MCP, for an agent.", "musubi mcp .")
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "musubi_trace",
            "arguments": {"path": "notes/design/gear.md", "start": inside, "end": inside + 5},
        },
    }
    finished = subprocess.run(
        [sys.executable, "-c", ENTRY, "mcp", "."],
        cwd=root,
        input=json.dumps(request) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    answer = json.loads(finished.stdout.splitlines()[0])
    print(textwrap.indent(answer["result"]["content"][0]["text"], "   "))
    print("\n   An agent that read this document can cite it. That is the whole")
    print("   point: a string cannot be checked and a citation can.")

    print()
    if arguments.keep:
        print(f"Left on disk: {root}")
    else:
        shutil.rmtree(root, ignore_errors=True)
        print("Removed. Pass --keep to walk through it by hand.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
