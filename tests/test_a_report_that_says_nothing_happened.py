"""Two ways a run that achieved nothing read as a run that went well.

Both are the same shape as the `answer_width` finding, and it is the shape this
repository keeps meeting: **the number a reader trusts, maximised by total
failure.**

```text
musubi plan — 0 emitted, 1 skipped, 0 removals, 100.0% traceable
  0 of 0 characters traceable (100.0%)
```

Nothing was converted. `Coverage.traceable_coverage` is 1.0 for an empty
artefact, and that is right per document — no character failed the guarantee —
but aggregated over a run that emitted nothing it is a percentage of nothing.

The second is quieter and worse. [ADR-0028] makes an installed extra
**offered, never claimed**, so that a dependency appearing in an environment
cannot change what a folder builds. The cost is that somebody installs
`musubi[pdf]` *because* their PDFs came back `no_pages`, runs it again, and gets
`no_pages` — with the converter that would read them sitting installed and
unmentioned.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from musubi import __version__
from musubi.application.pipeline import Settings, run
from musubi.domain.manifest import Manifest
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.converters.external import available
from musubi.infrastructure.emitters import DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import FilesystemSource
from musubi.interfaces.cli import main
from pdf_fixtures import classic, modern


def _settings() -> Settings:
    return Settings(
        ruleset=CORE,
        screener=default_screener(),
        converter_for=converter_for,
        musubi_version=__version__,
    )


def _plan(root: Path) -> Manifest:
    return run(
        FilesystemSource(root), _settings(), DocumentEmitter(root / "out"), write=False
    ).manifest


# -- a percentage of nothing ------------------------------------------------


def test_a_run_that_emitted_nothing_does_not_claim_full_coverage(tmp_path: Path) -> None:
    """The headline, which is the line most people read and no more."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "report.pdf").write_bytes(modern())

    summary = _plan(vault).summary()

    assert "0 emitted" in summary
    assert "100.0% traceable" not in summary, "a percentage of nothing was printed as success"
    assert "no characters to trace" in summary


def test_a_run_that_emitted_something_still_reports_its_coverage(tmp_path: Path) -> None:
    """The other half. A fix that stopped reporting coverage at all would be
    worse than the thing it fixed."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("# A note\n\nWith some prose in it.\n", encoding="utf-8")

    summary = _plan(vault).summary()

    assert "1 emitted" in summary
    assert "traceable" in summary
    assert "no characters to trace" not in summary


def test_the_coverage_block_says_so_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "report.pdf").write_bytes(modern())
    monkeypatch.chdir(tmp_path)

    assert main(["plan", str(vault), "--as", "filesystem"]) == 0
    printed = capsys.readouterr().out

    assert "0 of 0 characters traceable" not in printed
    assert "no characters were emitted" in printed


# -- the converter that was installed and never mentioned -------------------


@pytest.mark.skipif(not available(), reason="no optional converter is installed")
def test_a_refusal_names_the_installed_converter_that_could_read_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The trap ADR-0028 creates, and the line that defuses it.

    `pdf_text@1` scans for `N 0 obj` and cannot see a page inside a compressed
    object stream, which is what a PDF 1.5 is. `pdfium@1` reads it. Being
    installed is not enough — a settings file has to name it — so the refusal
    is the right place to say so.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "report.pdf").write_bytes(modern())
    monkeypatch.chdir(tmp_path)

    assert main(["plan", str(vault), "--as", "filesystem"]) == 0
    printed = capsys.readouterr().out

    assert "no_pages" in printed
    assert "Installed and not used" in printed
    assert "pdfium@1" in printed
    assert "[converters]" in printed, "it said one exists and not how to select it"


@pytest.mark.skipif(not available(), reason="no optional converter is installed")
def test_nothing_is_suggested_when_nothing_was_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A hint on every run is noise, and noise is how a real hint gets skipped."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "report.pdf").write_bytes(classic())
    monkeypatch.chdir(tmp_path)

    assert main(["plan", str(vault), "--as", "filesystem"]) == 0
    printed = capsys.readouterr().out

    assert "1 emitted" in printed or "1 documents would be written" in printed
    assert "Installed and not used" not in printed


def test_the_suggestion_is_not_a_default_change(tmp_path: Path) -> None:
    """[ADR-0028] is untouched: the installed converter is still not used.

    The whole safety property is that two machines with the same settings build
    the same folder whatever is in site-packages. A hint that quietly became a
    default would trade that away for convenience.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "report.pdf").write_bytes(modern())

    manifest = _plan(vault)
    assert manifest.coverage.emitted == 0, "the installed converter was used without being named"
    assert [skip.reason for skip in manifest.skipped] == ["no_pages"]
