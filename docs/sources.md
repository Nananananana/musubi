# The sources, and what each one can promise

A source's job is to say what is there and hand over bytes. What makes them
different from each other is **identity**: what a unit is called, whether that
name survives a re-export, and what happens to a corpus when it does not.

ADR-0006 is the argument. This page is the answer, per source, with the parts
that are not yet answered marked as such.

## What each one keys by

| source | `key_derivation` | a unit is | survives a rename? |
|---|---|---|---|
| `ObsidianSource`, `FilesystemSource` | `path` | one file, keyed by its path relative to the root | **no** — moving a file looks like a delete plus an add |
| `NotionSource` | `notion-page-id` | one exported page, keyed by the 32-character id in its filename | **probably, and not yet measured** |

Every manifest carries its source's `key_derivation`, so a reader can see which
weakness applies without being told (`docs/contracts.md`, *What a consumer
inherits*).

---

## `ObsidianSource` / `FilesystemSource`

**Reads** `.md`, `.markdown`, `.mdown`, `.mkd`, `.txt`, `.text`, `.html`,
`.htm`, `.xhtml`, `.pdf`. Anything else is skipped **by name, before the file is
opened** — cheaper and more honest than reading it and failing to convert it.

**Skips** `.git`, `.hg`, `.svn`, `.obsidian` and the other machinery
directories, whole. Files over 8 MB are skipped with their size.

**Keys by path**, which is the known weakness ADR-0006 names rather than hides: a
folder of files has no other identity to offer. Renaming or moving a note is a
delete and an add, and every reference a consumer derived from the old path
points at a document that no longer exists.

**Keeps each document's modification time** (ADR-0022), so a corpus has the
history the vault had.

---

## PDFs with a composite font

`pdf_text@1` **refuses** a PDF that declares a `Type0` font, with reason
`composite_font`. Under one, the bytes a text operator shows are glyph indices
rather than characters, and the map to characters is in the font's `ToUnicode`
CMap, which this converter does not read.

That covers every PDF holding Japanese, Chinese or Korean, and most current
producers' subsetted Latin fonts. `pip install 'musubi[pdf]'` reads them, and
the refusal names it
([ADR-0039](adr/0039-a-fixture-whose-answer-is-known-and-the-two-things-it-found.md)).

---

## `FetchedSource`

`--as fetched`, or `source = "fetched"`. A folder of pages somebody fetched --
an orchestrator pulling articles from feeds -- with a **record of the fetch
beside each page**:

```text
<root>/<feed>/<date>/<id>.html
<root>/<feed>/<date>/<id>.html.fetch.json
```

```json
{"url": "https://example.test/a/1", "fetched_at": "2026-09-05T03:12:00Z",
 "canonical_url": "https://example.test/a/1"}
```

**Reads** what `FilesystemSource` reads, keyed by path, and states the record's
facts in the document's front matter as `source_url`, `fetched_at` and
`canonical_url` -- beside `layer` and `producer`, as flat `key: value` lines
([ADR-0037](adr/0037-a-fetch-record-beside-the-page-is-a-fact-musubi-may-state.md)).
**The page's bytes are never touched**, so `musubi trace` still leads to what
was fetched. The facts are also recorded in the manifest beside the artefact,
and a record that changed under an unchanged page converts the unit again.

**Reads one article once.** Two pages whose records share a `canonical_url`
(or a `url`, when no canonical one is given) are one article: the first in walk
order is read, the rest are skipped as `duplicate` naming the page that stood
for them. Pages with no record are never taken for one another.

**Skips** a record that cannot be read as `bad_fetch_record`, with the reason. A
page with no record is read and states nothing. The record files themselves
are neither documents nor skips.

**`discover()` opens the records**, which is the one place a source departs
from the two stages: deduplication decides what is found and what is skipped,
and that is discovery's answer to give. **No page is opened** — a plan still
reports what it will skip without having read a word of what it will convert,
and a record is the orchestrator's note about a fetch rather than the owner's
document.

**Keys by path.** The orchestrator controls the layout, and a key it can read
in a citation is worth more than one derived from a URL.

---

## `NotionSource`

**Reads** the archive a Notion export produces, or a folder holding one.
Archives nest — `<uuid>_ExportBlock-<uuid>.zip` contains
`ExportBlock-<uuid>-Part-1.zip` contains the pages — and the walk follows them
four levels deep, which is a stated cap rather than unbounded recursion.

**Keys by the page id**: the 32 hexadecimal characters Notion puts at the end of
every exported filename. Not the title, and not the path.

**Why the id and not the title.** The key becomes the output filename
(ADR-0013), so keying by title would give readable names that change whenever
somebody renames a page — and a renamed page would arrive in the corpus as a
new document with no history. The id costs a corpus of hexadecimal filenames and
**loses nothing**, because Notion writes the title into the document's first
line as an `# ` heading. Measured on a real export: the title in the filename and
the H1 in the body are the same string.

**A file with no page id is skipped**, with reason `no_page_id`. Falling back to
the path for those would make `key_derivation` true for some units in a run and
false for others, with nothing in the manifest saying which.

### What is not yet established

**Whether a page id survives a re-export.** ADR-0006 contradicts itself here: its
Context says the UUID in an export filename *is regenerated per export*, its
Decision keys by *the page id parsed out of the filename*. A real export shows
**three UUIDs on three layers** — the export job, the block, and the page file's
suffix — so the two statements may be about different numbers and the
contradiction may be a sentence that never said which one it meant.

**One export cannot settle it.** The question is now narrow enough that a single
counterexample decides it: *is this specific suffix the same on the next export
of the same page*. Until a second export answers that, this source keys by the
page id and **says so in the manifest**. If the answer is no, the derivation
falls back to `path` and the manifest says `path`. The default does not become a
decision by accident.

### What a Notion corpus does not have

**A time axis.** Every entry in an export archive carries the *export's*
timestamp, not the page's — measured: the outer entry and the inner entry share
one to the second. So `NotionSource` reports no modification time at all rather
than handing on a date that is the same for every page and looks like history.

The consequence is real and worth stating plainly: a consumer that reads a
document's mtime as *the day it was written* will see one date across the whole
corpus. That is not musubi losing the information — **the export does not
contain it.** `kiseki-notes` warns when more than half a corpus shares a date,
and for a Notion corpus that warning is correct.

### What is not measured

**Cross-link rewriting.** A Notion export rewrites internal links to point at
the exported filenames, which musubi renames. Nothing here handles that yet, and
the one real export available is a single page with **zero internal links**, so
there is no evidence to build against. Stated rather than assumed to be fine.

**Databases.** `.csv` is recognised as a media type so that discovery reports it
instead of passing over it in silence. There is no converter for it, so it is
skipped with a reason like any other unsupported format.

---

## The ten-question gate

`kiseki` keeps a ten-question gate that a new source is meant to be answered
against, and the roadmap (§9, v0.5) says this page carries the answers.

**They are not answered here, because the questions have not been transcribed
into this repository.** Writing down what musubi believes the questions to be
and answering that would produce a page that looks complete and is checked
against nothing — the failure this project spends most of its time avoiding.

The one that is known, and worth answering for every source whoever consumes it:

> **What could this reveal that the owner would not choose to reveal?**

For all four sources the answer is the same, and it is stated here rather than
pointed at, because `docs/threat-model.md` is a file this repository plans and
does not have: **a synced folder is a copy of the owner's documents, and a trace
map is a per-character index of them.** The screener (ADR-0008) stops a run that
would carry a credential into the corpus; nothing stops a corpus from being a
corpus, and ADR-0019 is why a manifest inherits the classification of what it
describes.
