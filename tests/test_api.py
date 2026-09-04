"""The three lines, and the promise they must not quietly drop.

A convenience API is where guarantees go to die: it is the surface people
actually use, it is the one nobody wrote an ADR for, and every simplification in
it is a place a policy can be missing. So these are mostly about **sameness** --
that `musubi.convert(p)` treats a file exactly as `musubi sync` would.

The one that matters most is the credential test. A helper that quietly returned
text holding an AWS key would be the single place in musubi where [ADR-0008]
did not apply, and it would be the place most people meet the library.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import musubi
from musubi.application.pipeline import Settings
from musubi.application.sync import sync as run_sync
from musubi.domain.trace import CHARACTERS, OPAQUE, Kind
from musubi.errors import ConversionError, CredentialFoundError
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.emitters import DOCUMENTS, DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import FilesystemSource
from pdf_fixtures import FIRST_LINE, classic

NOTE = "# ギア設計\n\nテントは 2.4kg。https://example.test/a?utm_source=newsletter\n"


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No `musubi.toml` from anywhere above, and no `MUSUBI_*` from the shell.

    `settings()` reads the configuration the same way the command line does, so
    a test that did not do this would be reading the developer's own.
    """
    monkeypatch.chdir(tmp_path)
    for name in list(dict(__import__("os").environ)):
        if name.startswith("MUSUBI_"):
            monkeypatch.delenv(name)


@pytest.fixture
def note(tmp_path: Path) -> Path:
    path = tmp_path / "gear.md"
    path.write_text(NOTE, encoding="utf-8")
    return path


# -- the three lines --------------------------------------------------------


def test_one_file_becomes_text_and_a_map(note: Path) -> None:
    converted = musubi.convert(note)

    assert converted.text.startswith("# ギア設計")
    assert converted.converter == "markdown@1"
    assert converted.media_type == "text/markdown"
    assert converted.coverage == 1.0


def test_the_map_answers_where_a_range_came_from(note: Path) -> None:
    """The thing no other converter of this shape can do, and the reason the
    API exists rather than a `to_markdown()` function."""
    converted = musubi.convert(note)
    at = converted.text.index("2.4kg")

    where = converted.where(at, at + 5)
    assert where.unit == CHARACTERS
    assert where.is_exact

    # Read back from the **file**, not from `NOTE`. `write_text` on Windows
    # writes CRLF, so the note on disk is two characters longer by this point
    # than the string this module holds -- and the offsets are into the file,
    # which is the whole point of them. Comparing against the in-memory string
    # was off by exactly the line count.
    source = note.read_bytes().decode("utf-8")
    assert source[where.span.start : where.span.end] == "2.4kg"


def test_bytes_can_be_supplied_for_a_file_that_is_not_on_a_disk() -> None:
    converted = musubi.convert("gear.md", content=NOTE.encode("utf-8"))
    assert converted.text.startswith("# ギア設計")
    assert converted.path is None, "it claimed a path for bytes that came from memory"


def test_a_suffix_musubi_does_not_read_says_what_it_does_read(tmp_path: Path) -> None:
    odd = tmp_path / "sheet.ods"
    odd.write_bytes(b"anything")

    with pytest.raises(ConversionError, match=r"\.md"):
        musubi.convert(odd)


def test_the_format_can_be_stated_when_the_suffix_does_not_say_it(tmp_path: Path) -> None:
    odd = tmp_path / "notes.bak"
    odd.write_text(NOTE, encoding="utf-8")

    assert musubi.convert(odd, media_type="text/markdown").text.startswith("# ")


# -- the same treatment as a sync -------------------------------------------


def test_the_text_is_what_a_sync_would_write_without_the_front_matter(
    note: Path, tmp_path: Path
) -> None:
    """Sameness, asserted against a real sync rather than against a fixture.

    Two implementations of one promise is the failure this guards: a helper that
    cleansed differently, or not at all, would hand people text a corpus would
    never contain.
    """
    into = tmp_path / "corpus"
    run_sync(
        FilesystemSource(tmp_path),
        Settings(
            ruleset=CORE,
            screener=default_screener(),
            converter_for=converter_for,
            musubi_version=musubi.__version__,
        ),
        DocumentEmitter(into),
    )
    written = (into / DOCUMENTS / "gear.md").read_text(encoding="utf-8")
    body = written[written.index("---\n", 4) + 4 :]

    assert musubi.convert(note).text == body


def test_the_tracking_parameter_is_removed_and_recorded(note: Path) -> None:
    """[ADR-0005]: a subtraction that is not recorded is invisible in the
    output, and the record carries the rule and never the value."""
    converted = musubi.convert(note)

    assert "utm_source" not in converted.text
    (removal,) = converted.removals
    assert removal.rule == "tracking.utm-family"
    assert "newsletter" not in str(removal), "the removal record quotes the value"


def test_a_credential_refuses_rather_than_returning_the_text(tmp_path: Path) -> None:
    """The one that matters most.

    [ADR-0008] stops a *run*; the equivalent for a value is refusing to be one.
    A helper that returned this text would be the single place in musubi where
    the policy did not apply, and it would be the place most people meet it.
    """
    leaky = tmp_path / "config.md"
    leaky.write_text("# setup\n\naws_access_key_id = AKIAIOSFODNN7EXAMPLE\n", encoding="utf-8")

    with pytest.raises(CredentialFoundError) as refused:
        musubi.convert(leaky)

    message = str(refused.value)
    assert "aws.access-key" in message
    assert "AKIAIOSFODNN7EXAMPLE" not in message, "the refusal quoted the secret"


def test_the_configuration_is_the_one_the_command_line_reads(tmp_path: Path) -> None:
    """[ADR-0027]. A folder set up for `musubi sync` is set up for this, and
    `musubi config` explains both -- rather than the API having settings of its
    own that nothing prints."""
    (tmp_path / "musubi.toml").write_text('rules = "none"\n', encoding="utf-8")
    (tmp_path / "gear.md").write_text(NOTE, encoding="utf-8")

    assert "utm_source" in musubi.convert(tmp_path / "gear.md").text, (
        "rules = none was set and the tracking parameter was removed anyway"
    )


# -- the locator, which is not always characters ----------------------------


def test_a_pdf_answers_in_pages_and_says_so(tmp_path: Path) -> None:
    """[ADR-0025]. `[2:3]` is one character or one page and the numbers look
    identical, so `unit` has to be read before any arithmetic."""
    document = tmp_path / "report.pdf"
    document.write_bytes(classic())

    converted = musubi.convert(document)
    assert FIRST_LINE in converted.text

    where = converted.where(0, len(FIRST_LINE))
    assert where.unit == OPAQUE
    assert not where.is_exact, "a PDF page cannot be verbatim; nothing was sliced out"
    assert "page 1" in str(where)


def test_a_range_outside_the_text_is_refused(note: Path) -> None:
    converted = musubi.convert(note)
    with pytest.raises(ValueError, match="outside the text"):
        converted.where(0, len(converted.text) + 1)


# -- the surface itself -----------------------------------------------------


def test_the_package_exports_what_the_readme_shows() -> None:
    """A README example that does not run is worse than no README.

    Checked as a set relation so that a name removed from `__all__` and left in
    the documentation turns this red.
    """
    for name in ("convert", "sync", "media_type_of", "Document", "Where"):
        assert name in musubi.__all__, f"README uses musubi.{name} and it is not exported"
        assert hasattr(musubi, name)


def test_the_package_docstring_example_is_the_current_signature() -> None:
    """The docstring is what `help(musubi)` prints and what PyPI shows."""
    assert "musubi.convert(" in (musubi.__doc__ or "")


def test_sync_builds_a_corpus_through_the_same_path(tmp_path: Path) -> None:
    """Thin on purpose: a second implementation of a sync is exactly what
    [ADR-0013]'s reasoning is about, one layer up."""
    (tmp_path / "gear.md").write_text(NOTE, encoding="utf-8")
    result = musubi.sync(tmp_path, into=tmp_path / "corpus")

    manifest = json.loads((tmp_path / "corpus" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "sync"
    assert len(manifest["artefacts"]) == 1
    assert getattr(result, "manifest", None) is not None


def test_a_document_prints_as_its_text(note: Path) -> None:
    """So that `print(musubi.convert(p))` does the obvious thing, which is what
    somebody comparing this to a one-line converter will type first."""
    converted = musubi.convert(note)
    assert str(converted) == converted.text


def test_the_kinds_a_range_passes_through_are_reported(note: Path) -> None:
    """Not only where, but what happened on the way -- the field that stops a
    caller reading a transformed run as an exact one."""
    converted = musubi.convert(note)
    where = converted.where(0, len(converted.text))

    assert Kind.VERBATIM in where.kinds
    assert not where.is_exact, "the cleansed URL is a transformed run in this range"

    # `url_query`, the *rewrite* kind, not `tracking.utm-family`, the rule id.
    # A trace map says which kind of transformation a run is; the record in
    # `removals` says which rule made it and carries the hash. Two vocabularies
    # on purpose, and this asserts the one a map actually speaks.
    #
    # Getting this to pass found a real gap. The cleansed query becomes a
    # **removal**, which occupies no output, and `Span.overlaps` is false for an
    # empty span -- so the first version of `where()` answered *where this range
    # came from* while silently omitting *what was taken out of it*.
    assert Kind.REMOVAL in where.kinds
    assert "url_query" in where.rules
    assert {removal.rule for removal in converted.removals} == {"tracking.utm-family"}
