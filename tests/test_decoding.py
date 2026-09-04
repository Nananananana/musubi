"""Reading a vault that is not UTF-8, and saying what had to be assumed.

The refusal these relax was right about the danger and wrong about the shape:
a guess that is **invisible** writes plausible nonsense into a corpus, and the
implementation answered that by refusing rather than by making the guess
visible. [ADR-0031].

So the tests are about visibility rather than about correctness. Detection is
measured in `tools/encoding_detection.py` and it is **not perfect** — 17 of 19
at paragraph length, and every miss reported 100% coherence. What has to hold
here is that a corpus built with it says so.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from musubi import __version__
from musubi.application.pipeline import Settings
from musubi.application.sync import sync
from musubi.infrastructure.algorithms import chooser
from musubi.infrastructure.converters import known_converters
from musubi.infrastructure.corpus import Corpus
from musubi.infrastructure.decoding import CONFIDENT, DECODES, Decoding, detector, read
from musubi.infrastructure.emitters import DOCUMENTS, DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import FilesystemSource
from musubi.ports.converter import Converted

NOTE = "# 設計メモ\n\nテントは 2.4kg。ブーツのほうが効く。山では軽さがすべて。\n"

available = pytest.mark.skipif(detector() is None, reason="charset-normalizer is not installed")


def settings(*, detect: bool) -> Settings:
    return Settings(
        ruleset=CORE,
        screener=default_screener(),
        converter_for=chooser({}, detect=detect),
        musubi_version=__version__,
    )


# -- the domain is unchanged ------------------------------------------------


def test_the_domain_still_refuses_and_the_relaxation_is_infrastructures() -> None:
    """[ADR-0001] holds: the layer whose job is to be checkable did not acquire
    a guess. cp932 does not announce itself, so the domain has nothing to check
    a reading against and still says so.

    That the domain imports nothing outside the standard library is asserted by
    `tests/test_architecture.py`, which parses the imports. The first version of
    this test grepped the file for `charset` and went red when the docstring
    started **explaining why there is no detector** -- a check on the words
    rather than on the imports, and the second time in this repository that a
    canary turned out to be vocabulary.
    """
    from musubi.domain.text import decode

    with pytest.raises(ValueError, match="does not guess"):
        decode(NOTE.encode("cp932"))


# -- strict, which is the default -------------------------------------------


@available
def test_strict_still_refuses_and_now_says_what_the_file_is() -> None:
    """A refusal that cannot be acted on is most of why refusing was the wrong
    shape. This is the sentence that changes it from a dead end into a setting.
    """
    with pytest.raises(ValueError) as refused:
        read(NOTE.encode("cp932"), detect=False)

    message = str(refused.value)
    assert "cp932" in message
    assert 'encoding = "detect"' in message, "the refusal does not say what to do about it"


def test_utf8_is_read_the_same_way_in_both_modes() -> None:
    """Nothing about the ordinary path moves. The detector is not consulted for
    a file that decodes, in either mode."""
    for detect in (False, True):
        decoded, detection = read(NOTE.encode("utf-8"), detect=detect)
        assert decoded.text == NOTE
        assert decoded.encoding == "utf-8"
        assert detection is None, "a file that decodes was handed to a detector anyway"


# -- detect -----------------------------------------------------------------


@available
@pytest.mark.parametrize("encoding", ["cp932", "euc-jp"])
def test_a_japanese_note_is_read_and_the_encoding_comes_back(encoding: str) -> None:
    """The case the refusal made unusable, and the one detection is good at."""
    decoded, detection = read((NOTE * 4).encode(encoding), detect=True)

    assert decoded.text == NOTE * 4, "the text did not survive"
    assert detection is not None
    assert detection.confidence > CONFIDENT


# -- the bug found on the way, which needed no detector at all --------------


@pytest.mark.parametrize("paragraphs", [1, 4, 20])
def test_a_stateful_encoding_is_read_in_strict_mode_and_at_any_length(
    paragraphs: int,
) -> None:
    """ISO-2022-JP is **seven-bit**, so it decoded as UTF-8 without an error and
    came back as its own escape sequences, reported as `utf-8`, exit zero. That
    is the failure `decode` says it exists to prevent, arriving through the
    *success* path.

    It is read in `strict` mode, with no extra installed, because an ISO-2022
    file **declares its character set inline** and the reading is checked by a
    round trip. Self-describing is what separates it from cp932.

    Parametrised by length on purpose: `charset-normalizer` answers `iso2022_jp`
    for one paragraph of this document and `utf_8` for four. A reading that
    changes with the size of the file is not a reading, which is why this does
    not use one.
    """
    from musubi.domain.text import decode

    decoded = decode((NOTE * paragraphs).encode("iso-2022-jp"))
    assert decoded.text == NOTE * paragraphs
    assert decoded.encoding == "iso2022_jp"


def test_terminal_output_is_refused_rather_than_ingested() -> None:
    """The other half of the escape rule, and its cost.

    A captured terminal session is not prose, and a corpus holding colour
    codes is a corpus a model will read them out of. Refusing it is
    deliberate, and it is a real loss for anybody whose notes are session
    logs.
    """
    from musubi.domain.text import ESCAPE, decode

    log = f"a log line {ESCAPE}[31mred{ESCAPE}[0m and more text after it"
    with pytest.raises(ValueError, match="not text"):
        decode(log.encode("utf-8"))


@available
def test_a_reading_nothing_recognises_is_still_refused() -> None:
    """`detect` is not `guess`. Below the threshold the original rule applies,
    because a detector that recognised nothing is not an answer."""
    noise = bytes(range(128, 256)) * 40
    found = detector()
    assert found is not None
    detection = found(noise)
    if detection is not None and detection.worth_acting_on:
        pytest.skip(f"this noise reads coherently as {detection.encoding}; pick another")

    with pytest.raises(ValueError):
        read(noise, detect=True)


# -- the wrapper ------------------------------------------------------------


def test_every_registered_converter_falls_on_one_side_of_the_decoding_line() -> None:
    """A set relation, not a loop.

    `Decoding` is applied by media type, so a format nobody classified would be
    silently on the wrong side: a PDF transcoded is a PDF destroyed, and a text
    format missed keeps the refusal the setting was meant to lift.
    """
    claimed = {media for converter in known_converters() for media in converter.media_types}
    assert claimed, "no converters; this guard would run zero times"

    unclassified = {media for media in claimed if media not in DECODES}
    assert unclassified == {"application/pdf"}, (
        f"{sorted(unclassified)} is claimed by a converter and is not in DECODES. "
        f"Every media type has to be a deliberate yes or a deliberate no."
    )


@available
def test_a_pdf_is_never_transcoded() -> None:
    """The failure this would have: bytes are not text, and re-encoding them as
    UTF-8 destroys the file while looking like a decoding."""
    from pdf_fixtures import FIRST_LINE, classic

    inner = next(c for c in known_converters() if c.name == "pdf_text@1")
    wrapped = Decoding(inner, detect=True)
    result = wrapped.convert(classic(), "application/pdf")

    assert isinstance(result, Converted), getattr(result, "reason", result)
    assert FIRST_LINE in result.text


# -- what the corpus says afterwards ----------------------------------------


@available
def test_a_shift_jis_vault_becomes_a_corpus_that_names_the_encoding(tmp_path: Path) -> None:
    """The whole feature, end to end, and the part that makes it defensible.

    The document is correct Japanese and the **trace map says `cp932`** — so a
    reader knows musubi assumed something, and `text[:n].encode("cp932")` is
    still a byte offset in the file the owner has ([ADR-0018]).
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "old.md").write_bytes((NOTE * 4).encode("cp932"))
    into = tmp_path / "corpus"

    sync(FilesystemSource(vault), settings(detect=True), DocumentEmitter(into))

    document = (into / DOCUMENTS / "old.md").read_text(encoding="utf-8")
    assert "テントは 2.4kg。" in document

    held = Corpus(into).held("old.md")
    assert held.source.encoding == "cp932", "the corpus does not say what was assumed"
    assert held.source.encoding != "utf-8"


@available
def test_the_same_vault_is_skipped_with_a_reason_when_strict(tmp_path: Path) -> None:
    """And the skip is the actionable one, not `undecodable` alone."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "old.md").write_bytes((NOTE * 4).encode("cp932"))

    result = sync(FilesystemSource(vault), settings(detect=False), DocumentEmitter(tmp_path / "c"))

    (skip,) = result.manifest.skipped
    assert skip.reason == "undecodable"
    assert "cp932" in skip.detail
    assert 'encoding = "detect"' in skip.detail


@available
def test_the_offsets_still_convert_to_bytes_in_the_original_file(tmp_path: Path) -> None:
    """The claim [ADR-0018] makes, over a file that was not UTF-8 to begin with.

    This is the one that would break silently if transcoding were done
    carelessly: the map counts characters of the decoded text, and the recorded
    encoding is what turns a character offset into a byte offset **in the file
    on disk**, not in musubi's re-encoding of it.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    raw = (NOTE * 4).encode("cp932")
    (vault / "old.md").write_bytes(raw)
    into = tmp_path / "corpus"

    sync(FilesystemSource(vault), settings(detect=True), DocumentEmitter(into))
    held = Corpus(into).held("old.md")

    source_text = raw.decode(held.source.encoding)
    at = source_text.index("2.4kg")
    byte_at = len(source_text[:at].encode(held.source.encoding))

    assert raw[byte_at : byte_at + 5] == b"2.4kg"
