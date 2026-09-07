# ADR-0041 — An artefact is named for what musubi wrote

**Status:** accepted
**Date:** 2026-09-08
**`.html` in, `.md` out — and the lookup that had to stop guessing at a filename.**

## Context

The fetched lane writes an artefact per page, named after the page:
`documents/feed/2026-09-05/a1b2.html`. The artefact is not HTML. It is front
matter and extracted prose, and [ADR-0037](0037-a-fetch-record-beside-the-page-is-a-fact-musubi-may-state.md)
already listed the name as a cost and sent the question to the seam.

`tsumugi` answered directly (`musubi-work/01_tsumugi_answer_on_html_names.md`),
and the answer was worse than the question expected:

> `.html` はどの parser も claim していない。（…）**その corpus は 1 件も索引されない。**

Not *the extracted text is parsed as markup* — nothing is parsed at all. Every
file is skipped with a reason, and a fetched corpus is indexed **not at all**,
which is silent except for a count. And tsumugi declined to claim `.html`, for
the reason that decides this: *拡張子はそのファイルが どの形式か の宣言で,
`.html` という名前の「front matter + 抽出テキスト」は形式について嘘をついている* —
and claiming it would mean reading real HTML as Markdown, since the registry
allows one parser per suffix.

Sora asked for the change now, while it holds no references: *後になるほど高くつく*.

## Decision

**`FetchedSource` keys a unit by its path with musubi's own suffix**:
`feed/2026-09-05/a1b2.html` becomes `feed/2026-09-05/a1b2.md`. The artefact is
Markdown — front matter is a Markdown convention and the prose reads as
Markdown — and the name now says so.

**The source declares it.** `key_derivation` is no longer `path`, and
[ADR-0006](0006-the-unit-of-sync-is-the-record.md) makes that declaration a
thing a reader can rely on: a manifest that still said `path` while the key was
not the path would be the manifest saying something untrue.

**And the map records where the source is.** This is the part the change could
not be made without.

`Corpus._source_file` found the original by joining the **key** to the source
root. That worked while a key was a filename, and it is exactly what breaks
when a source derives one: the lookup would ask for `feed/a.md`, the page is
`feed/a.html`, and `musubi trace` stops finding the original — which is the
entire reason the fetched lane goes through musubi. Sora's screen is *click the
citation and the original opens at that position*.

So `Unit`, the trace map's `source` block and `SourceReference` carry
**`origin`** — how the source finds the unit again, opaque above the source
that produced it. The lookup follows `origin`, and falls back to the key for a
map written before it existed, where the two were the same thing.

**Only the fetched source.** An `ObsidianSource` vault holding a `.pdf` produces
an artefact named `.pdf` that tsumugi also skips, and that is the same problem
unfixed. It is left unfixed on purpose: changing every source's keys moves
every `unit_key` in every existing corpus, and `kiseki-notes` hashes the
corpus-relative path to make a note's stable reference. Sora's lane is new and
holds no references; a vault somebody has been syncing for months is not.

## Consequences

- A fetched corpus is now indexable by `tsumugi` at all, which it was not.
- `unit_key`, the artefact path, the trace path and the export id all move for
  the fetched lane. Sora asked for exactly that and said why now.
- `origin` is a new optional field on `musubi.trace-map/1-draft`. Draft, so the
  version does not move ([ADR-0024](0024-a-field-added-is-a-new-contract.md)).
- Two pages that would share a key — `a.html` and `a.md` in one folder — stop
  the run, which is [ADR-0006](0006-the-unit-of-sync-is-the-record.md)'s
  existing refusal reaching a case it could not previously reach.
- The two tests that corrupted `source.unit_key` to check a missing source now
  corrupt `origin`, because that is the field the lookup follows.

## What it costs

**Two sources now answer the same question differently.** A `.html` page in a
fetched folder becomes `a.md`; the same page in a vault stays `a.html`. Both
are defensible and the pair is not: a reader who learns the rule from one
source has learned it wrongly for the other. `key_derivation` is what makes the
difference legible, and it is a field a reader has to look at rather than a
thing they can assume.

**The key no longer round-trips to a filename**, and something will assume it
does. It was true for every source until now, `origin` is what replaces it, and
a consumer that joins `unit_key` to a source root will be right about three
sources and wrong about one — silently, because the file it asks for simply
does not exist and a missing source degrades rather than fails.

**And the suffix is a claim about format that musubi does not check.** A
converter that returned something that is not Markdown would still get a `.md`
name here. What makes it true today is that every converter's output is prose
with musubi's front matter on top; nothing enforces that, and the day one
returns something else this name becomes the lie it was written to remove.
