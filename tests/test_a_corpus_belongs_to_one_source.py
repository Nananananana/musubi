"""Syncing a second source into a corpus deleted the first one's documents.

Measured, before it was fixed:

```text
  after syncing A: ['from-a.md']
  after syncing B: ['from-b.md']
  withdrawn by B's run: ('documents/from-a.md', 'traces/from-a.md.json')
```

**Exit 0.** Nothing said anything, and `musubi verify` passed afterwards,
because the corpus really was consistent with the manifest that had just
replaced it.

It follows from the design rather than from a bug in it. The manifest is an
account of **one run** ([ADR-0002]), and withdrawal takes out whatever the
previous manifest recorded that this one does not ([ADR-0021]). A second source
pointed at the same folder therefore does not add to a corpus; it replaces one.

That is a reasonable design and it was **written down nowhere**, so the first
person to type the wrong `--into` finds it out by losing a corpus.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from musubi import __version__
from musubi.application.pipeline import Settings
from musubi.application.sync import sync, wrong_source
from musubi.errors import DONE, REFUSED, DifferentSourceError
from musubi.infrastructure.algorithms import chooser
from musubi.infrastructure.emitters import DOCUMENTS, DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import FilesystemSource, ObsidianSource
from musubi.interfaces.cli import main

NOTE = "# A note\n\nSome prose that a person wrote.\n"


def settings() -> Settings:
    return Settings(CORE, default_screener(), chooser({}), __version__)


def vault(root: Path, name: str) -> Path:
    root.mkdir(parents=True)
    (root / name).write_text(NOTE, encoding="utf-8")
    return root


def documents(into: Path) -> list[str]:
    return sorted(path.name for path in (into / DOCUMENTS).rglob("*.md"))


# -- the refusal -------------------------------------------------------------


def test_a_second_source_does_not_quietly_replace_the_first(tmp_path: Path) -> None:
    """The measured defect. A vault, then a folder, into one destination."""
    first = vault(tmp_path / "vault", "from-a.md")
    second = vault(tmp_path / "feed", "from-b.md")
    into = tmp_path / "corpus"

    sync(ObsidianSource(first), settings(), DocumentEmitter(into))
    assert documents(into) == ["from-a.md"]

    with pytest.raises(DifferentSourceError, match="belongs to one source"):
        sync(FilesystemSource(second), settings(), DocumentEmitter(into))

    assert documents(into) == ["from-a.md"], "a refusal wrote nothing and deleted nothing"


def test_the_refusal_says_how_much_would_have_gone(tmp_path: Path) -> None:
    """A refusal that does not say what it saved is one an operator overrides
    without knowing what they are agreeing to."""
    first = tmp_path / "vault"
    first.mkdir()
    for number in range(3):
        (first / f"note-{number}.md").write_text(NOTE, encoding="utf-8")
    second = vault(tmp_path / "feed", "other.md")
    into = tmp_path / "corpus"

    sync(ObsidianSource(first), settings(), DocumentEmitter(into))
    with pytest.raises(DifferentSourceError, match=r"6 file\(s\)"):
        sync(FilesystemSource(second), settings(), DocumentEmitter(into))


def test_withdraw_all_is_the_operator_saying_they_have_looked(tmp_path: Path) -> None:
    """The same gesture the other two refusals take. Replacing a corpus is a
    real thing to want; doing it without noticing is not."""
    first = vault(tmp_path / "vault", "from-a.md")
    second = vault(tmp_path / "feed", "from-b.md")
    into = tmp_path / "corpus"

    sync(ObsidianSource(first), settings(), DocumentEmitter(into))
    sync(FilesystemSource(second), settings(), DocumentEmitter(into), withdraw_all=True)

    assert documents(into) == ["from-b.md"]


# -- and what must keep working ---------------------------------------------


def test_the_same_source_syncing_again_is_untouched(tmp_path: Path) -> None:
    """The ordinary case, which is every run. A guard that fired here would
    stop musubi doing the thing it is for."""
    root = vault(tmp_path / "vault", "note.md")
    into = tmp_path / "corpus"

    sync(ObsidianSource(root), settings(), DocumentEmitter(into))
    (root / "second.md").write_text(NOTE, encoding="utf-8")
    again = sync(ObsidianSource(root), settings(), DocumentEmitter(into))

    assert documents(into) == ["note.md", "second.md"]
    assert again.withdrawn == ()


def test_a_first_run_into_an_empty_destination_is_not_a_different_source(
    tmp_path: Path,
) -> None:
    """Nothing wrote it, so nobody owns it."""
    root = vault(tmp_path / "vault", "note.md")
    assert sync(ObsidianSource(root), settings(), DocumentEmitter(tmp_path / "corpus")).promoted


def test_the_rule_itself(tmp_path: Path) -> None:
    """The predicate on its own, because the interesting cases are the empty
    one and the equal one and both are easy to get wrong."""
    assert not wrong_source(frozenset(), "vault"), "a destination nothing has written"
    assert not wrong_source(frozenset({"vault"}), "vault"), "the same source again"
    assert wrong_source(frozenset({"vault"}), "filesystem")
    assert wrong_source(frozenset({"vault", "fetched"}), "vault"), (
        "a corpus with two sources in it cannot arise once this refuses, and is "
        "still not a corpus this run accounts for"
    )


# -- through the command line, where the exit code is the answer ------------


def test_the_command_refuses_and_a_plan_predicts_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plan predicts the code a sync would exit with. It named two of the
    three refusals the day a third arrived, which is what a hand-written list
    of cases always does."""
    monkeypatch.chdir(tmp_path)
    first = vault(tmp_path / "vault", "from-a.md")
    second = vault(tmp_path / "feed", "from-b.md")
    into = tmp_path / "corpus"

    assert main(["sync", str(first), "--into", str(into)]) == DONE
    assert main(["plan", str(second), "--into", str(into), "--as", "filesystem"]) == REFUSED
    assert main(["sync", str(second), "--into", str(into), "--as", "filesystem"]) == REFUSED
    assert documents(into) == ["from-a.md"]


def test_the_refusal_names_its_kind_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """So that a program folding failures by name can tell this from the other
    two refusals, which is the whole of [ADR-0046]."""
    monkeypatch.chdir(tmp_path)
    first = vault(tmp_path / "vault", "from-a.md")
    second = vault(tmp_path / "feed", "from-b.md")
    into = tmp_path / "corpus"

    main(["sync", str(first), "--into", str(into)])
    capsys.readouterr()
    assert main(["sync", str(second), "--into", str(into), "--as", "filesystem"]) == REFUSED
    assert capsys.readouterr().err.splitlines()[0].startswith("DifferentSourceError: ")
