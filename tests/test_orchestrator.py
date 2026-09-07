"""What a program driving musubi needs to be able to tell, without reading prose.

Written against the requirements the `sora` orchestrator sent
(`musubi-work/01_sora_requirements.md`): it retries a failure and must not
retry a refusal; it draws *musubi wrote this* and *did not resolve* as two
different things; it keeps a card up to date from the runs since the last one
it drew; and it hands `musubi_trace` an anchor a consumer made into a corpus
document, front matter included.

Every one of these is a distinction a person reading the report already had
and a program did not. None of them is a new capability; all of them are a
word where there was a sentence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from musubi import __version__
from musubi.application.pipeline import Settings
from musubi.application.sync import sync
from musubi.application.trace import STATUSES, as_document, resolve
from musubi.domain.span import Span
from musubi.errors import DONE, FAILED, REFUSED, USAGE
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.corpus import Corpus
from musubi.infrastructure.emitters import DOCUMENTS, DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import ObsidianSource
from musubi.interfaces.cli import main
from musubi.interfaces.mcp import serve

NOTE = "# テント設計メモ\n\nテントは 2.4kg。\n"
AWS = "AKIAIOSFODNN7EXAMPLE"


def built(root: Path, into: Path, files: dict[str, str] | None = None) -> None:
    for name, body in (files or {"design/gear.md": NOTE}).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    sync(
        ObsidianSource(root),
        Settings(CORE, default_screener(), converter_for, __version__),
        DocumentEmitter(into),
    )


def mcp(root: Path, tool: str, **arguments: object) -> dict[str, object]:
    import io

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    written = io.StringIO()
    serve(root, stream=io.StringIO(json.dumps(request) + "\n"), out=written)
    answer = json.loads(written.getvalue().splitlines()[0])
    result: dict[str, object] = answer["result"]
    return result


def text_of(result: dict[str, object]) -> dict[str, object]:
    content = result["content"]
    assert isinstance(content, list)
    body: dict[str, object] = json.loads(content[0]["text"])
    return body


# -- exit codes --------------------------------------------------------------


def test_the_four_codes_are_distinct_and_documented() -> None:
    """The table in `docs/using-a-corpus.md` is what an orchestrator reads, so
    the numbers there are the numbers here, checked rather than copied."""
    assert len({DONE, FAILED, USAGE, REFUSED}) == 4
    doc = (Path(__file__).resolve().parent.parent / "docs" / "using-a-corpus.md").read_text(
        encoding="utf-8"
    )
    for code, name in ((DONE, "done"), (FAILED, "failed"), (USAGE, "usage"), (REFUSED, "refused")):
        assert f"| `{code}` | {name} |" in doc, f"docs do not state that {code} means {name}"


def test_a_refusal_is_not_a_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The distinction the orchestrator asked for. It retries a failure -- a
    corpus somebody broke -- and must not retry a refusal, which a person has
    to look at. Same code for both and it would retry a credential forever."""
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "vault"
    root.mkdir()
    (root / "setup.md").write_text(f"key: {AWS}\n", encoding="utf-8")
    into = tmp_path / "corpus"

    assert main(["sync", str(root), "--into", str(into)]) == REFUSED
    assert not (into / DOCUMENTS).exists()

    # And a corpus that is broken, not refused. (The folder exists: a refused
    # run made its staging area under it and discarded the staging area.)
    into.mkdir(exist_ok=True)
    (into / "manifest.json").write_text("{not json", encoding="utf-8")
    assert main(["verify", str(into)]) == FAILED


def test_an_emptied_source_is_a_refusal_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0021's stop: nothing was written and a person decides. The same
    word as a credential, because the orchestrator's move is the same."""
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "vault"
    into = tmp_path / "corpus"
    built(root, into)
    (root / "design" / "gear.md").unlink()

    assert main(["sync", str(root), "--into", str(into)]) == REFUSED
    assert main(["sync", str(root), "--into", str(into), "--withdraw-all"]) == DONE


def test_a_run_that_converted_nothing_is_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The question `sora` asked musubi to answer: is a run that skipped
    everything a success?

    It is not. The owner pointed musubi at a folder, musubi read every file in
    it and wrote none of them, and the only thing that said so was a count of
    skips in a report no program reads. Exiting 0 there is the same shape as
    `0 of 0 characters traceable (100.0%)` at the one place every caller looks
    ([ADR-0046]).

    A skip list is not this. Some files failing is reported and is normal;
    **not one file succeeding** is the count at which "musubi read your folder"
    and "musubi read nothing of it" cannot be told apart from outside.
    """
    monkeypatch.chdir(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    # Read as a unit, converted by nothing: a text file musubi cannot decode.
    (vault / "notes.md").write_bytes("テントは 2.4kg。".encode("cp932"))
    into = tmp_path / "corpus"

    assert main(["sync", str(vault), "--into", str(into), "--as", "filesystem"]) == REFUSED
    assert not (into / DOCUMENTS).exists(), "a refusal writes nothing"
    assert (
        main(["sync", str(vault), "--into", str(into), "--as", "filesystem", "--withdraw-all"])
        == DONE
    )


def test_some_files_failing_is_still_a_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other side, and what stops the refusal above from being a nuisance.

    A vault of notes beside a folder of images is the ordinary case, and every
    image is a skip. One emitted document proves the run did something, which
    is the whole distinction.
    """
    monkeypatch.chdir(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "good.md").write_text(NOTE, encoding="utf-8")
    (vault / "bad.md").write_bytes("テントは 2.4kg。".encode("cp932"))

    assert main(["sync", str(vault), "--into", str(tmp_path / "c"), "--as", "filesystem"]) == DONE


def test_the_error_catalogue_is_the_names_an_orchestrator_will_see(
    capsysbinary: pytest.CaptureFixture[bytes],
) -> None:
    """`sora` folds incidents by the word before the first colon on stderr and
    keeps nothing else from the line. That makes the set of words an interface,
    and `musubi errors --json` is where it is written down rather than
    discovered by being surprised."""
    assert main(["errors", "--json"]) == DONE
    body = json.loads(capsysbinary.readouterr().out.decode("utf-8"))

    names = {one["kind"] for one in body["errors"]}
    assert {"CredentialFoundError", "EverythingSkippedError", "Usage", "Unexpected"} <= names
    # The two an orchestrator branches on, stated rather than inferred.
    refusals = {one["kind"] for one in body["errors"] if one["exit_code"] == REFUSED}
    assert all(one["outcome"] == "refused" for one in body["errors"] if one["kind"] in refusals)
    assert not any(one["retryable"] for one in body["errors"] if one["kind"] in refusals), (
        "a refusal that says retrying may help is the one mistake this table exists to stop"
    )


def test_a_plan_predicts_the_code_a_sync_would_exit_with(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "vault"
    root.mkdir()
    (root / "setup.md").write_text(f"key: {AWS}\n", encoding="utf-8")
    assert main(["plan", str(root)]) == REFUSED


def test_no_command_is_a_usage_error() -> None:
    assert main([]) == USAGE


# -- one word for what kind of answer a trace is ---------------------------


def test_every_status_is_one_of_the_published_five(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    into = tmp_path / "corpus"
    built(root, into)
    corpus = Corpus(into)
    text = corpus.artefact("design/gear.md")
    at = text.index("2.4kg")

    resolved = resolve(corpus, "design/gear.md", Span(at, at + 5))
    assert resolved.status == "resolved"
    assert resolved.status in STATUSES

    synthetic = resolve(corpus, "design/gear.md", Span(0, 3))
    assert synthetic.status == "synthetic"

    (root / "design" / "gear.md").write_text("something else\n", encoding="utf-8")
    assert resolve(corpus, "design/gear.md", Span(at, at + 5)).status == "source_changed"

    (root / "design" / "gear.md").unlink()
    assert resolve(corpus, "design/gear.md", Span(at, at + 5)).status == "source_missing"


def test_a_source_outside_the_confinement_is_located_and_not_opened(tmp_path: Path) -> None:
    """The manifest names the source as an absolute path, and following it is
    the point of a trace. A caller confined to a folder must not be walked out
    of it by a manifest somebody else wrote -- so the answer says where the
    file is not, and carries no bytes and no excerpt from it."""
    root = tmp_path / "vault"
    into = tmp_path / "elsewhere" / "corpus"
    built(root, into)
    corpus = Corpus(into)
    text = corpus.artefact("design/gear.md")
    at = text.index("2.4kg")

    found = resolve(corpus, "design/gear.md", Span(at, at + 5), within=tmp_path / "elsewhere")
    assert found.status == "source_outside_root"
    assert found.source_path is None
    assert found.source_bytes is None
    assert found.source_excerpt is None
    assert found.source_span.length == 5, "the character range is still the answer"

    inside = resolve(corpus, "design/gear.md", Span(at, at + 5), within=tmp_path)
    assert inside.status == "resolved"


def test_the_command_and_the_document_carry_the_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "vault"
    into = tmp_path / "corpus"
    built(root, into)
    text = (into / DOCUMENTS / "design" / "gear.md").read_text(encoding="utf-8")
    at = text.index("2.4kg")

    assert main(["trace", f"{into / DOCUMENTS / 'design' / 'gear.md'}:{at}-{at + 5}"]) == DONE
    assert "[resolved]" in capsys.readouterr().out

    assert (
        main(["trace", f"{into / DOCUMENTS / 'design' / 'gear.md'}:{at}-{at + 5}", "--json"]) == 0
    )
    body = json.loads(capsys.readouterr().out)
    assert body["status"] == "resolved"
    assert body["source"]["unit"] == "characters"


# -- musubi_trace, from a corpus document ------------------------------------


def test_mcp_trace_answers_a_corpus_document_from_its_map(tmp_path: Path) -> None:
    """The anchor an orchestrator holds points into the document as it sits in
    the corpus, front matter included. Converting the source afresh would
    answer about a different text, off by the length of that front matter --
    which is exactly the confident wrong answer this library exists to
    prevent."""
    root = tmp_path / "vault"
    into = tmp_path / "corpus"
    built(root, into)
    document = into / DOCUMENTS / "design" / "gear.md"
    text = document.read_text(encoding="utf-8")
    at = text.index("2.4kg")
    assert at > 20, "the fixture should have front matter in front of the needle"

    answer = text_of(mcp(tmp_path, "musubi_trace", path=str(document), start=at, end=at + 5))
    assert answer["status"] == "resolved"
    assert answer["excerpt"] == "2.4kg"
    source = answer["source"]
    assert isinstance(source, dict)
    assert source["excerpt"] == "2.4kg"
    assert source["bytes"] is not None
    assert Path(str(source["path"])).name == "gear.md"

    matter = text_of(mcp(tmp_path, "musubi_trace", path=str(document), start=0, end=3))
    assert matter["status"] == "synthetic"


def test_mcp_trace_does_not_open_a_source_outside_its_root(tmp_path: Path) -> None:
    """Rooted at the corpus alone, the server can say where the source is
    supposed to be and nothing about what is in it."""
    root = tmp_path / "vault"
    into = tmp_path / "corpus"
    built(root, into)
    document = into / DOCUMENTS / "design" / "gear.md"
    at = document.read_text(encoding="utf-8").index("2.4kg")

    answer = text_of(mcp(into, "musubi_trace", path=str(document), start=at, end=at + 5))
    assert answer["status"] == "source_outside_root"
    source = answer["source"]
    assert isinstance(source, dict)
    assert source["bytes"] is None and source["excerpt"] is None and source["path"] is None


def test_mcp_trace_on_a_plain_file_still_converts_and_says_so(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "gear.md").write_text(NOTE, encoding="utf-8")
    at = NOTE.index("2.4kg")
    answer = text_of(
        mcp(tmp_path, "musubi_trace", path=str(root / "gear.md"), start=at, end=at + 5)
    )
    assert answer["status"] == "resolved"
    assert answer["excerpt"] == "2.4kg"


# -- the runs since the last one a card drew ------------------------------------


def test_log_since_gives_the_runs_after_the_one_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "vault"
    into = tmp_path / "corpus"
    built(root, into)
    (root / "stove.md").write_text("# stove\n", encoding="utf-8")
    built(root, into)
    (root / "pack.md").write_text("# pack\n", encoding="utf-8")
    built(root, into)

    assert main(["log", str(into), "--json"]) == DONE
    entries = json.loads(capsys.readouterr().out)
    assert len(entries) == 3
    oldest = entries[-1]["entry_id"]

    assert main(["log", str(into), "--json", "--since", oldest]) == DONE
    after = json.loads(capsys.readouterr().out)
    assert [entry["added"] for entry in after] == [["documents/pack.md"], ["documents/stove.md"]]

    assert main(["log", str(into), "--since", "nosuchrun"]) == FAILED


def test_the_answer_document_is_one_shape_everywhere(tmp_path: Path) -> None:
    """The command line and the server hand out the same keys, so a consumer
    reading both has one vocabulary."""
    root = tmp_path / "vault"
    into = tmp_path / "corpus"
    built(root, into)
    corpus = Corpus(into)
    at = corpus.artefact("design/gear.md").index("2.4kg")
    found = resolve(corpus, "design/gear.md", Span(at, at + 5))
    document = as_document(found)

    served = text_of(
        mcp(
            tmp_path,
            "musubi_trace",
            path=str(into / DOCUMENTS / "design" / "gear.md"),
            start=at,
            end=at + 5,
        )
    )
    assert set(served) == set(document)
    assert served["status"] == document["status"] == "resolved"
