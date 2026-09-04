"""A Notion export, keyed by the page id rather than by where the file sits.

This is the source ADR-0006's whole argument was aimed at. A vault has no
identity to offer but its paths, so `FilesystemSource` keys by path and states
the weakness: moving a file looks like a delete plus an add. A Notion export
does carry identity — and the ADR contradicted itself about where.

Its Context says the 32-character UUID in an export filename **is regenerated
per export**. Its Decision says `unit_key` is *the Notion page id parsed out of
the filename*, which is a stable key only if that UUID is **not** regenerated.
Both cannot be true of one number.

A real export settles the shape, though not yet the stability. There are **three
UUIDs on three layers**:

```text
<uuid>_ExportBlock-<uuid>.zip                 the export job, and the block
  └── ExportBlock-<uuid>-Part-1.zip           the same block, numbered part
        └── <Page title> <32 hex>.md          the page
```

The first two are certainly per-export. The third is a different number, and it
re-formats into a well-formed UUID. **So the Context and the Decision may both
be true, about different UUIDs, and the contradiction may be a sentence that did
not say which one it meant.**

That is not established, and this source does not pretend it is. It keys by the
page id, declares `key_derivation` as `notion-page-id` so the manifest names
exactly what it did, and `docs/sources.md` records that the stability is
**unverified until a second export of the same page**. If the second export
disagrees, the derivation falls back to `path` and the manifest says *that*. The
default does not become a decision by accident.

**The key is the page id and not the title.** That makes a corpus of hexadecimal
filenames, which is worse to browse and stable across a rename — and it costs
nothing, because Notion writes the title into the document's first line as an
`# ` heading. Measured on the real export: the title in the filename and the H1
in the body are the same string. Nothing is lost by not putting it in the name.

**A file with no page id is skipped rather than keyed by its path.** Mixing two
derivations under one `key_derivation` would make the manifest's statement false
for some units, and a reader has no way to tell which. Skipping is already a
first-class outcome with a reason attached.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ...errors import SourceError
from ...ports.source import Discovery, Found, Skipped

__all__ = ["MEDIA_TYPES", "NotionSource"]

#: `<Page title> <32 hex>.md`. Notion separates the title from the id with a
#: single space and uses lowercase hexadecimal.
_KEYED = re.compile(r"^(?P<title>.*) (?P<page>[0-9a-f]{32})$")

#: What a Notion export contains that musubi can read. `.csv` is a database
#: view; it is listed so that discovery reports it rather than passing over it
#: in silence, and skipped for want of a converter like any other format.
MEDIA_TYPES: dict[str, str] = {
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".html": "text/html",
}

#: How deep the nesting is followed. A Notion export is an archive of archives
#: (`Part-1.zip`, `Part-2.zip`), and two levels is what a real export uses. A
#: bound rather than recursion without one: an archive that contains itself is a
#: thing a downloaded file can be.
MAXIMUM_DEPTH = 4

#: What one entry may inflate to before it is refused.
#:
#: `ZipFile.read` decides how much memory to take from a number the archive
#: supplies, and a Notion export is a file downloaded from a service over a
#: network. A few hundred bytes of compressed zeroes take the process down, and
#: a process that died has not refused anything: [ADR-0008] is fail-closed, and
#: there is no manifest, no message, and the same exit code as an interrupt.
#:
#: A page of Notion Markdown is kilobytes. This is the largest single note
#: anybody has, several times over.
MAXIMUM_ENTRY_BYTES = 256 * 1024 * 1024

#: How much of a nested archive is kept inflated while a run reads it.
#:
#: A Notion export is an archive of archives, and reading one page means
#: inflating the `Part-N.zip` it lives in. Doing that per page is quadratic --
#: measured, and filed as #78. Holding every part is linear in the export, which
#: is the appetite `MAXIMUM_ENTRY_BYTES` exists to refuse.
#:
#: So: a budget. A real export's parts fit in it and the run is linear; a larger
#: one degrades to re-inflating, which is correct and slow, with a bound
#: somebody chose rather than none.
NESTED_BUDGET = 512 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class _Part:
    """A nested archive held open, and what it costs to hold it."""

    archive: zipfile.ZipFile
    size: int


class NotionSource:
    """Satisfies :class:`~musubi.ports.source.Source`.

    Reads a Notion export archive, or a folder holding one, opening entries
    only when asked for them.
    """

    key_derivation = "notion-page-id"

    def __init__(
        self,
        root: Path,
        *,
        source_id: str = "notion",
        adapter: str = "notion-export@1",
        maximum_depth: int = MAXIMUM_DEPTH,
        nested_budget: int = NESTED_BUDGET,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        if not self.root.exists():
            raise SourceError(f"{self.root} does not exist")
        self.source_id = source_id
        self.adapter = adapter
        self.origin = str(self.root)
        self._maximum_depth = maximum_depth
        self._origins: Mapping[str, tuple[str | None, str]] | None = None
        self._nested: OrderedDict[str, _Part] = OrderedDict()
        self._held = 0
        self._budget = nested_budget

    # -- stage one: what is there ------------------------------------------

    def discover(self) -> Discovery:
        found: list[Found] = []
        skipped: list[Skipped] = []
        for path in self._archives():
            try:
                outer = zipfile.ZipFile(path)
            except zipfile.BadZipFile as error:
                skipped.append(Skipped(path.name, "unreadable_archive", str(error)))
                continue
            with outer:
                self._walk(outer, path.name, found, skipped, depth=0)
        return Discovery(
            found=tuple(sorted(found, key=lambda f: f.key_parts)),
            skipped=tuple(sorted(skipped, key=lambda s: s.origin)),
            caps=(
                f"archives are followed {self._maximum_depth} levels deep",
                "only files whose name ends in a 32-character page id are read",
            ),
        )

    def _archives(self) -> list[Path]:
        if self.root.is_file():
            return [self.root]
        archives = sorted(p for p in self.root.glob("*.zip") if p.is_file())
        if not archives:
            raise SourceError(
                f"{self.root} holds no .zip. A Notion export is an archive; point this "
                f"at the file the export produced, or at the folder holding it."
            )
        return archives

    def _walk(
        self,
        archive: zipfile.ZipFile,
        inside: str,
        found: list[Found],
        skipped: list[Skipped],
        *,
        depth: int,
        index: dict[str, tuple[str | None, str]] | None = None,
    ) -> None:
        """Read one archive, following the archives it contains.

        Takes an **open** archive rather than its bytes. `zipfile` reads a
        central directory and then seeks, so an archive opened on a path costs
        its directory rather than its size -- and a Notion export is one file
        that a folder of them multiplies.
        """
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            origin = f"{inside}!{entry.filename}"
            suffix = Path(entry.filename).suffix.lower()
            if index is not None:
                # `inside` is the outer archive's *file name* at depth 0 and a
                # nested archive's origin below it, which is exactly the two
                # cases `_part` has to tell apart.
                index[origin] = (None if "!" not in inside else inside, entry.filename)

            if suffix == ".zip":
                if depth + 1 > self._maximum_depth:
                    skipped.append(Skipped(origin, "too_deep", f"{depth + 1} levels"))
                    continue
                try:
                    nested = self._keep(origin, _bounded(archive, entry))
                except _TooLargeError as refusal:
                    skipped.append(Skipped(origin, "too_large", str(refusal)))
                    continue
                except zipfile.BadZipFile as error:
                    skipped.append(Skipped(origin, "unreadable_archive", str(error)))
                    continue
                self._walk(nested, origin, found, skipped, depth=depth + 1, index=index)
                continue

            media_type = MEDIA_TYPES.get(suffix)
            if media_type is None:
                skipped.append(Skipped(origin, "unknown_format", suffix or "(no suffix)"))
                continue

            keyed = _KEYED.match(Path(entry.filename).stem)
            if keyed is None:
                # Keyed by path instead would make `key_derivation` false for
                # this unit and true for its neighbours, with nothing in the
                # manifest saying which is which.
                skipped.append(
                    Skipped(origin, "no_page_id", "the name carries no 32-character page id")
                )
                continue

            found.append(
                Found(
                    key_parts=(f"{keyed['page']}{suffix}",),
                    media_type=media_type,
                    size_bytes=entry.file_size,
                    origin=origin,
                    # A zip entry's timestamp is when the *export* wrote it, not
                    # when the note was written, and every entry in one export
                    # shares it. Passing it on would give a corpus a single date
                    # and call it history (ADR-0022).
                    modified_at=None,
                )
            )

    # -- stage two: one thing, opened --------------------------------------

    def read(self, found: Found) -> bytes:
        """The entry's bytes, reached back through the archives it sits in.

        **The origin is not parsed to get back here.** It reads
        `outer.zip!Part-1.zip!Title <id>.md`, and the obvious thing is to split
        it on `!` -- which works until a page is called `Done!`, and a Notion
        title may contain any character a filename may. Then `plan` lists the
        page and `sync` cannot open it: two commands disagreeing about the same
        export, over a punctuation mark.

        So the archives are walked again and the origin is **rebuilt** by the
        same expression that built it, and compared whole. The two sides cannot
        drift, because there is only one side.

        **What that used to cost, and does not now.** `read()` is called once
        per unit, and it used to inflate the whole export each time: measured at
        400 pages, doubling them more than tripled the time, and the bytes
        touched grew as pages squared. A real export is thousands of pages and
        hundreds of megabytes, where that is not slow but unusable ([#78]).

        Three changes make it linear, and the third is the one that was not
        obvious. The outer archive is **opened on its path**, so it costs a
        central directory rather than its size. The nested parts -- the
        expensive thing, because a `Part-N.zip` is inflated whole -- are held
        under a byte budget. And the origins are **indexed once**, because
        scanning `infolist()` for the target on every call is cheap per entry
        and still quadratic over a run; caching the inflate alone left the curve
        exactly where it was.
        """
        where = self._index().get(found.origin)
        if where is None:
            raise SourceError(f"{found.origin} is not where discovery said it was")

        holder, name = where
        try:
            if holder is None:
                path = next(p for p in self._archives() if p.name == found.origin.split("!")[0])
                with zipfile.ZipFile(path) as outer:
                    return _bounded(outer, outer.getinfo(name))
            nested = self._part(holder)
            return _bounded(nested, nested.getinfo(name))
        except _TooLargeError as refusal:
            raise SourceError(f"{found.origin} was not read: {refusal}") from refusal
        except (zipfile.BadZipFile, KeyError, StopIteration) as error:
            raise SourceError(f"{found.origin} could not be opened: {error}") from error

    def _index(self) -> Mapping[str, tuple[str | None, str]]:
        """Origin to (the archive holding it, its entry name), built once.

        **Still the same construction, not its inverse.** The keys come from the
        same `f"{inside}!{entry.filename}"` expression `_walk` uses, so a title
        containing `!` cannot desynchronise the two sides -- which was the whole
        point of rebuilding rather than parsing, and is preserved here.

        What changes is when it is built: once, rather than per unit. `read()`
        is called once per unit, and a linear scan inside it is a quadratic over
        the run.
        """
        if self._origins is None:
            found: list[Found] = []
            skipped: list[Skipped] = []
            index: dict[str, tuple[str | None, str]] = {}
            for path in self._archives():
                with zipfile.ZipFile(path) as outer:
                    self._walk(outer, path.name, found, skipped, depth=0, index=index)
            self._origins = index
        return self._origins

    def _part(self, origin: str) -> zipfile.ZipFile:
        """A nested archive, **open**, from the cache or inflated again.

        The cache holds the opened archive rather than its bytes, and that is
        not a detail. Constructing a `ZipFile` reads a central directory, which
        is linear in the entries -- so caching only the payload left the run
        quadratic with a smaller constant, which is what the measurement said
        after the first attempt at this.
        """
        held = self._nested.get(origin)
        if held is not None:
            self._nested.move_to_end(origin)
            return held.archive

        holder, name = self._index()[origin]
        if holder is None:
            path = next(p for p in self._archives() if p.name == origin.split("!")[0])
            with zipfile.ZipFile(path) as outer:
                payload = _bounded(outer, outer.getinfo(name))
        else:
            inner = self._part(holder)
            payload = _bounded(inner, inner.getinfo(name))
        return self._keep(origin, payload)

    def _keep(self, origin: str, payload: bytes) -> zipfile.ZipFile:
        """Open a nested archive and hold it, if the budget allows.

        Least-recently-used, bounded in **bytes** rather than in entries,
        because the thing being bounded is memory and a part can be any size.

        The budget rather than an unbounded cache: this reads an export that
        came from somewhere else, and a dictionary that grows with the input is
        the same unbounded-appetite problem `MAXIMUM_ENTRY_BYTES` exists for.
        The budget rather than a cache of one: the pipeline sorts units by key
        and a Notion key is a page id, so reads arrive in an order unrelated to
        which part they are in, and a single slot would thrash.

        An export larger than the budget degrades to the previous behaviour --
        correct, and slow, with a bound somebody chose rather than none.
        """
        archive = zipfile.ZipFile(io.BytesIO(payload))
        if len(payload) <= self._budget:
            self._nested[origin] = _Part(archive=archive, size=len(payload))
            self._held += len(payload)
            while self._held > self._budget and len(self._nested) > 1:
                _, evicted = self._nested.popitem(last=False)
                self._held -= evicted.size
                evicted.archive.close()
        return archive


class _TooLargeError(Exception):
    """One entry claimed more room than the archive is worth."""

    def __init__(self, name: str, limit: int) -> None:
        super().__init__(f"{name} inflates past {limit:,} bytes")


def _bounded(archive: zipfile.ZipFile, entry: zipfile.ZipInfo) -> bytes:
    """The entry's bytes, or a refusal -- never more than the limit.

    Reads one byte past the limit rather than trusting `entry.file_size`, which
    is a number written in the archive by whoever built it.
    """
    with archive.open(entry) as stream:
        body = stream.read(MAXIMUM_ENTRY_BYTES + 1)
    if len(body) > MAXIMUM_ENTRY_BYTES:
        raise _TooLargeError(entry.filename, MAXIMUM_ENTRY_BYTES)
    return body
