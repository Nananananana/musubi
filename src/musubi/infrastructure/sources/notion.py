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
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        if not self.root.exists():
            raise SourceError(f"{self.root} does not exist")
        self.source_id = source_id
        self.adapter = adapter
        self.origin = str(self.root)
        self._maximum_depth = maximum_depth

    # -- stage one: what is there ------------------------------------------

    def discover(self) -> Discovery:
        found: list[Found] = []
        skipped: list[Skipped] = []
        for archive in self._archives():
            self._walk(archive.read_bytes(), archive.name, found, skipped, depth=0)
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
        payload: bytes,
        inside: str,
        found: list[Found],
        skipped: list[Skipped],
        *,
        depth: int,
    ) -> None:
        """Read one archive, following the archives it contains."""
        try:
            archive = zipfile.ZipFile(io.BytesIO(payload))
        except zipfile.BadZipFile as error:
            skipped.append(Skipped(inside, "unreadable_archive", str(error)))
            return

        with archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                origin = f"{inside}!{entry.filename}"
                suffix = Path(entry.filename).suffix.lower()

                if suffix == ".zip":
                    if depth + 1 > self._maximum_depth:
                        skipped.append(Skipped(origin, "too_deep", f"{depth + 1} levels"))
                        continue
                    self._walk(archive.read(entry), origin, found, skipped, depth=depth + 1)
                    continue

                media_type = MEDIA_TYPES.get(suffix)
                if media_type is None:
                    skipped.append(Skipped(origin, "unknown_format", suffix or "(no suffix)"))
                    continue

                keyed = _KEYED.match(Path(entry.filename).stem)
                if keyed is None:
                    # Keyed by path instead would make `key_derivation` false
                    # for this unit and true for its neighbours, with nothing in
                    # the manifest saying which is which.
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
                        # A zip entry's timestamp is when the *export* wrote it,
                        # not when the note was written, and every entry in one
                        # export shares it. Passing it on would give a corpus a
                        # single date and call it history (ADR-0022).
                        modified_at=None,
                    )
                )

    # -- stage two: one thing, opened --------------------------------------

    def read(self, found: Found) -> bytes:
        """The entry's bytes, reached back through the archives it sits in."""
        outer, _, rest = found.origin.partition("!")
        archive = self.root if self.root.is_file() else self.root / outer
        if not archive.is_file():
            raise SourceError(f"{archive} is not where discovery said it was")
        return _entry(archive.read_bytes(), rest, found.origin)


def _entry(payload: bytes, path: str, origin: str) -> bytes:
    """Follow `a.zip!b.zip!c.md` down to the bytes of `c.md`."""
    name, _, rest = path.partition("!")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            body = archive.read(name)
    except (zipfile.BadZipFile, KeyError) as error:
        raise SourceError(f"{origin} could not be opened: {error}") from error
    return _entry(body, rest, origin) if rest else body
