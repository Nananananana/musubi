"""Content hashes that name their algorithm, and a canonical form to hash.

ADR-0015. The prefix costs seven bytes and means a future change of algorithm is
a data change an old reader can refuse, rather than a silent reinterpretation of
a field that looks the same and means something else.

The canonical form follows RFC 8785 for the subset musubi's inputs reach, and
refuses the input that would reach the rest.
"""

from __future__ import annotations

import hashlib

import pytest
from hypothesis import given
from hypothesis import strategies as st

from musubi.domain.hashing import ALGORITHM, canonical, content_hash, hash_of, is_hash

# -- content hashes ---------------------------------------------------------


def test_a_hash_names_its_algorithm() -> None:
    assert content_hash(b"hello").startswith("sha256:")
    assert ALGORITHM == "sha256"


def test_a_hash_is_the_one_everybody_else_computes() -> None:
    """Comparable across the four sibling projects without translation."""
    expected = hashlib.sha256(b"hello").hexdigest()
    assert content_hash(b"hello") == f"sha256:{expected}"


def test_text_is_hashed_as_utf8() -> None:
    assert content_hash("紡ぎ") == content_hash("紡ぎ".encode())


def test_a_byte_order_mark_is_part_of_the_bytes_it_is_in() -> None:
    """Hashing happens over what was read, not over an idea of it."""
    assert content_hash(b"\xef\xbb\xbfhello") != content_hash(b"hello")


def test_the_shape_is_checkable() -> None:
    assert is_hash(content_hash(b""))
    assert not is_hash("sha256:tooshort")
    assert not is_hash(hashlib.sha256(b"").hexdigest()), "a bare digest names no algorithm"
    assert not is_hash("SHA256:" + "a" * 64), "upper case is a different string"
    assert not is_hash("sha256:" + "A" * 64), "and so are upper-case digits"


# -- the canonical form -----------------------------------------------------


def test_an_object_is_written_without_whitespace() -> None:
    assert canonical({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_keys_are_sorted_by_utf16_code_unit() -> None:
    """RFC 8785's ordering, which is not Python's for anything outside the
    basic multilingual plane. musubi's own keys are ASCII, where the two agree;
    following the specification anyway is what lets somebody re-derive a run_id
    in another language."""
    assert canonical({"\U0001f600": 1, "￿": 2}) == '{"\U0001f600":1,"￿":2}'


def test_an_array_keeps_its_order() -> None:
    assert canonical(["b", "a"]) == '["b","a"]'


def test_the_literals() -> None:
    assert canonical(True) == "true"
    assert canonical(False) == "false"
    assert canonical(None) == "null"


def test_a_boolean_is_not_written_as_a_number() -> None:
    """`bool` is a subclass of `int`, and the obvious implementation writes
    `true` as `1`."""
    assert canonical({"ok": True}) == '{"ok":true}'


def test_integers_have_no_decoration() -> None:
    assert canonical([0, -1, 1000000]) == "[0,-1,1000000]"


def test_non_ascii_survives_rather_than_being_escaped() -> None:
    assert canonical("紡ぎ") == '"紡ぎ"'


def test_control_characters_are_escaped() -> None:
    assert canonical("a\nb") == '"a\\nb"'


def test_a_float_is_refused() -> None:
    """The one clause of RFC 8785 that is hard to get exactly right, and the one
    musubi's inputs never need. Refusing is a smaller promise than implementing
    it badly (ADR-0015)."""
    with pytest.raises(TypeError, match="floating point"):
        canonical({"coverage": 0.99})


def test_something_that_is_not_a_document_is_refused() -> None:
    with pytest.raises(TypeError, match="cannot be canonicalized"):
        canonical({"when": object()})


def test_a_non_string_key_is_refused() -> None:
    with pytest.raises(TypeError, match="keys are strings"):
        canonical({1: "one"})


# -- hashing a structure ----------------------------------------------------


def test_the_same_structure_hashes_the_same_whatever_order_it_was_built_in() -> None:
    assert hash_of({"a": 1, "b": [1, 2]}) == hash_of({"b": [1, 2], "a": 1})


def test_a_different_structure_hashes_differently() -> None:
    assert hash_of({"a": 1}) != hash_of({"a": 2})


def test_a_nested_structure_is_canonical_all_the_way_down() -> None:
    assert canonical({"o": {"z": 1, "a": 2}}) == '{"o":{"a":2,"z":1}}'


@given(
    st.dictionaries(
        st.text(max_size=8),
        st.one_of(st.text(max_size=8), st.integers(), st.booleans(), st.none()),
        max_size=6,
    )
)
def test_canonicalizing_is_stable(value: dict[str, object]) -> None:
    assert canonical(value) == canonical(dict(reversed(list(value.items()))))
