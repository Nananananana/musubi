"""UTF-16 without a byte-order mark is valid UTF-8, and read as text it is mojibake.

Every ASCII character becomes itself followed by a NUL, so the UTF-8 decode
**succeeds**, the reading is reported as `utf-8`, and the corpus holds the
document interleaved with NUL characters.

Measured on one file, before it was refused:

```text
  with-bom.md    WRITTEN  coverage 43/87 (49%)  NULs=0   readable: True
  le-no-bom.md   WRITTEN  coverage 86/130 (66%)  NULs=43  readable: False
  utf8.md        WRITTEN  coverage 43/87 (49%)  NULs=0   readable: True
```

**The broken document scored better.** `traceable_coverage` was 66% against the
correctly-read file's 49%, because the mangling doubled the body and made
musubi's own front matter a smaller share of it. So the number a reader trusts
went *up* as the document became unreadable -- which is the family this
repository keeps finding, arriving through the success path.

`verify` held. Nothing anywhere said a thing.

## Why it is refused rather than read

`decode` already refuses a UTF-8 decoding that holds an escape character,
because ISO-2022-JP is seven-bit and decodes cleanly into its own escape
sequences ([ADR-0031]). This is the same failure from the other direction, and
it gets the same answer.

It does **not** get ISO-2022's recovery. That one re-reads the bytes by name
and checks the reading against them by round trip, which works because an
ISO-2022 file describes its own character set inline. UTF-16 describes nothing:
every even-length byte string decodes and re-encodes as UTF-16 unchanged, so a
round trip proves nothing and the only honest answer is to stop ([ADR-0054]).

`encoding = "detect"` reads these correctly, and the refusal in strict mode says
so through the machinery that was already there.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from musubi import __version__
from musubi.application.pipeline import Settings
from musubi.application.sync import sync
from musubi.domain.text import NUL, decode
from musubi.infrastructure.algorithms import chooser
from musubi.infrastructure.decoding import detector
from musubi.infrastructure.emitters import DOCUMENTS, DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import FilesystemSource

TEXT = "# The gear list\n\nA tent that weighs 2.4kg.\n"

available = pytest.mark.skipif(detector() is None, reason="charset-normalizer is not installed")


def settings(*, detect: bool = False) -> Settings:
    return Settings(CORE, default_screener(), chooser({}, detect=detect), __version__)


# -- the decoding itself -----------------------------------------------------


@pytest.mark.parametrize("codec", ["utf-16-le", "utf-16-be"], ids=lambda c: c)
def test_utf16_without_a_mark_is_refused_rather_than_read_as_nulls(codec: str) -> None:
    """It decodes without an error, which is the whole problem."""
    raw = TEXT.encode(codec)
    assert raw.decode("utf-8"), "the premise: this is valid UTF-8"
    assert NUL in raw.decode("utf-8")

    with pytest.raises(ValueError, match="contains a NUL"):
        decode(raw)


def test_the_refusal_says_what_the_file_probably_is() -> None:
    """A refusal that names no cause is a file its owner has to guess about."""
    with pytest.raises(ValueError) as raised:
        decode(TEXT.encode("utf-16-le"))
    said = str(raised.value)
    assert "byte-order mark" in said
    assert "one NUL per ASCII character" in said


@pytest.mark.parametrize(
    "codec", ["utf-8", "utf-16", "utf-16-le-with-mark", "utf-16-be-with-mark"], ids=lambda c: c
)
def test_a_file_that_says_what_it_is_still_reads(codec: str) -> None:
    """The other half, and the one that matters more: this must not refuse the
    encodings musubi has always accepted."""
    import codecs as std

    raw = {
        "utf-8": TEXT.encode("utf-8"),
        "utf-16": TEXT.encode("utf-16"),
        "utf-16-le-with-mark": std.BOM_UTF16_LE + TEXT.encode("utf-16-le"),
        "utf-16-be-with-mark": std.BOM_UTF16_BE + TEXT.encode("utf-16-be"),
    }[codec]
    assert decode(raw).text == TEXT


def test_a_utf8_document_with_no_nul_is_untouched() -> None:
    """Including the control characters that are not NUL. Only the one that is
    evidence of a mis-encoding is refused."""
    for body in ("plain\n", "bell\x07\n", "vtab\x0b\n", "formfeed\x0c\n", "設計メモ\n"):
        assert decode(body.encode("utf-8")).text == body


# -- and what a sync does with one -------------------------------------------


def test_a_corpus_does_not_quietly_hold_the_mojibake(tmp_path: Path) -> None:
    """End to end, which is where it was found. It used to be written, verify
    used to hold, and the coverage used to look better than the real file's."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "le.md").write_bytes(TEXT.encode("utf-16-le"))
    (vault / "good.md").write_text(TEXT, encoding="utf-8")
    into = tmp_path / "corpus"

    result = sync(FilesystemSource(vault), settings(), DocumentEmitter(into))

    (skip,) = result.manifest.skipped
    assert skip.origin == "le.md"
    assert skip.reason == "undecodable"
    assert not (into / DOCUMENTS / "le.md").exists()

    (kept,) = result.manifest.artefacts
    assert kept.unit_key == "good.md", "the readable file still arrives"


@available
def test_detection_reads_it_correctly_when_it_is_asked_to(tmp_path: Path) -> None:
    """The refusal is the strict answer, not the only one. `encoding =
    "detect"` recovers the text, and the corpus records that it guessed."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "le.md").write_bytes(TEXT.encode("utf-16-le"))
    into = tmp_path / "corpus"

    result = sync(FilesystemSource(vault), settings(detect=True), DocumentEmitter(into))

    (artefact,) = result.manifest.artefacts
    assert artefact.encoding.replace("_", "-") == "utf-16-le"
    assert artefact.encoding_detected, "a guess, recorded as one"
    body = (into / DOCUMENTS / "le.md").read_text(encoding="utf-8")
    assert NUL not in body
    assert "2.4kg" in body


def test_the_number_that_made_this_invisible(tmp_path: Path) -> None:
    """Kept because it is the reason nothing caught this for so long.

    Coverage is output characters that resolve, over output characters. The
    mangled reading has twice the body, so musubi's own front matter -- which
    is synthetic and counts *against* coverage -- is a smaller share of it, and
    the broken document scores higher than the correct one.
    """
    root = Path(tempfile.mkdtemp())
    try:
        vault = root / "vault"
        vault.mkdir()
        (vault / "good.md").write_text(TEXT, encoding="utf-8")
        result = sync(FilesystemSource(vault), settings(), DocumentEmitter(root / "corpus"))
        (good,) = result.manifest.artefacts
        # The mangled document would have had ~2x the characters and the same
        # fixed synthetic block, so a higher ratio. This pins the correct one so
        # that the comparison in the docstring stays checkable.
        assert good.traceable_coverage < 0.6, (
            "the correctly-read file's coverage, which the mojibake beat at 66%"
        )
    finally:
        import shutil

        shutil.rmtree(root, ignore_errors=True)
