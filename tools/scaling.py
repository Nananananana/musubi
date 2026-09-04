"""Four numbers the design predicted and nobody had measured.

`docs/proposals/0001-the-design.md` §10 writes down what would falsify the
design, and §9's v0.4 lists the metrics that would decide it. Two of those
numbers turn out to be bad, and one of the two is bad in a way the proposal
predicted *the wrong fix for*. That is the falsification section working, and it
only works if somebody runs it.

```text
**map size**        map bytes per document byte, on a real sync
**re-read ratio**   a no-change re-sync against a cold one
**archive reads**   what a source re-reads to hand over one unit
**cold ceiling**    what a run holds in memory at once
```

Everything here generates its own corpus. That is a real limitation and it is
the same one `docs/evaluation-corpus.md` will state: generated text has the
right *shape* and none of the mess. What it can answer is the question of
**order of growth**, which is what these four are about -- a number that doubles
when the input doubles is a different problem from one that quadruples, and no
amount of realism changes which one you have.

    uv run python tools/scaling.py
    uv run python tools/scaling.py --only archive
"""

from __future__ import annotations

import argparse
import io
import json
import tempfile
import time
import tracemalloc
import zipfile
from collections.abc import Callable
from pathlib import Path

from musubi import __version__
from musubi.application.pipeline import Settings
from musubi.application.sync import sync
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.emitters import DOCUMENTS, MANIFEST, TRACES, DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import FilesystemSource
from musubi.infrastructure.sources.notion import NotionSource

PARAGRAPH = "Some ordinary prose in a paragraph that a person actually wrote.\n\n"
MARKDOWN = "# A note\n\n" + PARAGRAPH * 40
HTML = (
    "<!doctype html><html><body><nav><a href='/'>Home</a></nav><article>"
    + "".join(
        f"<p>A paragraph of ordinary prose, number {i}, long enough to match.</p>\n"
        for i in range(40)
    )
    + "</article><footer>Copyright 2026 Example</footer></body></html>"
)


def settings() -> Settings:
    return Settings(
        ruleset=CORE,
        screener=default_screener(),
        converter_for=converter_for,
        musubi_version=__version__,
    )


def _vault(root: Path, notes: int, pages: int) -> Path:
    vault = root / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    for i in range(notes):
        (vault / f"note{i:05d}.md").write_text(MARKDOWN, encoding="utf-8")
    for i in range(pages):
        (vault / f"page{i:05d}.html").write_text(HTML, encoding="utf-8")
    return vault


def _bytes_under(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


# -- 1. what the guarantee costs in storage ---------------------------------


def map_size() -> None:
    """Map bytes per document byte, on a corpus a real sync wrote.

    §10: *if a map routinely exceeds its document, the guarantee costs more
    storage than the corpus*, and the proposal says **the fix is
    converter-side**. Half of it is not: the sidecar is written with
    `indent=2`, and the indentation is about as many bytes as the data.
    """
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        vault = _vault(root, notes=20, pages=20)
        into = root / "corpus"
        sync(FilesystemSource(vault), settings(), DocumentEmitter(into))

        documents = _bytes_under(into / DOCUMENTS)
        maps = _bytes_under(into / TRACES)
        manifest = (into / MANIFEST).stat().st_size

        print(f"  documents/ {documents:>10,}")
        print(f"  traces/    {maps:>10,}   {maps / documents:>5.1f}x the documents")
        print(f"  manifest   {manifest:>10,}")
        print(
            f"  everything {documents + maps + manifest:>10,}   "
            f"{(documents + maps + manifest) / documents:>5.1f}x"
        )
        print()

        for label, name in (("one .html", "page00000.html"), ("one .md", "note00000.md")):
            sidecar = into / TRACES / f"{name}.json"
            body = json.loads(sidecar.read_text(encoding="utf-8"))
            segments = body["segments"]
            packed = len(json.dumps(segments, separators=(",", ":"), ensure_ascii=False).encode())
            document = (into / DOCUMENTS / name).stat().st_size
            print(
                f"  {label:9s} document {document:>7,}  map {sidecar.stat().st_size:>7,} "
                f"({sidecar.stat().st_size / document:>5.1f}x)  "
                f"{len(segments):>4} segments, {packed:>7,} bytes minified"
            )


# -- 2. what a re-sync that changed nothing costs ---------------------------


def re_read() -> None:
    """ADR-0006: *a re-export that changed nothing produces an empty diff*.

    `Change` exists and nothing calls it, which `docs/README.md` says plainly.
    This is what that costs, rather than what it sounds like it costs.
    """
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        vault = _vault(root, notes=400, pages=0)
        into = root / "corpus"

        started = time.perf_counter()
        cold = sync(FilesystemSource(vault), settings(), DocumentEmitter(into))
        cold_seconds = time.perf_counter() - started

        started = time.perf_counter()
        again = sync(FilesystemSource(vault), settings(), DocumentEmitter(into))
        again_seconds = time.perf_counter() - started

        first = len(cold.manifest.artefacts)
        second = len(again.manifest.artefacts)
        print(f"  cold sync            {cold_seconds:>6.2f}s  {first} artefacts")
        print(f"  no-change re-sync    {again_seconds:>6.2f}s  {second} artefacts")
        print(
            f"  **re-read ratio       {again_seconds / cold_seconds:>6.2f}**   "
            f"(the design implies near zero)"
        )


# -- 3. what a source re-reads to hand over one unit ------------------------


def archive_reads() -> None:
    """`Source` is two stages: `discover()` opens nothing, `read()` opens one.

    For a folder that is exactly right. For an **archive** it is the shape of a
    quadratic: there is no way to open one entry without the container, so the
    container is opened once per entry.
    """
    # No "bytes touched" column. The obvious one is `pages * archive size`,
    # which is an *estimate of a particular implementation* rather than a
    # measurement of this one -- and it would keep printing a quadratic number
    # after the implementation stopped being quadratic. The per-page cost is the
    # honest signal: flat means linear.
    print(f"  {'pages':>6} {'archive':>10} {'read all':>10} {'per page':>10}")
    previous: tuple[int, float] | None = None
    for pages in (50, 100, 200, 400):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            inner = io.BytesIO()
            with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as part:
                for i in range(pages):
                    part.writestr(f"Note {i} {i:032x}.md", f"# note {i}\n\n{PARAGRAPH * 20}")
            outer = root / "8a1_ExportBlock-9f2.zip"
            with zipfile.ZipFile(outer, "w") as archive:
                archive.writestr("ExportBlock-9f2-Part-1.zip", inner.getvalue())

            size = outer.stat().st_size
            source = NotionSource(root)
            found = source.discover().found
            started = time.perf_counter()
            for item in found:
                source.read(item)
            seconds = time.perf_counter() - started

            growth = ""
            if previous is not None:
                pages_factor = pages / previous[0]
                time_factor = seconds / previous[1] if previous[1] else 0.0
                growth = f"   {pages_factor:.0f}x pages -> {time_factor:.1f}x time"
            previous = (pages, seconds)
            each = seconds / pages * 1000
            print(f"  {pages:>6} {size:>10,} {seconds:>9.3f}s {each:>9.2f}ms{growth}")


# -- 4. what a run holds at once --------------------------------------------


def cold_ceiling() -> None:
    """Peak memory during a sync, against the size of what is being read.

    Not a bug on its own -- a bound that grows with the corpus is fine until
    somebody points this at the folder holding everything they have written,
    which is the folder ADR-0007 says musubi is for.
    """
    print(f"  {'notes':>6} {'input':>10} {'peak':>12} {'peak/input':>11}")
    for notes in (100, 200, 400):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            vault = _vault(root, notes=notes, pages=0)
            source_bytes = _bytes_under(vault)

            tracemalloc.start()
            sync(FilesystemSource(vault), settings(), DocumentEmitter(root / "corpus"))
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            print(f"  {notes:>6} {source_bytes:>10,} {peak:>12,} {peak / source_bytes:>10.1f}x")


MEASUREMENTS: dict[str, tuple[str, Callable[[], None]]] = {
    "map": ("What the guarantee costs in storage", map_size),
    "resync": ("What a re-sync that changed nothing costs", re_read),
    "archive": ("What a source re-reads to hand over one unit", archive_reads),
    "memory": ("What a run holds at once", cold_ceiling),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure what the design predicted.")
    parser.add_argument("--only", choices=sorted(MEASUREMENTS), default=None)
    arguments = parser.parse_args()

    chosen = [arguments.only] if arguments.only else list(MEASUREMENTS)
    for name in chosen:
        heading, measure = MEASUREMENTS[name]
        print(f"\n== {name}: {heading} ==\n", flush=True)
        measure()
    print()
    print("Generated corpora, so these answer order of growth and not absolute cost.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
