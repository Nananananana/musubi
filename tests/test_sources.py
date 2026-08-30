"""Reading a folder somebody named, and refusing the ones they did not.

ADR-0007's boundary is where this file spends most of its effort, because it is
the boundary that makes every other promise checkable: musubi reads what it was
pointed at and nothing else.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from musubi.domain.record import Unit, unit_key
from musubi.errors import SourceError
from musubi.infrastructure.sources import FilesystemSource, ObsidianSource
from musubi.ports.source import Source


def link(source: Path, target: Path, *, directory: bool = False) -> None:
    """Make a symbolic link, or skip the test if this machine will not.

    Skipped by *capability* rather than by platform: Windows allows this with
    developer mode on, and these are the branches that guard ADR-0007's
    boundary. A test that never runs anywhere the developer works is a test
    that rots, so it runs wherever it can.
    """
    try:
        source.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as error:  # pragma: no cover - platform
        pytest.skip(f"this machine will not create symbolic links: {error}")


def vault(root: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def keys(source: FilesystemSource) -> list[str]:
    return [unit_key(*f.key_parts) for f in source.discover().found]


def reasons(source: FilesystemSource) -> dict[str, str]:
    return {s.origin: s.reason for s in source.discover().skipped}


# -- what it finds ----------------------------------------------------------


def test_a_folder_of_notes(tmp_path: Path) -> None:
    vault(tmp_path, {"a.md": "one", "design/gear.md": "two"})
    assert keys(FilesystemSource(tmp_path)) == ["a.md", "design/gear.md"]


def test_the_walk_is_sorted_at_every_level(tmp_path: Path) -> None:
    """ADR-0003. An unordered walk reaching an output is how two runs of the
    same folder stop being the same run."""
    vault(tmp_path, {f"{name}.md": "x" for name in "zmab"})
    vault(tmp_path, {f"z-dir/{name}.md": "x" for name in "cb"})
    assert keys(FilesystemSource(tmp_path)) == [
        "a.md",
        "b.md",
        "m.md",
        "z-dir/b.md",
        "z-dir/c.md",
        "z.md",
    ]


def test_the_media_type_comes_from_the_suffix(tmp_path: Path) -> None:
    vault(tmp_path, {"a.md": "x", "b.txt": "y"})
    found = {f.origin: f.media_type for f in FilesystemSource(tmp_path).discover().found}
    assert found == {"a.md": "text/markdown", "b.txt": "text/plain"}


def test_a_suffix_is_matched_whatever_its_case(tmp_path: Path) -> None:
    vault(tmp_path, {"A.MD": "x"})
    assert keys(FilesystemSource(tmp_path)) == ["A.MD"]


def test_the_size_is_reported_without_reading_anything(tmp_path: Path) -> None:
    vault(tmp_path, {"a.md": "hello"})
    (found,) = FilesystemSource(tmp_path).discover().found
    assert found.size_bytes == 5


def test_an_empty_folder_finds_nothing(tmp_path: Path) -> None:
    assert FilesystemSource(tmp_path).discover().found == ()


# -- what it will not read, and why -----------------------------------------


def test_an_unknown_format_is_skipped_by_name_before_it_is_opened(tmp_path: Path) -> None:
    vault(tmp_path, {"a.md": "x", "photo.png": "y", "notes.docx": "z"})
    assert reasons(FilesystemSource(tmp_path)) == {
        "notes.docx": "unknown_format",
        "photo.png": "unknown_format",
    }


def test_a_file_with_no_suffix_says_so(tmp_path: Path) -> None:
    vault(tmp_path, {"LICENSE": "x"})
    (skipped,) = FilesystemSource(tmp_path).discover().skipped
    assert skipped.reason == "unknown_format"
    assert skipped.detail == "(no suffix)"


def test_machinery_is_skipped_whole(tmp_path: Path) -> None:
    vault(tmp_path, {"a.md": "x", ".obsidian/workspace.md": "y", ".git/config.md": "z"})
    source = ObsidianSource(tmp_path)
    assert keys(source) == ["a.md"]
    assert reasons(source) == {".git": "machinery", ".obsidian": "machinery"}


def test_a_file_over_the_cap_is_skipped_and_the_cap_is_declared(tmp_path: Path) -> None:
    """ADR-0005: a bound that shortens coverage appears in the account rather
    than being inferred from a shortfall."""
    vault(tmp_path, {"big.md": "x" * 200})
    discovery = FilesystemSource(tmp_path, maximum_bytes=100).discover()
    assert [(s.reason, s.detail) for s in discovery.skipped] == [("too_large", "200 bytes")]
    assert any("larger than 100 bytes" in cap for cap in discovery.caps)


def test_the_suffix_list_is_declared_as_a_cap_too(tmp_path: Path) -> None:
    discovery = FilesystemSource(tmp_path).discover()
    assert any(".md" in cap and "suffixes" in cap for cap in discovery.caps)


# -- the boundary -----------------------------------------------------------


def test_a_link_pointing_out_of_the_root_is_not_followed(tmp_path: Path) -> None:
    """The whole of ADR-0007 in one case. A link in somebody's notes folder is
    how an ingestion tool ends up reading a file nobody meant to give it."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("not yours", encoding="utf-8")

    root = tmp_path / "vault"
    root.mkdir()
    (root / "a.md").write_text("mine", encoding="utf-8")
    link(root / "leak.md", outside / "secret.md")

    source = FilesystemSource(root)
    assert keys(source) == ["a.md"]
    assert reasons(source) == {"leak.md": "outside_the_root"}


def test_a_link_inside_the_root_is_followed(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    (root / "real").mkdir(parents=True)
    (root / "real" / "a.md").write_text("mine", encoding="utf-8")
    link(root / "alias.md", root / "real" / "a.md")

    assert keys(FilesystemSource(root)) == ["alias.md", "real/a.md"]


def test_a_directory_link_is_never_followed(tmp_path: Path) -> None:
    """Two links can point at each other, and a cycle in an unattended walk is
    a hang."""
    root = tmp_path / "vault"
    (root / "real").mkdir(parents=True)
    (root / "real" / "a.md").write_text("mine", encoding="utf-8")
    link(root / "loop", root, directory=True)

    source = FilesystemSource(root)
    assert keys(source) == ["real/a.md"]
    assert reasons(source) == {"loop": "directory_symlink"}


def test_the_home_directory_is_refused(tmp_path: Path) -> None:
    """A source that finds documents you forgot you had is a search tool, and
    this is not one."""
    with pytest.raises(SourceError, match="home directory"):
        FilesystemSource(Path.home())


def test_a_filesystem_root_is_refused() -> None:
    with pytest.raises(SourceError, match="filesystem root"):
        FilesystemSource(Path(Path.cwd().anchor))


def test_a_folder_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="does not exist"):
        FilesystemSource(tmp_path / "nowhere")


def test_a_file_is_not_a_folder(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    with pytest.raises(SourceError, match="not a folder"):
        FilesystemSource(tmp_path / "a.md")


# -- reading ----------------------------------------------------------------


def test_reading_gives_back_the_bytes_that_were_written(tmp_path: Path) -> None:
    vault(tmp_path, {"a.md": "紡ぎ"})
    source = FilesystemSource(tmp_path)
    (found,) = source.discover().found
    assert source.read(found) == "紡ぎ".encode()


def test_reading_something_that_has_gone_says_which(tmp_path: Path) -> None:
    vault(tmp_path, {"a.md": "x"})
    source = FilesystemSource(tmp_path)
    (found,) = source.discover().found
    (tmp_path / "a.md").unlink()
    with pytest.raises(SourceError, match=r"cannot read a.md"):
        source.read(found)


def test_reading_cannot_be_talked_into_leaving_the_root(tmp_path: Path) -> None:
    """`origin` is opaque above the source, but it is still a path, and a
    forged one must not become a file read."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("not yours", encoding="utf-8")
    root = tmp_path / "vault"
    root.mkdir()

    source = FilesystemSource(root)
    from musubi.ports.source import Found

    forged = Found(("..", "outside", "secret.md"), "text/markdown", 9, "../outside/secret.md")
    with pytest.raises(SourceError, match="outside"):
        source.read(forged)


# -- what a source declares -------------------------------------------------


def test_a_source_declares_how_it_derives_a_key(tmp_path: Path) -> None:
    """ADR-0006's weak form, stated rather than left to be discovered: moving a
    file looks like a delete plus an add, and the manifest says so."""
    assert FilesystemSource(tmp_path).key_derivation == "path"


def test_a_vault_names_itself_differently_from_a_bare_folder(tmp_path: Path) -> None:
    assert ObsidianSource(tmp_path).adapter == "obsidian@1"
    assert ObsidianSource(tmp_path).source_id == "vault"
    assert FilesystemSource(tmp_path).adapter == "filesystem@1"


def test_a_source_satisfies_the_port(tmp_path: Path) -> None:
    source: Source = ObsidianSource(tmp_path)
    assert source.discover().found == ()


# -- and the units it turns into --------------------------------------------


def test_a_discovery_becomes_units_with_stable_identities(tmp_path: Path) -> None:
    vault(tmp_path, {"design/gear.md": "the tent weighs 2.4kg"})
    source = FilesystemSource(tmp_path, source_id="vault")
    units = [
        Unit.of(source.source_id, f.key_parts, source.read(f), f.media_type)
        for f in source.discover().found
    ]
    assert [u.identity for u in units] == [("vault", "design/gear.md")]


def test_discovering_twice_finds_the_same_thing_in_the_same_order(tmp_path: Path) -> None:
    vault(tmp_path, {"b.md": "x", "a.md": "y", "c/d.md": "z"})
    source = FilesystemSource(tmp_path)
    assert source.discover() == source.discover()


def test_a_summary_says_both_halves(tmp_path: Path) -> None:
    vault(tmp_path, {"a.md": "x", "b.png": "y"})
    assert FilesystemSource(tmp_path).discover().summary() == "1 to read, 1 skipped"
