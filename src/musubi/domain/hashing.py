"""Content hashes that name their algorithm, and a canonical form to hash.

ADR-0015. A hash is ``sha256:`` followed by 64 lowercase hex characters, and the
prefix is the decision: it costs seven bytes and it means a future change of
algorithm is a *data* change an old reader can detect and refuse, rather than a
silent reinterpretation of a field that looks the same and means something else.

Structured values are hashed over a canonical form, following **RFC 8785 (JSON
Canonicalization Scheme)** for the clauses musubi's inputs reach: keys ordered
lexicographically by UTF-16 code unit, minimal separators, no insignificant
whitespace. Floating-point numbers -- the specification's hardest clause and the
one musubi does not need -- are refused rather than approximated.

Following a published specification rather than inventing one is what lets
somebody re-derive a ``run_id`` in another language, which is the whole of what
``musubi verify`` is for.
"""

from __future__ import annotations

import hashlib
import json
import re

__all__ = ["ALGORITHM", "Canonical", "canonical", "content_hash", "hash_of", "is_hash"]

#: The one algorithm, named in every value it produces.
ALGORITHM = "sha256"

_SHAPE = re.compile(r"^sha256:[0-9a-f]{64}$")

#: What the canonicalizer accepts. Deliberately not `float`: see ADR-0015.
type Canonical = str | int | bool | list[Canonical] | dict[str, Canonical] | None


def content_hash(data: bytes | str) -> str:
    """The hash of these bytes, or of this text encoded as UTF-8.

    Over what was actually read, never over an idea of it -- a byte-order mark
    is part of the bytes it is in, and two files that differ only by one are two
    files.
    """
    payload = data.encode("utf-8") if isinstance(data, str) else data
    return f"{ALGORITHM}:{hashlib.sha256(payload).hexdigest()}"


def is_hash(text: str) -> bool:
    """Is this the shape of a hash musubi wrote?

    Strict about case on both halves. A hash is compared as a string in every
    contract that carries one, so two spellings of the same digest are two
    different values and the looser check would let them both in.
    """
    return bool(_SHAPE.match(text))


def hash_of(value: Canonical) -> str:
    """The hash of a structure, over its canonical form.

    Two structures that differ only in the order they were built in hash the
    same, which is what makes a ``run_id`` a property of the inputs rather than
    of the code that assembled them.
    """
    return content_hash(canonical(value))


def canonical(value: Canonical) -> str:
    """RFC 8785, for the subset musubi uses.

    Calling this "RFC 8785" without qualification would be a claim musubi does
    not meet: it implements the clauses its input domain reaches and refuses
    input that would reach the rest. That is a smaller promise, and it is stated
    rather than assumed (ADR-0015).
    """
    out: list[str] = []
    _write(value, out)
    return "".join(out)


def _write(value: Canonical, out: list[str]) -> None:
    # `bool` before `int`: it is a subclass, and the obvious implementation
    # writes `true` as `1`.
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, str):
        # JSON string escaping is JCS string escaping. `ensure_ascii=False`
        # because JCS emits the characters themselves rather than \u escapes.
        out.append(json.dumps(value, ensure_ascii=False))
    elif isinstance(value, float):
        raise TypeError(
            "a floating point number cannot be canonicalized: RFC 8785's number "
            "serialization is the one clause musubi does not implement, and nothing "
            "that determines a run is a float. See docs/adr/0015-a-hash-names-its-algorithm.md"
        )
    elif isinstance(value, int):
        out.append(str(value))
    elif isinstance(value, list):
        out.append("[")
        for index, item in enumerate(value):
            if index:
                out.append(",")
            _write(item, out)
        out.append("]")
    elif isinstance(value, dict):
        out.append("{")
        # A non-string key is refused by the sort key below, before any of it
        # is written -- there is no second check here to fall out of step.
        for index, key in enumerate(sorted(value, key=_utf16_order)):
            if index:
                out.append(",")
            _write(key, out)
            out.append(":")
            _write(value[key], out)
        out.append("}")
    else:
        raise TypeError(f"a {type(value).__name__} cannot be canonicalized")


def _utf16_order(key: object) -> bytes:
    """RFC 8785 sorts by UTF-16 code unit, which is not Python's code-point order.

    They agree for everything below the basic multilingual plane, which is every
    key musubi writes. Following the specification anyway is what makes the
    canonical form reproducible by an implementation that is not this one.
    """
    if not isinstance(key, str):
        raise TypeError(f"object keys are strings, not {type(key).__name__}")
    return key.encode("utf-16-be", errors="surrogatepass")
