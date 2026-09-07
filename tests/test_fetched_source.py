"""A folder of fetched pages, and the record beside each one.

Written for the `sora` orchestrator's news lane (R1, U1, U2 in
`musubi-work/01_sora_requirements.md`). The facts a page does not state about
itself -- where it was fetched from, when -- travel in a record beside it and
are stated by musubi in the document's front matter. The page's bytes are never
touched, so a trace still leads to what was fetched.

The tests are about the ways this could quietly be wrong: a record read into
the wrong document, a record that changed under an unchanged page being
carried forward, two feeds' copies of one article both making it in, and a
record whose value would break the one-line-per-key reader downstream.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from musubi import __version__
from musubi.application.pipeline import Settings
from musubi.application.sync import Synced, sync
from musubi.application.trace import resolve
from musubi.application.verify import verify
from musubi.domain.frontmatter import FrontMatter
from musubi.domain.record import unit_key
from musubi.domain.span import Span
from musubi.errors import SourceError
from musubi.infrastructure.converters import converter_for
from musubi.infrastructure.corpus import Corpus
from musubi.infrastructure.emitters import DOCUMENTS, MANIFEST, DocumentEmitter
from musubi.infrastructure.rules import CORE
from musubi.infrastructure.screeners import default_screener
from musubi.infrastructure.sources import FetchedSource, ObsidianSource
from musubi.infrastructure.sources.fetched import RECORD_SUFFIX

PAGE = "<html><body><article><h1>Gear</h1><p>The tent weighs 2.4kg.</p></article></body></html>\n"


def fetched(root: Path, pages: dict[str, tuple[str, dict[str, str] | None]]) -> Path:
    """Pages laid out the way the orchestrator lays them out, each with or
    without a record."""
    for name, (body, record) in pages.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        if record is not None:
            (root / (name + RECORD_SUFFIX)).write_text(json.dumps(record), encoding="utf-8")
    return root


def synced(root: Path, into: Path, at: str = "2026-09-06T00:00:00+00:00") -> Synced:
    return sync(
        FetchedSource(root),
        Settings(CORE, default_screener(), converter_for, __version__, created_at=at),
        DocumentEmitter(into),
    )


RECORD = {"url": "https://example.test/gear", "fetched_at": "2026-09-05T03:12:00Z"}


# -- the facts reach the document, and only the document they are about -----


def test_the_record_is_stated_in_the_front_matter(tmp_path: Path) -> None:
    root = fetched(tmp_path / "fetched", {"feed/2026-09-05/a.html": (PAGE, RECORD)})
    into = tmp_path / "corpus"
    synced(root, into)

    text = (into / DOCUMENTS / "feed" / "2026-09-05" / "a.md").read_text(encoding="utf-8")
    head = text.split("---")[1]
    assert "source_url: https://example.test/gear" in head
    assert "fetched_at: 2026-09-05T03:12:00Z" in head
    assert "layer: fact" in head
    assert "2.4kg" in text


def test_the_page_itself_is_never_touched_so_the_trace_still_lands(tmp_path: Path) -> None:
    """The whole point. A page with front matter written into it would be a
    page whose bytes are no longer the fetched bytes."""
    root = fetched(tmp_path / "fetched", {"feed/a.html": (PAGE, RECORD)})
    into = tmp_path / "corpus"
    synced(root, into)

    assert (root / "feed" / "a.html").read_text(encoding="utf-8") == PAGE
    assert verify(Corpus(into)).holds
    text = (into / DOCUMENTS / "feed" / "a.md").read_text(encoding="utf-8")
    at = text.index("2.4kg")
    from musubi.application.trace import resolve
    from musubi.domain.span import Span

    found = resolve(Corpus(into), "feed/a.md", Span(at, at + 5))
    assert not found.changed and found.source_path is not None
    assert found.source_excerpt == "2.4kg"


def test_a_record_belongs_to_the_page_it_sits_beside(tmp_path: Path) -> None:
    root = fetched(
        tmp_path / "fetched",
        {
            "feed/a.html": (PAGE, {"url": "https://example.test/a", "fetched_at": "t1"}),
            "feed/b.html": (
                PAGE.replace("Gear", "Stove"),
                {"url": "https://example.test/b", "fetched_at": "t2"},
            ),
        },
    )
    facts = {unit_key(*f.key_parts): dict(f.facts) for f in FetchedSource(root).discover().found}
    assert facts["feed/a.md"]["source_url"] == "https://example.test/a"
    assert facts["feed/b.md"]["source_url"] == "https://example.test/b"


def test_the_record_is_neither_a_document_nor_a_skip(tmp_path: Path) -> None:
    """Reporting every record as `unknown_format` would double the length of
    every manifest for no information."""
    root = fetched(tmp_path / "fetched", {"feed/a.html": (PAGE, RECORD)})
    discovery = FetchedSource(root).discover()
    assert [unit_key(*f.key_parts) for f in discovery.found] == ["feed/a.md"]
    assert discovery.skipped == ()


def test_a_page_without_a_record_is_read_and_states_nothing(tmp_path: Path) -> None:
    root = fetched(tmp_path / "fetched", {"feed/a.html": (PAGE, None)})
    into = tmp_path / "corpus"
    synced(root, into)
    text = (into / DOCUMENTS / "feed" / "a.md").read_text(encoding="utf-8")
    assert not text.startswith("---"), "no facts, no front matter on an HTML page"
    assert "2.4kg" in text


def test_a_record_that_cannot_be_read_is_a_skip_with_its_reason(tmp_path: Path) -> None:
    """A record that lies is worse than none."""
    root = fetched(tmp_path / "fetched", {"feed/a.html": (PAGE, None)})
    (root / "feed" / ("a.html" + RECORD_SUFFIX)).write_text("{not json", encoding="utf-8")
    discovery = FetchedSource(root).discover()
    assert discovery.found == ()
    assert [(s.origin, s.reason) for s in discovery.skipped] == [
        ("feed/a.html", "bad_fetch_record")
    ]


def test_a_value_with_a_line_break_is_refused_before_it_reaches_a_document(tmp_path: Path) -> None:
    """The reader downstream takes one line per key. A value that breaks the
    line would put the rest of itself into the document body."""
    root = fetched(
        tmp_path / "fetched",
        {"feed/a.html": (PAGE, {"url": "https://x\nsource_url: https://y", "fetched_at": "t"})},
    )
    discovery = FetchedSource(root).discover()
    assert [s.reason for s in discovery.skipped] == ["bad_fetch_record"]
    assert "line break" in discovery.skipped[0].detail


def test_a_fact_may_not_overwrite_what_musubi_states() -> None:
    with pytest.raises(ValueError, match="not a key a fact may be stated under"):
        FrontMatter(facts=(("layer", "interpretation"),))
    with pytest.raises(ValueError, match="not a key a fact may be stated under"):
        FrontMatter(facts=(("a:b", "x"),))


def test_discovery_opens_the_records_and_never_a_page(tmp_path: Path) -> None:
    """The one departure this source makes from the two stages, asserted.

    Deduplication decides what is found and what is skipped, and that is
    discovery's answer to give, so the records are opened. The promise that
    mattered is that `musubi plan` can report what it will skip before a word
    of what it will convert has been read -- so the pages stay shut, and this
    watches every `open` to say so.
    """
    root = fetched(
        tmp_path / "fetched",
        {"feed/a.html": (PAGE, RECORD), "feed/b.html": (PAGE.replace("Gear", "Stove"), None)},
    )

    opened: list[str] = []
    real = Path.read_text
    real_bytes = Path.read_bytes

    def noting_text(self: Path, *args: object, **kwargs: object) -> str:
        opened.append(self.name)
        return real(self, *args, **kwargs)  # type: ignore[arg-type]

    def noting_bytes(self: Path) -> bytes:
        opened.append(self.name)
        return real_bytes(self)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "read_text", noting_text)
        patch.setattr(Path, "read_bytes", noting_bytes)
        discovery = FetchedSource(root).discover()

    assert len(discovery.found) == 2
    assert opened == ["a.html" + RECORD_SUFFIX], opened


# -- the same article from two feeds ----------------------------------------


def test_the_same_canonical_url_is_read_once_and_the_rest_say_which_stood_for_them(
    tmp_path: Path,
) -> None:
    """Two feeds carried one article. A corpus with both answers the same
    question twice, and the orchestrator draws two cards."""
    article = {
        "url": "https://a.test/x?utm=1",
        "fetched_at": "t",
        "canonical_url": "https://a.test/x",
    }
    again = {"url": "https://b.test/mirror", "fetched_at": "t", "canonical_url": "https://a.test/x"}
    root = fetched(
        tmp_path / "fetched",
        {"feed-a/2026/x.html": (PAGE, article), "feed-b/2026/y.html": (PAGE, again)},
    )
    discovery = FetchedSource(root).discover()
    assert [unit_key(*f.key_parts) for f in discovery.found] == ["feed-a/2026/x.md"]
    (skip,) = discovery.skipped
    assert (skip.origin, skip.reason) == ("feed-b/2026/y.html", "duplicate")
    assert "feed-a/2026/x.html" in skip.detail


def test_without_a_canonical_url_the_url_itself_decides(tmp_path: Path) -> None:
    root = fetched(
        tmp_path / "fetched",
        {"a/x.html": (PAGE, RECORD), "b/y.html": (PAGE, RECORD)},
    )
    discovery = FetchedSource(root).discover()
    assert len(discovery.found) == 1
    assert [s.reason for s in discovery.skipped] == ["duplicate"]


def test_pages_that_say_nothing_are_never_taken_for_one_another(tmp_path: Path) -> None:
    """No record, no article identity, no deduplication. Silence is not
    evidence that two pages are the same."""
    root = fetched(tmp_path / "fetched", {"a/x.html": (PAGE, None), "b/y.html": (PAGE, None)})
    assert len(FetchedSource(root).discover().found) == 2


def test_the_cap_names_the_deduplication(tmp_path: Path) -> None:
    root = fetched(tmp_path / "fetched", {"a.html": (PAGE, RECORD)})
    assert any("canonical url" in cap for cap in FetchedSource(root).discover().caps)


# -- the manifest, and the re-sync ---------------------------------------------


def test_the_manifest_records_the_facts_beside_the_artefact(tmp_path: Path) -> None:
    root = fetched(tmp_path / "fetched", {"feed/a.html": (PAGE, RECORD)})
    into = tmp_path / "corpus"
    synced(root, into)
    body = json.loads((into / MANIFEST).read_text(encoding="utf-8"))
    (artefact,) = body["artefacts"]
    assert artefact["facts"] == {
        "source_url": "https://example.test/gear",
        "fetched_at": "2026-09-05T03:12:00Z",
    }


def test_a_changed_record_under_an_unchanged_page_converts_the_unit_again(tmp_path: Path) -> None:
    """The facts are in the artefact and not in the page's bytes, so the bytes
    agreeing is not enough ([ADR-0036] compares both)."""
    root = fetched(tmp_path / "fetched", {"feed/a.html": (PAGE, RECORD)})
    into = tmp_path / "corpus"
    synced(root, into)

    moved = {**RECORD, "fetched_at": "2026-09-06T03:12:00Z"}
    (root / "feed" / ("a.html" + RECORD_SUFFIX)).write_text(json.dumps(moved), encoding="utf-8")
    result = synced(root, into, at="2026-09-06T00:00:01+00:00")

    assert result.kept == ()
    text = (into / DOCUMENTS / "feed" / "a.md").read_text(encoding="utf-8")
    assert "fetched_at: 2026-09-06T03:12:00Z" in text
    assert verify(Corpus(into)).holds


def test_an_unchanged_page_and_record_are_carried_forward(tmp_path: Path) -> None:
    root = fetched(tmp_path / "fetched", {"feed/a.html": (PAGE, RECORD)})
    into = tmp_path / "corpus"
    synced(root, into)
    result = synced(root, into, at="2026-09-06T00:00:01+00:00")
    assert result.kept == ("feed/a.md",)


def test_the_export_carries_the_facts_a_reader_can_key_on(tmp_path: Path) -> None:
    """A consumer that reads the export rather than the documents still learns
    where a page came from."""
    import musubi

    root = fetched(tmp_path / "fetched", {"feed/a.html": (PAGE, RECORD)})
    into = tmp_path / "corpus"
    synced(root, into)
    (row,) = list(musubi.documents(into))
    assert row.text.startswith("---")
    assert "source_url: https://example.test/gear" in row.text[: row.metadata["body_offset"]]


# -- named for what musubi wrote, not for what it read ----------------------


def test_the_artefact_is_markdown_and_the_page_is_still_html(tmp_path: Path) -> None:
    """`tsumugi` claims no parser for `.html`, so an ingest skipped every file
    and **the corpus was not indexed at all** -- worse than being read wrong,
    and silent but for a count of skips. The artefact is front matter and
    extracted prose; `.md` is the format it is in ([ADR-0041])."""
    root = fetched(tmp_path / "fetched", {"feed/2026/a.html": (PAGE, RECORD)})
    into = tmp_path / "corpus"
    synced(root, into)

    assert (into / DOCUMENTS / "feed" / "2026" / "a.md").is_file()
    assert not (into / DOCUMENTS / "feed" / "2026" / "a.html").exists()
    assert (root / "feed" / "2026" / "a.html").read_text(encoding="utf-8") == PAGE
    assert (into / "traces" / "feed" / "2026" / "a.md.json").is_file()


def test_the_original_is_still_what_a_trace_opens(tmp_path: Path) -> None:
    """The trap this had to avoid.

    A source file used to be found by joining the **key** to the source root.
    Rename the key to `.md` and that lookup asks for a page that does not
    exist, so `musubi trace` stops finding the original -- which is the whole
    reason the fetched lane goes through musubi. The map records `origin`, and
    the lookup follows that.
    """
    root = fetched(tmp_path / "fetched", {"feed/a.html": (PAGE, RECORD)})
    into = tmp_path / "corpus"
    synced(root, into)

    text = (into / DOCUMENTS / "feed" / "a.md").read_text(encoding="utf-8")
    at = text.index("2.4kg")
    found = resolve(Corpus(into), "feed/a.md", Span(at, at + 5))

    assert found.source_path is not None
    assert found.source_path.name == "a.html", "the page, not the key"
    assert found.source_excerpt == "2.4kg"
    assert found.source_bytes is not None
    assert not found.changed


def test_the_map_records_where_the_source_is(tmp_path: Path) -> None:
    root = fetched(tmp_path / "fetched", {"feed/a.html": (PAGE, RECORD)})
    into = tmp_path / "corpus"
    synced(root, into)

    body = json.loads((into / "traces" / "feed" / "a.md.json").read_text(encoding="utf-8"))
    assert body["source"]["unit_key"] == "feed/a.md"
    assert body["source"]["origin"] == "feed/a.html"


def test_a_map_written_before_origin_still_finds_its_source(tmp_path: Path) -> None:
    """Where the two were the same thing. A reader that required the new field
    would stop resolving every corpus written before it."""
    vault = tmp_path / "notes"
    vault.mkdir()
    (vault / "gear.md").write_text("# gear\n\nテントは 2.4kg。\n", encoding="utf-8")
    into = tmp_path / "corpus"
    sync(
        ObsidianSource(vault),
        Settings(CORE, default_screener(), converter_for, __version__),
        DocumentEmitter(into),
    )
    sidecar = into / "traces" / "gear.md.json"
    body = json.loads(sidecar.read_text(encoding="utf-8"))
    del body["source"]["origin"]
    sidecar.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")

    text = (into / DOCUMENTS / "gear.md").read_text(encoding="utf-8")
    at = text.index("2.4kg")
    found = resolve(Corpus(into), "gear.md", Span(at, at + 5))
    assert found.source_path is not None and found.source_excerpt == "2.4kg"


def test_the_manifest_declares_that_the_key_is_derived(tmp_path: Path) -> None:
    """[ADR-0006]: a source declares how it derives a key, and the declaration
    goes in the manifest. A key that is no longer exactly the path while the
    manifest still says `path` is the manifest saying something untrue."""
    root = fetched(tmp_path / "fetched", {"feed/a.html": (PAGE, RECORD)})
    into = tmp_path / "corpus"
    synced(root, into)

    (source,) = json.loads((into / MANIFEST).read_text(encoding="utf-8"))["sources"]
    assert source["key_derivation"] != "path"
    assert "suffix" in source["key_derivation"]


def test_two_pages_that_would_share_a_key_stop_the_run(tmp_path: Path) -> None:
    """`a.html` and `a.md` in one folder both want `a.md`. One would overwrite
    the other with the manifest listing both -- a corpus smaller than its own
    account -- so the run stops rather than choosing ([ADR-0006])."""
    root = fetched(tmp_path / "fetched", {"feed/a.html": (PAGE, None)})
    (root / "feed" / "a.md").write_text("# other\n", encoding="utf-8")

    with pytest.raises(SourceError, match="two different units"):
        synced(root, tmp_path / "corpus")


def test_a_markdown_page_keeps_the_name_it_had(tmp_path: Path) -> None:
    root = fetched(tmp_path / "fetched", {"feed/note.md": ("# a note\n", RECORD)})
    into = tmp_path / "corpus"
    synced(root, into)
    assert (into / DOCUMENTS / "feed" / "note.md").is_file()


def test_the_export_carries_the_new_name(tmp_path: Path) -> None:
    """The id is `source_id:unit_key`, so it moves with the key. Sora asked for
    this now because it holds no references yet, and later it costs."""
    import musubi

    root = fetched(tmp_path / "fetched", {"feed/a.html": (PAGE, RECORD)})
    into = tmp_path / "corpus"
    synced(root, into)
    (row,) = list(musubi.documents(into))
    assert row.id == "fetched:feed/a.md"
