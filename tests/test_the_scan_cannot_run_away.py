"""`Signature.find` terminates, and this is what that rests on.

`tools/mutate.py` found this by accident and it is the more useful half of what
it found. Mutating the advance in `find`'s `while` loop produces code that does
not terminate: the first sweep sat spinning with no output and stopped on the
fifth module. The docstring said *nothing here can backtrack*, which is true of
what is written and **one character away from being false**, and nothing
anywhere asserted it.

Two tests, because two different things can be said and they are not equally
strong:

- **the precondition, exactly.** `at` strictly increases every iteration only
  because `end >= start + len(prefix)` and the prefix is never empty. That is a
  validation in `__post_init__`, and it can be checked exactly.
- **the behaviour, bluntly.** A worst-case input, in a subprocess with a
  deadline. It cannot prove termination; it converts a hang into a failure,
  which is the difference between a red build and an overnight job.

`mamori` made the same distinction on the same day about a different constant,
and put it better: **where the bound can be counted, count it; where it cannot,
saying so is more accurate than a number.** The bound here *can* be counted --
at most `len(text) + 1` iterations -- so it is written into the docstring rather
than described.
"""

from __future__ import annotations

import itertools
import subprocess
import sys
import textwrap

import pytest

from musubi.domain.screening import BASE62, Signature
from musubi.infrastructure.screeners.signatures import SIGNATURES

#: Long enough that a quadratic scan is visibly slower than a linear one, small
#: enough that the linear one is instant. A real note holding a base64 image is
#: this size.
WORST_CASE = 200_000

#: Ten times what the whole scan takes when it is linear, on the slowest
#: machine in CI. A deadline that a correct implementation can reach is a flaky
#: test; one a broken implementation can reach is not a test.
DEADLINE = 60.0


def test_a_signature_cannot_have_an_empty_prefix() -> None:
    """The validation that buys termination.

    It reads as a rule about signature quality -- an entropy filter wearing a
    signature's clothes -- and it is also the reason `at` cannot stand still.
    With an empty prefix, `end` can equal `start` can equal `at`, and the loop
    finds the same position forever.
    """
    with pytest.raises(ValueError, match="no prefix"):
        Signature(
            id="empty",
            label="a signature with nothing to look for",
            prefix="",
            alphabet=BASE62,
            minimum=16,
            evidence="none; this must not be constructible",
            since="2026-09-04",
        )


def test_every_shipped_signature_has_the_property_the_bound_rests_on() -> None:
    """Checked over the shipped list rather than over one example.

    A rule enforced in a constructor and violated by the data would be enforced
    nowhere, and the list is data that grows.
    """
    assert SIGNATURES, "no signatures; this guard would run zero times"
    for signature in SIGNATURES:
        assert signature.prefix, signature.id


def test_the_matches_advance_and_never_repeat() -> None:
    """The observable shadow of `at` increasing.

    Not a proof -- a scan could advance and still revisit -- but a run that
    returned overlapping or out-of-order spans would mean the pointer moved
    backwards somewhere, which is the failure this file is about.
    """
    aws = next(s for s in SIGNATURES if s.id == "aws.access-key")
    text = " ".join(["AKIAIOSFODNN7EXAMPLE"] * 50)
    spans = aws.find(text)

    assert len(spans) == 50
    assert spans == sorted(spans, key=lambda span: span.start)
    for earlier, later in itertools.pairwise(spans):
        assert earlier.end <= later.start, "two matches claim the same characters"


#: A text that is nothing but prefixes the boundary rejects, so that every
#: occurrence takes the branch that advances by one character -- the most
#: iterations per byte this scan can be made to do.
#:
#: The leading `A` is the whole trick, and the first attempt at this file got it
#: wrong. Without it the occurrence at offset 0 has **no preceding character**,
#: passes the boundary, and the alphabet run swallows the entire string in one
#: iteration: a fixture measuring the fastest path while claiming to measure the
#: slowest. It matched once instead of never, which is what gave it away, and is
#: why the count is asserted rather than only the exit code.
PROBE = textwrap.dedent(
    """
    from musubi.infrastructure.screeners.signatures import SIGNATURES

    aws = next(s for s in SIGNATURES if s.id == "aws.access-key")
    text = "A" + "AKIA" * ({size} // 4)
    print(len(aws.find(text)))
    """
).strip()


def test_the_worst_case_input_finishes() -> None:
    """In a subprocess, with a deadline, because the failure mode is a hang.

    An in-process assertion cannot fail here -- it can only never return, and
    pytest has nothing to say about a test that is still running. A subprocess
    with a timeout turns that into a red build.

    The same reason `tools/mutate.py` has a `TIMEOUT`: a hang is a result, and
    reporting it as one is what stops it becoming an overnight job.
    """
    finished = subprocess.run(  # noqa: S603 - the interpreter, and a literal in this file
        [sys.executable, "-c", PROBE.format(size=WORST_CASE)],
        capture_output=True,
        text=True,
        timeout=DEADLINE,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout.strip() == "0", (
        "the worst case matched something, which means the boundary branch was not "
        "the one being exercised and the scan took the cheap path"
    )
