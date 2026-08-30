"""A folder the owner named, walked in a fixed order.

[ADR-0007] *A folder the owner named.* Never the home directory, never every
document on the machine -- `kiseki` states the reason exactly: a source that
finds documents somebody forgot they had is a search tool, and this is not one.
Pointing at a home directory is refused rather than obeyed.

[ADR-0003] The walk is sorted at every level, so two runs over the same folder
produce the same order on any filesystem.

[ADR-0006] The key is the path relative to the root, which is the weak form and
is declared as such: moving a file looks like a delete plus an add. The manifest
carries ``key_derivation: path`` so a reader can see it rather than having to
know it.

## Symbolic links

A vault can contain them, and following them naively is how an ingestion tool
reads `/etc/shadow` because somebody put a link in their notes folder years ago.

- A **file** link is followed only if it resolves inside the root, and skipped
  with a reason if it does not.
- A **directory** link is never followed. Two links can point at each other, and
  a cycle in an unattended walk is a hang; and even without one, a directory
  link produces the same file under two keys, which [ADR-0006] says is a
  duplicate identity and stops the run.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ...errors import SourceError
from ...ports.source import Discovery, Found, Skipped

__all__ = ["MACHINERY", "MAXIMUM_BYTES", "MEDIA_TYPES", "FilesystemSource", "ObsidianSource"]

#: What a suffix means. A format with no entry here is skipped by name, before
#: the file is opened, and reported -- which is cheaper and more honest than
#: reading it and failing to convert it.
MEDIA_TYPES: dict[str, str] = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".mdown": "text/markdown",
    ".mkd": "text/markdown",
    ".txt": "text/plain",
    ".text": "text/plain",
}

#: Directories that are machinery rather than writing. Skipped whole.
MACHINERY: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".obsidian",
        ".trash",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
    }
)

#: A generous cap. Past it, a `.txt` is a data file wearing a note's extension,
#: and reading it costs more than it is worth. Named in the manifest as a cap,
#: because a bound that shortens coverage has to appear there rather than be
#: inferred from a shortfall ([ADR-0005]).
MAXIMUM_BYTES = 8 * 1024 * 1024


class FilesystemSource:
    """Satisfies :class:`~musubi.ports.source.Source`.

    Reads one folder, by suffix, in sorted order, opening nothing until asked.
    """

    key_derivation = "path"

    def __init__(
        self,
        root: Path,
        *,
        source_id: str = "filesystem",
        adapter: str = "filesystem@1",
        media_types: dict[str, str] | None = None,
        machinery: Iterable[str] = MACHINERY,
        maximum_bytes: int = MAXIMUM_BYTES,
    ) -> None:
        self.root = _accept(root)
        self.source_id = source_id
        self.adapter = adapter
        self._media_types = dict(MEDIA_TYPES if media_types is None else media_types)
        self._machinery = frozenset(machinery)
        self._maximum_bytes = maximum_bytes

    # -- stage one: what is there ------------------------------------------

    def discover(self) -> Discovery:
        found: list[Found] = []
        skipped: list[Skipped] = []
        self._walk(self.root, found, skipped)
        return Discovery(
            found=tuple(found),
            skipped=tuple(skipped),
            caps=(
                f"files larger than {self._maximum_bytes} bytes are not read",
                f"only these suffixes are read: {', '.join(sorted(self._media_types))}",
            ),
        )

    def _walk(self, directory: Path, found: list[Found], skipped: list[Skipped]) -> None:
        # Sorted, at every level. An unordered walk reaching an output is how
        # two runs of the same folder stop being the same run (ADR-0003).
        for entry in sorted(directory.iterdir(), key=lambda p: p.name):
            relative = entry.relative_to(self.root).as_posix()

            if entry.is_dir():
                if entry.name in self._machinery:
                    skipped.append(Skipped(relative, "machinery", entry.name))
                elif entry.is_symlink():
                    # Never followed: two links can point at each other, and a
                    # cycle in an unattended walk is a hang.
                    skipped.append(Skipped(relative, "directory_symlink"))
                else:
                    self._walk(entry, found, skipped)
                continue

            self._consider(entry, relative, found, skipped)

    def _consider(
        self, entry: Path, relative: str, found: list[Found], skipped: list[Skipped]
    ) -> None:
        if entry.is_symlink() and not self._inside(entry):
            # The whole of ADR-0007's boundary, in one check. A link in
            # somebody's notes folder is how an ingestion tool ends up reading
            # a file nobody meant to give it.
            skipped.append(Skipped(relative, "outside_the_root"))
            return

        media_type = self._media_types.get(entry.suffix.lower())
        if media_type is None:
            skipped.append(Skipped(relative, "unknown_format", entry.suffix or "(no suffix)"))
            return

        size = entry.stat().st_size
        if size > self._maximum_bytes:
            skipped.append(Skipped(relative, "too_large", f"{size} bytes"))
            return

        found.append(
            Found(
                key_parts=entry.relative_to(self.root).parts,
                media_type=media_type,
                size_bytes=size,
                origin=relative,
            )
        )

    def _inside(self, entry: Path) -> bool:
        try:
            entry.resolve().relative_to(self.root)
        except (OSError, ValueError):
            return False
        return True

    # -- stage two: the bytes of one thing ---------------------------------

    def read(self, found: Found) -> bytes:
        path = self.root / found.origin
        if not self._inside(path):
            raise SourceError(f"{found.origin} resolves outside {self.root}")
        try:
            return path.read_bytes()
        except OSError as error:
            raise SourceError(f"cannot read {found.origin}: {error}") from error


class ObsidianSource(FilesystemSource):
    """A vault. A filesystem source that knows what Obsidian leaves lying about.

    There is no Obsidian *format* -- a vault is Markdown in a folder, which is
    the whole reason it is a pleasant thing to read. What it needs is the
    machinery list, and that is the difference between the two classes.
    """

    def __init__(
        self,
        root: Path,
        *,
        source_id: str = "vault",
        machinery: Iterable[str] = MACHINERY,
        maximum_bytes: int = MAXIMUM_BYTES,
    ) -> None:
        super().__init__(
            root,
            source_id=source_id,
            adapter="obsidian@1",
            machinery=machinery,
            maximum_bytes=maximum_bytes,
        )


def _accept(root: Path) -> Path:
    """Refuse a root nobody should point an ingestion tool at.

    ADR-0007 in one function. The home directory holds the browser profile, the
    ssh keys and the shell history; a filesystem root holds everything. Reading
    either is not what "a folder the owner named" means, and a tool that obeys
    the instruction anyway is a search tool.
    """
    resolved = root.expanduser().resolve()
    if not resolved.exists():
        raise SourceError(f"{resolved} does not exist")
    if not resolved.is_dir():
        raise SourceError(f"{resolved} is not a folder")
    if resolved == resolved.parent:
        raise SourceError(
            f"{resolved} is a filesystem root; musubi reads a folder somebody named, "
            f"not a whole machine"
        )
    if resolved == Path.home().resolve():
        raise SourceError(
            f"{resolved} is the home directory. musubi reads a folder somebody named: "
            f"a source that finds documents you forgot you had is a search tool, and "
            f"this is not one. Name the folder."
        )
    return resolved
