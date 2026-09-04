"""Six defects the suite did not have a test for, and the tests it needed.

Every fix in this file passed 871 existing tests before it was written. That is
the finding: each of these is a **refusal that was already in the code** --
overlapping replacements are refused, a credential stops a run, an archive is
followed to a bounded depth, a corpus path is checked before it is written --
and in each case there was an input the refusal did not cover, with nothing
saying so.

They are collected in one file because they are one shape, not six subjects:

| | What was refused | What was not |
|---|---|---|
| 1 | overlapping replacements | an insertion **inside** one, which no `Span` overlaps |
| 2 | a prefix that looks like a credential | whether it *starts* anything ([ADR-0026]) |
| 3 | a PDF with no text layer | a stream that inflates past the memory there is |
| 4 | an archive nested too deep | a title holding the character the path is joined with |
| 5 | a path that leaves the staging area | two units claiming the same path |
| 6 | a manifest with the wrong layout | a right layout whose key leaves the corpus |
"""

from __future__ import annotations

import io
import zipfile
import zlib
from pathlib import Path

import pytest

from musubi import __version__
from musubi.application.pipeline import Settings, run
from musubi.domain.screening import Signature
from musubi.domain.span import Span
from musubi.domain.text import Replacement, rewrite
from musubi.errors import ContractError, SourceError
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.converters.pdf import MAXIMUM_STREAM_BYTES, PdfConverter
from musubi.infrastructure.corpus import Corpus
from musubi.infrastructure.emitters import DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.screeners.signatures import SIGNATURES
from musubi.infrastructure.sources.notion import MAXIMUM_ENTRY_BYTES, NotionSource

# -- 1. an insertion inside a replacement -----------------------------------


def test_an_insertion_inside_a_replacement_is_refused_by_the_refusal() -> None:
    """It was refused before this, by `_assert_tiles`, half a function later.

    The message read `the source tiling has a gap or an overlap at 10`, which is
    a sentence about musubi's own arithmetic. What actually happened is that two
    rules claimed the same characters, and ADR-0009 says which one wins is a
    decision somebody makes. A refusal that fires from the wrong place says the
    wrong thing.

    `Span.overlaps` cannot see this pair: an empty span overlaps nothing, and it
    has to, or every legal insertion would collide with the run it sits in.
    """
    with pytest.raises(ValueError, match="which one wins is a decision") as raised:
        rewrite(
            "abcdefghij",
            [
                Replacement(Span(0, 10), "X", "wide"),
                Replacement(Span(3, 3), "!", "narrow"),
            ],
        )
    assert "tiling" not in str(raised.value), "still being caught by the wrong check"


def test_a_non_adjacent_pair_is_refused_too() -> None:
    """The same fix, and the reason it is not a special case for empty spans.

    The old check compared **neighbours** after sorting. A wide replacement and
    a distant narrow one are not neighbours once anything sorts between them.
    """
    with pytest.raises(ValueError, match="which one wins is a decision"):
        rewrite(
            "abcdefghij",
            [
                Replacement(Span(0, 9), "X", "wide"),
                Replacement(Span(2, 3), "Y", "first"),
                Replacement(Span(5, 6), "Z", "second"),
            ],
        )


@pytest.mark.parametrize(
    ("label", "replacements"),
    [
        ("at the start", [Replacement(Span(2, 6), "X", "a"), Replacement(Span(2, 2), "!", "b")]),
        ("at the end", [Replacement(Span(2, 6), "X", "a"), Replacement(Span(6, 6), "!", "b")]),
        (
            "two at one point",
            [Replacement(Span(3, 3), "X", "a"), Replacement(Span(3, 3), "Y", "b")],
        ),
        ("adjacent", [Replacement(Span(0, 2), "X", "a"), Replacement(Span(2, 5), "Y", "b")]),
    ],
)
def test_the_insertions_that_are_legal_stay_legal(
    label: str, replacements: list[Replacement]
) -> None:
    """The other half. A refusal that also refuses correct input is not a fix.

    Front matter is an insertion at a boundary, and it is on every Markdown
    document musubi writes.
    """
    assert rewrite("abcdefghij", replacements).text, label


# -- 2. a prefix in the middle of a blob ------------------------------------


def _aws() -> Signature:
    return next(signature for signature in SIGNATURES if signature.id == "aws.access-key")


def test_a_prefix_inside_a_run_of_its_own_alphabet_is_not_a_credential() -> None:
    """[ADR-0026]. Measured at 3.33% of base64url documents before the fix.

    Under [ADR-0008] this is not a warning. The sync stops, nothing is written,
    and the message names a credential in a note whose author can see nothing
    wrong with it.
    """
    assert _aws().find("AKIAIOSFODNN7EXAMPLE"), "a real key must still be found"
    assert not _aws().find("DEADBEEFAKIAIOSFODNN7EXAMPLE"), (
        "the prefix here is inside a longer run of the same alphabet"
    )


def test_the_boundary_is_the_signatures_own_alphabet_not_a_word_break() -> None:
    """Why it is per-signature rather than one rule for all of them.

    An AWS key id is uppercase and digits. A lowercase `d` before the prefix is
    not a character that format allows, so the uppercase run really does start
    there and really is anomalous. `F` is, so it does not.
    """
    assert _aws().find("sha256:deadAKIAIOSFODNN7EXAMPLE")
    assert not _aws().find("sha256:DEADAKIAIOSFODNN7EXAMPLE")


@pytest.mark.parametrize(
    "text",
    [
        "AKIAIOSFODNN7EXAMPLE",
        "aws_access_key_id = AKIAIOSFODNN7EXAMPLE",
        '{"key": "AKIAIOSFODNN7EXAMPLE"}',
        "see https://example.test/AKIAIOSFODNN7EXAMPLE",
    ],
)
def test_a_credential_written_the_way_people_write_them_is_still_found(text: str) -> None:
    """The recall side. ADR-0026 trades a miss for a precision gain, and the
    miss it trades is a key with no separator in front of it -- not any of
    these, which is how they are actually written."""
    assert _aws().find(text), text


# -- 3. a stream that inflates past the memory there is ---------------------


def _one_page_pdf(stream: bytes, *, flate: bool) -> bytes:
    filter_entry = b"<< /Filter /FlateDecode >>" if flate else b"<< >>"
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Page /Contents 2 0 R >>\nendobj\n"
        b"2 0 obj\n" + filter_entry + b"\nstream\n" + stream + b"\nendstream\nendobj\n"
    )


def test_a_pdf_whose_stream_is_a_bomb_is_refused_rather_than_fatal() -> None:
    """`zlib.decompress` takes what the stream asks for.

    64 kB of compressed zeroes become 64 MB, and the ratio has no upper bound.
    The process dies, which is not fail-closed: [ADR-0008] promises a refusal,
    and a killed process leaves no manifest, no message, and the exit code of an
    interrupted run.
    """
    bomb = zlib.compress(b"\0" * (MAXIMUM_STREAM_BYTES + 4096), 9)
    assert len(bomb) < 100_000, "the fixture is meant to be small and the payload large"

    refused = PdfConverter().convert(_one_page_pdf(bomb, flate=True), "application/pdf")
    assert getattr(refused, "reason", None) == "stream_too_large"


def test_a_pdf_that_is_merely_large_still_converts() -> None:
    """The population check. A cap nothing can reach protects nothing, and a cap
    a real document reaches is a defect of its own."""
    page = b"BT (" + b"a word " * 2000 + b") Tj ET"
    converted = PdfConverter().convert(
        _one_page_pdf(zlib.compress(page), flate=True), "application/pdf"
    )
    assert getattr(converted, "text", "").strip().endswith("a word")


def test_the_notion_source_bounds_an_entry_too(tmp_path: Path) -> None:
    """The same hole in the other reader of untrusted archives.

    `ZipFile.read` sizes its buffer from a number written in the archive by
    whoever built it, so the bound is a bounded read rather than a check of
    `file_size`. Measured against the limit rather than at it: inflating 256 MB
    inside a test costs more than the assertion is worth, so what is asserted
    here is that the limit is small enough to be reachable by an attacker and
    large enough for any note, and the bounded read itself is exercised by every
    other Notion test in the suite.
    """
    assert 1_000_000 < MAXIMUM_ENTRY_BYTES < 2**31


# -- 4. a page whose title holds the character the path is joined with ------


def _export(root: Path, names: dict[str, str]) -> Path:
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as part:
        for name, body in names.items():
            part.writestr(name, body)
    outer = root / "8a1_ExportBlock-9f2.zip"
    with zipfile.ZipFile(outer, "w") as archive:
        archive.writestr("ExportBlock-9f2-Part-1.zip", inner.getvalue())
    return outer


def test_a_notion_page_called_done_can_be_read(tmp_path: Path) -> None:
    """`plan` listed it and `sync` could not open it, over a punctuation mark.

    The origin is `outer.zip!Part-1.zip!Title <id>.md`, and it used to be split
    on `!` to get back. A Notion title may contain any character a filename may,
    and `Done!` is a title people have.
    """
    _export(
        tmp_path,
        {
            "Done! 0123456789abcdef0123456789abcdef.md": "# done\n",
            "Plain 0123456789abcdef0123456789abcdee.md": "# plain\n",
        },
    )
    source = NotionSource(tmp_path)
    found = source.discover().found
    assert len(found) == 2
    assert {source.read(item) for item in found} == {b"# done\n", b"# plain\n"}


def test_a_title_that_is_nothing_but_separators_can_be_read(tmp_path: Path) -> None:
    """The general case, which is why the fix is not an escaping rule.

    The path is rebuilt by the same expression that built it and compared whole,
    so there is nothing to escape and nothing to get the escaping wrong.
    """
    _export(tmp_path, {"a!b!c 0123456789abcdef0123456789abcded.md": "# nasty\n"})
    source = NotionSource(tmp_path)
    (only,) = source.discover().found
    assert source.read(only) == b"# nasty\n"


# -- 5. two units claiming one artefact -------------------------------------


def test_two_units_with_the_same_key_stop_the_run(tmp_path: Path) -> None:
    """One document would overwrite the other and the manifest would list both.

    A corpus quietly smaller than its own account of itself, with every coverage
    number in it counting a file that is not there. Which of the two owns the
    key is not something musubi can decide; what it can say is that the source's
    `key_derivation` turned out not to be true of this export.
    """
    _export(
        tmp_path,
        {
            "First 0123456789abcdef0123456789abcdef.md": "# first\n",
            "Second 0123456789abcdef0123456789abcdef.md": "# second\n",
        },
    )
    source = NotionSource(tmp_path)
    assert len(source.discover().found) == 2, "both are discovered; the collision is downstream"

    settings = Settings(
        ruleset=CORE,
        screener=default_screener(),
        converter_for=converter_for,
        musubi_version=__version__,
    )
    with pytest.raises(SourceError, match="two different units"):
        run(source, settings, DocumentEmitter(tmp_path / "corpus"), write=False)


# -- 6. a manifest whose layout is right and whose key is not ---------------


@pytest.mark.parametrize(
    "path",
    [
        "documents/../../secrets.md",
        "documents//etc/passwd",
        "documents/",
    ],
)
def test_a_manifest_cannot_point_verify_outside_the_corpus(tmp_path: Path, path: str) -> None:
    """`key_of` checked the prefix, which says only where a path starts."""
    key = path[len("documents/") :]
    with pytest.raises(ContractError, match="does not stay under"):
        Corpus(tmp_path).key_of(path, f"traces/{key}.json")


def test_the_same_key_escapes_on_one_platform_and_does_not_on_another(tmp_path: Path) -> None:
    """`documents/C:/Windows/win.ini`, and why the check asks the filesystem.

    It holds no `..` and is not absolute by POSIX rules, so a string test would
    pass it everywhere. On Windows, joining it **discards everything to its
    left** and `verify` reads a file nobody synced. On Linux it is an ordinary
    relative directory called `C:`.

    Both are correct, and neither is a special case in the code: the question is
    put to `Path.resolve` and `relative_to`, which already know which platform
    they are on. This test is written the same way -- the *first* run of it
    asserted the Windows answer on every platform and went red on four CI
    machines, which is the same mistake one layer up.
    """
    corpus = Corpus(tmp_path)
    path = "documents/C:/Windows/win.ini"
    escapes = (Path("documents") / "C:/Windows/win.ini").is_absolute()

    if escapes:
        with pytest.raises(ContractError, match="does not stay under"):
            corpus.key_of(path, "traces/C:/Windows/win.ini.json")
    else:
        assert corpus.key_of(path, "traces/C:/Windows/win.ini.json") == "C:/Windows/win.ini"


def test_the_paths_musubi_writes_are_still_accepted(tmp_path: Path) -> None:
    """Including a nested one, which is what a folder of folders produces."""
    corpus = Corpus(tmp_path)
    assert corpus.key_of("documents/a.md", "traces/a.md.json") == "a.md"
    assert corpus.key_of("documents/x/y/b.md", "traces/x/y/b.md.json") == "x/y/b.md"
