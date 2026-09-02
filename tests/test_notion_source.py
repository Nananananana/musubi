"""The source ADR-0006's argument was aimed at, and the one it contradicts itself about.

Every fixture is a real archive built by `an_export()` — nested, the way a Notion
export nests, because the nesting is the part that would be got wrong. The shape
comes from a real export that was opened and measured; nothing here is a guess
about what Notion emits, and the two places where evidence ran out say so.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from musubi.errors import SourceError
from musubi.infrastructure.sources import NotionSource

#: A real export's page id, in the shape Notion writes it. This one is invented;
#: what is copied from the real export is the *form* -- 32 lowercase hex
#: characters, one space after the title.
PAGE = "1fe43ad4ff6680f19971c582699521cf"
OTHER = "2ab99c1d40aa71e2b883d411c9e07733"


def an_export(entries: dict[str, bytes], *, nested: bool = True) -> bytes:
    """One archive, optionally wrapped in another the way Notion wraps them."""
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as archive:
        for name, body in entries.items():
            archive.writestr(name, body)
    if not nested:
        return inner.getvalue()

    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as archive:
        archive.writestr("ExportBlock-5d9cf2d0-Part-1.zip", inner.getvalue())
    return outer.getvalue()


def export_at(tmp_path: Path, entries: dict[str, bytes], **kwargs: bool) -> Path:
    root = tmp_path / "export"
    root.mkdir(exist_ok=True)
    (root / "f3c30fde_ExportBlock-5d9cf2d0.zip").write_bytes(an_export(entries, **kwargs))
    return root


# -- the key ----------------------------------------------------------------


def test_a_page_is_keyed_by_its_id_and_not_its_title(tmp_path: Path) -> None:
    """The key becomes the output filename (ADR-0013), so keying by title would
    make a renamed page arrive as a new document with no history."""
    root = export_at(tmp_path, {f"Journal {PAGE}.md": b"# Journal\n"})
    found = NotionSource(root).discover().found

    assert len(found) == 1
    assert found[0].key_parts == (f"{PAGE}.md",)
    assert "Journal" not in found[0].key_parts[0]


def test_the_derivation_is_named_in_full(tmp_path: Path) -> None:
    """`path` would be a lie and `notion` would be vague. The manifest carries
    this, and a consumer reads it to know which weakness applies."""
    assert NotionSource(export_at(tmp_path, {})).key_derivation == "notion-page-id"


def test_renaming_the_page_does_not_change_the_key(tmp_path: Path) -> None:
    """The whole reason for keying by the id, asserted rather than asserted
    about: the same page under two titles is one unit."""
    before = NotionSource(export_at(tmp_path, {f"Journal {PAGE}.md": b"x"})).discover()
    after = NotionSource(export_at(tmp_path, {f"Diary Renamed {PAGE}.md": b"x"})).discover()

    assert before.found[0].key_parts == after.found[0].key_parts


def test_a_file_with_no_page_id_is_skipped_not_keyed_by_path(tmp_path: Path) -> None:
    """Falling back to the path for these would make `key_derivation` true for
    some units in the run and false for others, with nothing saying which."""
    root = export_at(tmp_path, {f"Journal {PAGE}.md": b"x", "loose-note.md": b"y"})
    discovery = NotionSource(root).discover()

    assert [f.key_parts for f in discovery.found] == [(f"{PAGE}.md",)]
    assert [s.reason for s in discovery.skipped] == ["no_page_id"]


@pytest.mark.parametrize(
    "name",
    [
        f"Journal {PAGE.upper()}.md",  # Notion writes lowercase
        f"Journal {PAGE[:31]}.md",  # 31 characters is not an id
        f"Journal{PAGE}.md",  # no separating space
    ],
)
def test_something_that_only_looks_like_a_page_id_is_not_one(tmp_path: Path, name: str) -> None:
    discovery = NotionSource(export_at(tmp_path, {name: b"x"})).discover()
    assert not discovery.found
    assert [s.reason for s in discovery.skipped] == ["no_page_id"]


# -- the nesting ------------------------------------------------------------


def test_the_archive_inside_the_archive_is_followed(tmp_path: Path) -> None:
    """A real export is `Export.zip` holding `ExportBlock-…-Part-1.zip` holding
    the pages. A walk that stopped at the first level would find nothing and
    report success."""
    source = NotionSource(export_at(tmp_path, {f"Journal {PAGE}.md": b"# Journal\n"}))
    found = source.discover().found

    assert found[0].origin.count("!") == 2, "outer, inner, entry"
    assert source.read(found[0]) == b"# Journal\n"


def test_a_flat_archive_works_too(tmp_path: Path) -> None:
    """Not every export nests, and a source that required it would refuse a
    valid one."""
    root = tmp_path / "flat"
    root.mkdir()
    (root / "export.zip").write_bytes(an_export({f"J {PAGE}.md": b"x"}, nested=False))
    assert NotionSource(root).discover().found[0].key_parts == (f"{PAGE}.md",)


def test_the_depth_is_capped_and_the_cap_is_reported(tmp_path: Path) -> None:
    """An archive that contains itself is a thing a downloaded file can be.

    `maximum_depth=1` follows one level of nesting, which is what a real export
    needs -- so the refusal is tested at zero, where nothing nested is followed
    and the archive that would have held the pages is reported instead of
    silently producing an empty run.
    """
    source = NotionSource(export_at(tmp_path, {f"J {PAGE}.md": b"x"}), maximum_depth=0)
    discovery = source.discover()

    assert any("levels deep" in cap for cap in discovery.caps)
    assert [s.reason for s in discovery.skipped] == ["too_deep"]
    assert not discovery.found


def test_one_level_of_nesting_is_what_a_real_export_needs(tmp_path: Path) -> None:
    source = NotionSource(export_at(tmp_path, {f"J {PAGE}.md": b"x"}), maximum_depth=1)
    assert source.discover().found[0].key_parts == (f"{PAGE}.md",)


def test_a_corrupt_archive_is_reported_rather_than_raised(tmp_path: Path) -> None:
    root = tmp_path / "export"
    root.mkdir()
    (root / "broken.zip").write_bytes(b"PK\x03\x04 not really a zip")
    discovery = NotionSource(root).discover()

    assert not discovery.found
    assert [s.reason for s in discovery.skipped] == ["unreadable_archive"]


# -- reading ----------------------------------------------------------------


def test_the_bytes_come_back_exactly(tmp_path: Path) -> None:
    body = "# 見出し\n日本語の本文\n".encode()
    root = export_at(tmp_path, {f"Note {PAGE}.md": body})
    source = NotionSource(root)
    assert source.read(source.discover().found[0]) == body


def test_discovery_opens_nothing_it_was_not_asked_for(tmp_path: Path) -> None:
    """ADR-0007's two stages. `discover` reports sizes from the archive's own
    directory; the bytes are not read until `read` asks."""
    root = export_at(tmp_path, {f"Note {PAGE}.md": b"12345"})
    found = NotionSource(root).discover().found[0]
    assert found.size_bytes == 5


def test_a_missing_archive_is_a_source_error(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="does not exist"):
        NotionSource(tmp_path / "nowhere")


def test_a_folder_with_no_archive_says_what_it_wanted(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SourceError, match=r"holds no \.zip"):
        NotionSource(empty).discover()


# -- the time axis, which the export does not carry -------------------------


def test_no_modification_time_is_offered(tmp_path: Path) -> None:
    """Measured on a real export: the outer and inner entries share one
    timestamp, to the second, and it is when the *export* ran.

    Handing that on would give every page in a corpus the same date and call it
    history -- the failure ADR-0022 exists to prevent, arriving from the other
    direction. `None` gives the run's time, which is equally uniform and does
    not pretend to be anything else.
    """
    root = export_at(tmp_path, {f"Note {PAGE}.md": b"x", f"Other {OTHER}.md": b"y"})
    assert all(f.modified_at is None for f in NotionSource(root).discover().found)


# -- what it says about itself ----------------------------------------------


def test_the_caps_say_what_bounded_the_discovery(tmp_path: Path) -> None:
    """ADR-0005: a bound appears in the manifest rather than being inferred from
    a shortfall."""
    caps = NotionSource(export_at(tmp_path, {})).discover().caps
    assert any("levels deep" in cap for cap in caps)
    assert any("page id" in cap for cap in caps)


def test_a_csv_is_recognised_and_then_skipped_for_want_of_a_converter(tmp_path: Path) -> None:
    """A database view. Listing the media type means discovery *reports* it
    instead of passing over it in silence; there is no converter, so the
    pipeline skips it with a reason."""
    root = export_at(tmp_path, {f"Table {PAGE}.csv": b"a,b\n1,2\n"})
    found = NotionSource(root).discover().found

    assert found[0].media_type == "text/csv"
    assert found[0].key_parts == (f"{PAGE}.csv",)
