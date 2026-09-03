# The documents, and what each one is for

musubi's documentation is written so that three different things never get
mistaken for one another:

- **what is true now** — the current architecture and rules;
- **why it became true** — the decisions, as they were made;
- **what might become true** — proposed and planned work.

A reader who cannot tell these apart will implement a proposal as though it
shipped, or "fix" an ADR to match today's code and erase the reasoning that
produced it. Both have a cost that grows with the project, so the separation is
structural: each document says at the top which of the three it is.

This convention is taken from the sibling projects `kiseki`, `tsumugi` and
`akashi`, which learned it the expensive way.

## Responsibilities

| Document | Responsibility |
|---|---|
| `README.md` | For anyone outside: what musubi is, what it solves, what it can do |
| `AGENTS.md` | For contributors and AI agents: the current rules, constraints and state |
| `docs/concept.md` | The conceptual model, and the whole picture across five projects |
| `docs/architecture.md` | The current architecture — **not written yet, on purpose** |
| `docs/contracts.md` | The SyncManifest and TraceMap contracts, for producers and consumers — including what the schemas cannot say |
| `docs/sources.md` | Per source: its key derivation, its rule pack, and `kiseki`'s ten questions answered |
| `docs/configuration.md` | Every setting, where they are read from, and which algorithms a setting can name |
| `docs/threat-model.md` | What a synced folder and a trace map contain, and what they become if they leak |
| `docs/evaluation-corpus.md` | The generated dataset: its shape, its plants, and what it cannot tell you |
| `docs/measurements.md` | Traceable coverage, map size, screener recall and the re-read ratio, with the tools that produced them |
| `docs/adr/` | Decisions as they were made, with their reasons — history |
| `docs/proposals/` | Proposed or planned work — not necessarily implemented |
| [GitHub milestones](https://github.com/Nananananana/musubi/milestones?state=all) | One per roadmap chapter: where each stands, and every correction the roadmap cannot carry |
| `CHANGELOG.md` | The released history, briefly |

**A roadmap chapter's current state is a milestone, not the roadmap.** The design
document is left as written once the code disagrees with it, which is what makes
it evidence of what was planned — and useless as an answer to *where is this
now*. There is one milestone per chapter of
[`proposals/0001-the-design.md`](proposals/0001-the-design.md) §9, and the
descriptions carry what the document cannot be edited to say. Three of them are
corrections rather than progress:

- **v0.2** — the freeze is a *condition* recorded in that chapter, not a
  deliverable of it. It completes with both contracts still `-draft`, and
  `musubi verify` does **not** satisfy the condition, though the roadmap guesses
  it might.
- **v0.4** — one item is calendar-bound and should start now rather than there:
  the two real exports taken weeks apart, which are collected and cannot be
  generated.
- **v0.6** — the seam in that chapter is `mamori`, not `tsumugi`.

## The rules that keep them apart

- An ADR is not edited to match the present. A decision that no longer holds is
  superseded by a later ADR that says so; the original stays as it was written,
  because the reasoning is the point.
- A proposal is never cited as evidence that something exists. When a proposal
  lands, the current-state documents change and the proposal stays where it is,
  describing what was proposed.
- The current-state documents describe what the code does today. If one of them
  disagrees with the code, one of the two is wrong and the disagreement is a
  defect — not a difference of opinion.
- An architecture document says why, not only what. A rule without its reason is
  a rule the next reader will break for good reasons of their own.
- **A number in a document is measured or it is not written.** Every table of
  scores names the script that produced it, the corpus it ran on, and what the
  number does not cover.
- **"What exists" is updated in the same pull request as the code it describes.**
  This project's whole claim is that its documents and its code do not diverge, so
  a README saying *nothing is built* over a working command costs more credibility
  than any other kind of staleness. It happened once, in the four days between the
  design landing and the CLI working, and this line is the answer to it.

## Where the project is right now

**v0.1 is done.** `musubi plan`, `musubi sync` and `musubi trace` work: a folder
of notes becomes a corpus in which every character can be traced back to the
byte it came from, nothing is written until the whole run has passed, and the
invariants a schema cannot express are asserted against generated corpora rather
than only enumerated.

Nothing is released and the public API is not stable. The full list of what does
and does not exist is below, and it is the thing to trust over any sentence
elsewhere in this repository.

Read in this order:

1. [`proposals/0001-the-design.md`](proposals/0001-the-design.md) — the design
   and the roadmap, written before the code and left as written afterwards.
2. [`adr/0004`](adr/0004-a-conversion-carries-a-map-back-to-its-source.md) — the
   decision the rest of the design is arranged around.
3. [`adr/0005`](adr/0005-say-what-was-removed-and-by-which-rule.md) — the
   decision that makes 0004 honest.
4. [`adr/0007`](adr/0007-musubi-reads-exports-never-services.md) — the boundary
   that makes everything else checkable.
5. [`adr/README.md`](adr/README.md) — the rest.

## What exists

This section is the one a reader should trust over any sentence elsewhere. It is
the answer to *is this thing real yet*, and it is kept current in the same pull
request as the code it describes.

**Built, and exercised end to end by `musubi plan`:**

| | |
|---|---|
| `musubi plan` | Reads a folder and reports what a sync would do, writing nothing ([ADR-0012](adr/0012-a-dry-run-comes-first.md)) |
| Sources | `FilesystemSource`, `ObsidianSource`, `NotionSource`. Two stages: `discover()` opens nothing, `read()` opens one thing. Notion keys by the **page id** and skips anything without one, so `key_derivation` is true of every unit in a run ([`sources.md`](sources.md)) |
| Converters | Markdown and plain text — decoding, line endings, and a trace map over both |
| `trafilatura@1` | **Optional** (`pip install 'musubi[html]'`). Main-content extraction that wins its benchmarks, with the map **recovered by alignment** rather than built while converting. Measured on one generated page: 6/6 planted boilerplate strings rejected against `html@1`'s 3/6, and **99.7% traceable against 93.5%** ([ADR-0028](adr/0028-a-dependency-outside-the-domain-buys-quality-and-still-owes-a-map.md), `tools/html_coverage.py`). Offered, never claimed: installing it changes no folder's output until a settings file names it |
| `pdfium@1` | **Optional** (`pip install 'musubi[pdf]'`). Chrome's PDF engine, behind a dependency-free BSD-3-Clause wheel. The case is **reach, not quality**: `pdf_text@1` scans for `N 0 obj` and reports `no_pages` on a PDF 1.5, where the page lives in a compressed object stream — which is what almost every current producer writes ([ADR-0029](adr/0029-a-better-reader-does-not-buy-a-finer-locator.md), `tools/pdf_coverage.py`). Same `src` spans as `pdf_text@1`, asserted by a test: a corpus rebuilt with it still cites *page three* |
| Alignment | `domain/alignment.py`. Finds an extractor's text in the source and tiles what is left: verbatim where a run is there, transformed where it is not, `removal` for a stretch that produced nothing. A forward scan with a bounded window, not a diff |
| `html@1` | HTML, where the output is a minority of the input: boilerplate removed as `removal` segments with rules, entities `transformed`, structure `synthetic`. The first converter whose traceable coverage is a measurement |
| `pdf_text@1` | A PDF's text layer, page by page. The first map whose source is **not** characters: `src` is a page range and `source_unit` is `opaque` ([ADR-0025](adr/0025-a-map-with-no-verbatim-run-composes-whatever-it-measures.md)). A page with no text layer is reported, not guessed at |
| The tiling | Segments, composition, merging, coverage ([ADR-0004](adr/0004-a-conversion-carries-a-map-back-to-its-source.md)) |
| Cleansing | 65 rules derived from ClearURLs, matched structurally and never by regex ([ADR-0016](adr/0016-a-rule-is-a-matcher-not-a-regular-expression.md)) |
| Screening | 21 credential signatures; the entropy tier exists and is opt-in ([ADR-0017](adr/0017-entropy-is-a-tier-not-a-default.md)) |
| `musubi sync` | The same run with the writing on: staged, promoted together, and a credential means nothing is written at all ([ADR-0008](adr/0008-a-credential-stops-the-run.md)) |
| `musubi trace` | A range of a synced document, resolved back through every transformation to a place in the file you have ([ADR-0004](adr/0004-a-conversion-carries-a-map-back-to-its-source.md)) |
| The emitter | Front matter, the trace sidecar, staging, atomic promotion, and withdrawal |
| The contracts | Both schemas, shipped in the wheel, validated against real output ([`contracts.md`](contracts.md)) |
| The invariants | What the schemas cannot express, asserted against generated corpora — and a guard that fails if the enumeration grows an entry nothing runs |
| `musubi config` | Every setting in effect **with the thing that decided it**, and the files found and not read. Reads a `musubi.toml`, a `[tool.musubi]` table or the environment; the nearest file wins whole ([ADR-0027](adr/0027-the-nearest-file-wins-whole-and-every-value-says-where-it-came-from.md)) |
| `musubi verify` | The same invariants, run against a folder rather than a run — plus the one no test can make, that each document still hashes to what the manifest recorded |

**Not built, and named rather than implied:**

- **`musubi rules`**, `musubi eval`, `musubi doctor`. Named in the design, none
  written.
- **The incremental path.** A sync withdraws an artefact whose unit is gone, by
  reading the previous manifest as its ledger — but it still re-reads, converts
  and rewrites every unit that *is* there. `Change` exists and nothing calls it,
  so every run is a cold one.
- **Notion, Slack, HTML, PDF.** v0.3, and the milestone where traceable coverage
  stops being 1.0 by construction and starts being a measurement.
- **Every number in `docs/measurements.md`**, because that file does not exist.
  No recall is claimed for the screener and no coverage is claimed for any
  format; v0.4 owes both.
- **`docs/architecture.md`**, deliberately. An ADR before the code is legitimate,
  because it records a decision that has been made. A current-state document
  before the code is fiction — and this table is the current-state document until
  there is enough architecture to be worth describing on its own.
