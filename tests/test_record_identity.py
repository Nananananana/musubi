"""The unit of sync, its key, and how a re-read tells what changed.

ADR-0006: identity is ``(source_id, unit_key)`` and change is ``content_hash``.
ADR-0014: the key is normalized to NFC and the content never is, because the
same vault synced from a Mac and from a PC otherwise produces two corpora with
disjoint keys and every re-sync looks like a full rewrite.
"""

from __future__ import annotations

import unicodedata

import pytest
from hypothesis import given
from hypothesis import strategies as st

from musubi.domain.hashing import content_hash
from musubi.domain.record import Unit, compare, unit_key

# -- keys -------------------------------------------------------------------


def test_a_key_joins_its_parts_with_a_forward_slash() -> None:
    assert unit_key("design", "gear.md") == "design/gear.md"


def test_a_single_part_is_a_key() -> None:
    assert unit_key("gear.md") == "gear.md"


def test_a_key_is_normalized_to_nfc() -> None:
    """The whole of ADR-0014. macOS hands back NFD, Windows and Linux hand back
    NFC, and they are the same name to everybody who looks at it."""
    decomposed = unicodedata.normalize("NFD", "café.md")
    composed = unicodedata.normalize("NFC", "café.md")
    assert decomposed != composed, "the fixture is not testing anything otherwise"
    assert unit_key(decomposed) == unit_key(composed)
    assert unit_key(decomposed) == composed


def test_a_key_does_not_fold_case() -> None:
    """`README.md` and `readme.md` are two files on Linux and two documents in
    somebody's corpus. Folding would lose one to solve a nuisance."""
    assert unit_key("README.md") != unit_key("readme.md")


def test_a_key_is_not_compatibility_normalized() -> None:
    """NFKC would turn ｕｒｌ into url and ① into 1. The key names a file the
    owner has; it does not get to improve the name."""
    assert unit_key("ＵＲＬ.md") != unit_key("URL.md")


def test_a_part_may_not_climb_out_of_its_own_directory() -> None:
    """A key becomes an output filename (ADR-0013), so this is a path traversal
    check done once in the domain rather than forgotten in one emitter."""
    with pytest.raises(ValueError, match="climb"):
        unit_key("notes", "..", "secrets.md")


def test_a_part_may_not_be_the_current_directory() -> None:
    with pytest.raises(ValueError, match="climb"):
        unit_key("notes", ".", "gear.md")


def test_a_part_may_not_forge_structure_with_a_separator() -> None:
    with pytest.raises(ValueError, match="separator"):
        unit_key("notes/design", "gear.md")


def test_a_backslash_is_a_separator_too() -> None:
    """A source on Windows that hands over a raw relative path rather than its
    parts would otherwise produce a key nothing on Linux could match."""
    with pytest.raises(ValueError, match="separator"):
        unit_key("notes\\design")


def test_an_empty_part_is_refused() -> None:
    with pytest.raises(ValueError, match="empty"):
        unit_key("design", "", "gear.md")


def test_a_key_with_no_parts_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one"):
        unit_key()


# -- units ------------------------------------------------------------------


def test_a_unit_hashes_its_own_content() -> None:
    unit = Unit.of("vault", ("gear.md",), b"the tent weighs 2.4kg", "text/markdown")
    assert unit.unit_key == "gear.md"
    assert unit.content_hash == content_hash(b"the tent weighs 2.4kg")
    assert unit.identity == ("vault", "gear.md")


def test_the_content_hash_is_over_the_bytes_and_not_over_a_normalized_form() -> None:
    """ADR-0014's other half. Normalizing the owner's text would be an
    unrequested rewrite, and it would move every offset the trace map reports."""
    decomposed = unicodedata.normalize("NFD", "café").encode()
    composed = unicodedata.normalize("NFC", "café").encode()
    left = Unit.of("vault", ("a.md",), decomposed, "text/markdown")
    right = Unit.of("vault", ("a.md",), composed, "text/markdown")
    assert left.content_hash != right.content_hash


def test_two_units_from_different_sources_are_different_things() -> None:
    left = Unit.of("vault", ("gear.md",), b"x", "text/markdown")
    right = Unit.of("notion", ("gear.md",), b"x", "text/markdown")
    assert left.identity != right.identity


# -- comparing a re-read against what was held ------------------------------


def held(*units: Unit) -> dict[str, Unit]:
    return {unit.unit_key: unit for unit in units}


def a_unit(key: str, content: bytes) -> Unit:
    return Unit.of("vault", (key,), content, "text/markdown")


def test_an_unchanged_re_read_reports_nothing_to_do() -> None:
    """The property ADR-0006 exists for: a re-export that changed nothing
    produces an empty diff, whatever the bytes of the archive did."""
    before = [a_unit("a.md", b"one"), a_unit("b.md", b"two")]
    change = compare(held(*before), before)
    assert change.added == ()
    assert change.changed == ()
    assert change.removed == ()
    assert [u.unit_key for u in change.unchanged] == ["a.md", "b.md"]
    assert change.is_empty, "nothing to do is not the same as nothing found"


def test_a_new_unit_is_added() -> None:
    change = compare(held(a_unit("a.md", b"one")), [a_unit("a.md", b"one"), a_unit("b.md", b"two")])
    assert [u.unit_key for u in change.added] == ["b.md"]


def test_a_rewritten_unit_is_changed_not_re_added() -> None:
    change = compare(held(a_unit("a.md", b"one")), [a_unit("a.md", b"ONE")])
    assert [u.unit_key for u in change.changed] == ["a.md"]
    assert change.added == ()


def test_a_unit_that_is_no_longer_there_is_removed() -> None:
    change = compare(held(a_unit("a.md", b"one"), a_unit("b.md", b"two")), [a_unit("a.md", b"one")])
    assert [u.unit_key for u in change.removed] == ["b.md"]


def test_the_report_is_ordered_by_key_whatever_order_the_source_walked_in() -> None:
    """ADR-0003. An unordered iteration reaching an output is how two runs of
    the same input stop being the same run."""
    units = [a_unit("c.md", b"3"), a_unit("a.md", b"1"), a_unit("b.md", b"2")]
    change = compare({}, units)
    assert [u.unit_key for u in change.added] == ["a.md", "b.md", "c.md"]


def test_two_units_with_the_same_key_stop_the_run() -> None:
    """ADR-0014's cost, made loud. On Linux two files can differ only by
    normalization; picking one would silently drop a document."""
    with pytest.raises(ValueError, match="twice"):
        compare({}, [a_unit("a.md", b"one"), a_unit("a.md", b"two")])


def test_units_from_the_wrong_source_are_refused() -> None:
    """A comparison mixing two sources would report every unit of one as added
    and every unit of the other as removed, which is a very confident wrong
    answer."""
    mine = a_unit("a.md", b"one")
    theirs = Unit.of("notion", ("b.md",), b"two", "text/markdown")
    with pytest.raises(ValueError, match="one source"):
        compare({}, [mine, theirs])


def test_nothing_at_all_is_an_empty_report() -> None:
    change = compare({}, [])
    assert change.is_empty
    assert change.summary() == "0 new, 0 changed, 0 unchanged, 0 gone"


@given(st.lists(st.text(alphabet="abc", min_size=1, max_size=3), max_size=8, unique=True))
def test_comparing_a_read_against_itself_is_always_empty(keys: list[str]) -> None:
    units = [a_unit(f"{key}.md", key.encode()) for key in keys]
    change = compare(held(*units), units)
    assert change.is_empty
    assert len(change.unchanged) == len(units)
