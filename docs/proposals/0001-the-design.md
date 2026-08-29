# musubi — the design, and the order it gets built in

**Status: proposed.** Nothing in this document exists yet. It is the plan,
written before the code, and it stays as written once the code disagrees with it
— the current-state documents are where the code is described. See
[docs/README.md](../README.md) for why that separation is structural.

Decisions already taken are in [docs/adr](../adr/README.md) and are not
re-argued here. This document is about *shape and order*.

---

## 1. What musubi is, in one paragraph

musubi turns the exports and folders somebody already has — an Obsidian vault, a
Notion zip, a Slack archive, a maildir, a shelf of PDFs — into clean, normalized
documents that a language-model pipeline can use, and it does it without ever
losing the correspondence back to the original bytes. It strips the tracking
identifiers and export scaffolding on the way through, records every subtraction
with the rule that made it, refuses to continue when it finds a credential, and
produces byte-identical output for byte-identical input. No network, no service
tokens, no model.

The name is 結び: the knot, the tying, the joining of two things that stay
themselves.

## 2. The problem, stated so that the design follows from it

By 2026 the retrieval half of RAG is solved infrastructure and the auditing half
is being solved — in this family, by `tsumugi` and `akashi`. Both rest on the
same guarantee: **every piece of context names the document, the offset and the
hash it came from.**

Underneath both of them sits a step nobody guarantees anything about.

Somebody's knowledge does not live in a folder of clean Markdown. It lives in a
Notion workspace, a Slack history, a mail archive, and four hundred PDFs. To get
it into `tsumugi` it has to be converted, and every converter in existence —
`markitdown`, `docling`, `unstructured`, `trafilatura`, every commercial parsing
API — has the same signature: bytes in, string out. The correspondence between
that string and the file it came from is discarded inside the library.

So the evidence chain has a hole in it, and the hole is at the bottom:

```text
gear.pdf  ──[ conversion ]──>  synced/gear.md  ──> tsumugi ──> akashi
             ^^^^^^^^^^^^                            │           │
             nothing recorded                        └── "doc_4b1e, offset 1204"
                                                           ...of a file musubi
                                                           invented last Tuesday
```

An anchor into `synced/gear.md` is real and checkable, and it points at a derived
artefact. The owner opens `gear.pdf` to see for themselves and there is nothing
to open it *to*. Meanwhile the conversion is exactly where silent corruption
enters — a two-column page reflowed in the wrong order interleaves two arguments
into sentences that never existed; a table flattened to lines pairs the wrong
value with the wrong label; a boilerplate stripper takes a paragraph of the
article with it. Every one of those produces fluent output that nothing
downstream can detect.

The design question is therefore not "which converter scores highest".

> **Can the conversion carry a map back to the source, at a cost worth paying —
> and does that map cover enough of a real corpus to close the hole?**

[ADR-0004](../adr/0004-a-conversion-carries-a-map-back-to-its-source.md) is the
answer: yes, if the converter's output is defined as a *tiling of segments over
the source* rather than as a string.
[ADR-0005](../adr/0005-say-what-was-removed-and-by-which-rule.md) is what keeps
it honest when musubi deliberately deletes.

### The second problem, which is why the first one is affordable

An ingestion layer is also the most dangerous component in a local-first stack,
because it is the one pointed at everything. It reads the vault that contains the
resignation letter, the mail archive, the notes about other people. It writes a
folder built to be sent to a language model.

Every connector product in this category solves that by being an API client with
an OAuth token per service. musubi solves it by
[not having a network](../adr/0007-musubi-reads-exports-never-services.md) — no
sockets, anywhere, checked by the build — and by
[stopping the run](../adr/0008-a-credential-stops-the-run.md) rather than quietly
skipping a unit when it finds something that looks like a secret.

The two problems share a solution, which is the reason this is one library. A
component with no network and no model can be made a pure function of its inputs,
and a pure function is the only kind of thing whose output map can be trusted.

## 3. What musubi is not

Stated first, because the boundary is the design.

- **Not a crawler, and not a search tool.** It reads a folder the owner named.
  Never the home directory, never "every document on this machine". A source
  that finds documents somebody forgot they had is a different product with a
  different ethics.
- **Not a sync client.** No tokens, no polling, no webhooks, no API versions.
  The owner exports; musubi reads (ADR-0007).
- **Not an indexer.** It writes documents. `tsumugi` indexes them, and musubi
  has no opinion about how.
- **Not a redactor.** It refuses on a credential; it does not rewrite around one.
  `mamori` redacts, and it is much better at it (ADR-0008).
- **Not an OCR or layout system.** The PDF converter reads a text layer. A
  scanned page is reported as unconvertible, not guessed at.
- **Not a summariser, a rewriter or a cleaner-up of prose.** No model runs in a
  sync (ADR-0003). Content invented at ingestion time is grounded content
  forever, and no check downstream can see it.
- **Not a deduplicator.** It marks redundancy and never resolves it (ADR-0011).

## 4. Architecture

The layering is `mamori`'s, `tsumugi`'s and `akashi`'s, unchanged, because it is
asserted by a test in all three and all three were right to.

```text
interfaces ──> application ──> domain
                    │              ▲
                    │              │
                    └──> ports <───┴── infrastructure
```

| Layer | May import |
|---|---|
| `domain/` | **stdlib only** — and never `tsumugi`, `kiseki` or `mamori` |
| `errors.py` | nothing |
| `ports/` | `domain`, `errors` |
| `application/` | `domain`, `ports`, `errors` |
| `infrastructure/` | `domain`, `ports`, `errors` |
| `config.py` | everything above |
| `interfaces/` | everything above |

Enforced twice: `tests/test_architecture.py` parses every module and asserts the
table, and `import-linter` asserts the direction plus the forbidden-import
contracts. A diagram that stops matching the code turns the build red rather
than quietly becoming fiction.

```text
src/musubi/
├── domain/
│   ├── span.py          # half-open ranges, and the arithmetic on them
│   ├── text.py          # normalization that keeps its offsets
│   ├── trace.py         # the tiling: segments, kinds, composition, coverage
│   ├── record.py        # the unit of sync, its key and its content hash
│   ├── removal.py       # a subtraction and the rule that made it
│   ├── cleansing.py     # the algorithm; rules are data
│   ├── frontmatter.py   # the metadata block a consumer reads
│   ├── manifest.py      # what a run did, as values
│   ├── redundancy.py    # marking, never resolving
│   └── hashing.py       # content_hash, run_id, over exactly the inputs
├── ports/
│   ├── source.py        # yields raw units out of an export
│   ├── converter.py     # (bytes, media type) -> (text, TraceMap)
│   ├── screener.py      # ADR-0008 — is there a credential in here
│   ├── emitter.py       # writes a consumer's contract
│   └── ledger.py        # what the last run saw, for incremental sync
├── application/
│   ├── plan.py          # the dry run (ADR-0012)
│   ├── sync.py          # the one use case
│   ├── verify.py        # re-derive a manifest from its own inputs
│   └── trace.py         # follow an offset back to the source
├── infrastructure/
│   ├── sources/         # filesystem, obsidian, notion_export, slack_export, maildir
│   ├── converters/      # markdown, plaintext, html, pdf_text
│   ├── rules/           # the vendored cleansing packs (ADR-0009)
│   ├── screeners/       # patterns + entropy, stdlib only
│   ├── emitters/        # tsumugi_folder, kiseki_records
│   ├── storage/         # the sync ledger, SQLite
│   └── adapters/
│       └── mamori.py    # optional; the only module that knows it exists
├── evaluation/          # the generated corpus, the metrics, the floors
└── interfaces/
    ├── cli/
    └── mcp/
```

Two notes on that tree.

`domain/trace.py` is the centre. Everything else is arranged so that the tiling
can be built, composed and checked: a source yields a unit, a converter produces
a tiling over it, the cleanser produces a second tiling over *that*, and the two
compose into one map from the artefact to the owner's file. Composition being an
operation on values in the domain — not a side effect of a pipeline — is what
makes it testable and what makes ADR-0003's reproducibility claim mean something.

`domain/cleansing.py` holds the algorithm and `infrastructure/rules/` holds the
rules it runs. That split is `mamori`'s ADR-0008, and it is what makes a new
source's quirks a data change.

## 5. The pipeline

Six stages. Every one is a pure function of its inputs.

1. **Open.** A source reads an export and yields raw units: bytes, a media type
   hint, and a `unit_key` derived by a rule the source declares (ADR-0006). No
   file hashing, no mtime, no zip metadata.

2. **Screen.** Every unit goes past the screener before anything is converted.
   A hit stops the run — nothing is promoted, including the units that already
   converted cleanly (ADR-0008). Screening first rather than last means the
   secret never reaches a temporary file.

3. **Convert.** Bytes to text *and a tiling*. A converter that cannot map its
   output does not emit it; the unit is reported unconvertible with a reason,
   and it appears in the manifest rather than in a log.

4. **Cleanse.** Rules fire against the converted text, producing a shorter string
   and a `RemovalRecord` per firing (ADR-0005). Each removal is a discontinuity
   in a second tiling, so offsets after it stay resolvable.

5. **Compose.** The two tilings compose into one `musubi.trace-map/1` from the
   artefact back to the source unit. Adjacent segments of the same kind and the
   same delta merge. Traceable coverage falls out of this stage as a number.

6. **Emit.** An emitter writes a consumer's contract: Markdown with front matter
   for `tsumugi`, records as JSON for `kiseki` (ADR-0010). It writes into a
   staging area; a run promotes atomically or not at all.

The manifest is assembled across all six and written last.

### Where the difficulty actually is

Stages 1 and 3. Stage 1 because every export format has a different idea of
identity and each one needs its own argument (ADR-0006). Stage 3 because a
tiling is a much stronger obligation than a string, and it is the obligation that
makes musubi different from everything else in this category.

Stages 2, 4, 5 and 6 are careful bookkeeping. That is not a complaint — the
bookkeeping *is* the product — but it is where the schedule should not be spent.

## 6. The documents

Two contracts (ADR-0002). Sketches, not schemas; the schemas are written with the
code that produces them.

### `musubi.sync-manifest/1`

```json
{
  "contract": "musubi.sync-manifest/1",
  "run_id": "sha256:7c1f...",
  "kind": "sync",
  "created_at": "2026-08-30T14:22:10+09:00",
  "musubi_version": "0.1.0",

  "sources": [
    {"source_id": "vault", "adapter": "obsidian@1", "root": "~/notes",
     "key_derivation": "path", "units": 412}
  ],
  "rulesets": [{"id": "core", "version": "2026.08", "rules": 148}],
  "converters": [{"name": "markdown@1", "units": 401}, {"name": "pdf_text@1", "units": 11}],
  "screener": {"name": "patterns+entropy@1", "measured_recall": "docs/measurements.md#screener"},

  "emitted": [
    {"artefact": "synced/design/gear.md",
     "source": {"source_id": "vault", "unit_key": "design/gear.md"},
     "content_hash": "sha256:9f2c...",
     "trace_map": "synced/design/gear.md.trace.json",
     "traceable_coverage": 1.0,
     "layer": "fact"}
  ],

  "removals": [
    {"rule": "tracking.utm", "kind": "tracking_parameter",
     "unit_key": "design/gear.md", "span": [1204, 1231],
     "removed_chars": 27, "removed_sha256": "sha256:be31..."}
  ],

  "skipped": [
    {"unit_key": "scans/contract.pdf", "reason": "no_text_layer",
     "rule": "pdf_text@1 requires an extractable text layer"}
  ],

  "redundant": [],

  "coverage": {
    "units_read": 412, "emitted": 401, "skipped": 11,
    "chars_emitted": 1840221, "chars_traceable": 1836004,
    "traceable_coverage": 0.9977
  },

  "limits": [
    "A traceable character means an offset resolves to the source. It does not mean the conversion read the page in the right order.",
    "The screener catches common credential shapes; its measured recall is not 100%.",
    "Removals are recorded by hash, not by value. Confirming one requires the source."
  ]
}
```

`limits` is in the document, not in the documentation, for `akashi`'s reason: the
artefact travels and the documentation does not.

`coverage` publishes the denominator. `emitted` alone would let a reader compute
a ratio against the wrong total, and they would.

### `musubi.trace-map/1`

```json
{
  "contract": "musubi.trace-map/1",
  "artefact": {"path": "synced/design/gear.md", "content_hash": "sha256:9f2c..."},
  "source": {"source_id": "vault", "unit_key": "design/gear.md",
             "content_hash": "sha256:41ab...", "media_type": "text/markdown"},
  "segments": [
    {"out": [0, 118], "kind": "synthetic", "why": "front_matter"},
    {"out": [118, 1204], "src": [0, 1086], "kind": "verbatim"},
    {"out": [1204, 1204], "kind": "removal", "rule": "tracking.utm", "src": [1086, 1113]},
    {"out": [1204, 4021], "src": [1113, 3930], "kind": "verbatim"}
  ]
}
```

The segments tile `[0, len(artefact))` exactly. A `removal` segment is
zero-length in the output and non-empty in the source, which is how a subtraction
stays visible in a map whose whole job is to be continuous.

## 7. The command line

```bash
musubi plan  ~/notes --as obsidian --into ./synced     # writes nothing (ADR-0012)
musubi plan  ~/notes --as obsidian --show-removals     # values, to the terminal only
musubi sync  ~/notes --as obsidian --into ./synced     # stages, then promotes
musubi trace ./synced/design/gear.md:1204-1231         # where did this come from
musubi verify ./synced/manifest.json                   # re-derive, compare run_id
musubi rules --list / --explain tracking.utm / --stale # the enforced policy
musubi eval --tier ci                                  # the floors
musubi doctor                                          # what is installed, what is not
```

`trace` is the command the whole design is for. Everything else is a pipeline
somebody else also has; `trace` is the thing that only works because of ADR-0004.

## 8. The seams

```text
[ musubi ]   exports and folders ➔ clean documents that can point back
     ↓
[ kiseki ]   personal context, as facts / measures / interpretations
     ↓
[ tsumugi ]  selection ➔ a ContextPackage: what was sent, what was withheld
     ↓
[ mamori ]   pseudonymization ➔ out to the model, and restoration on the way back
     ↓
[ akashi ]   ➔ which particulars of the answer are traceable, and which are floating
```

### With `tsumugi`

musubi writes a folder `tsumugi ingest` reads: Markdown with YAML front matter
carrying `title`, `producer`, `observed_at` and `layer`, plus a `.trace.json`
beside each file that `tsumugi` ignores entirely.

The interesting property is what this does to a citation. `tsumugi` anchors into
`synced/design/gear.md` at offset 1204; `musubi trace` resolves that to
`~/notes/design/gear.md` at byte 1086. The chain from a sentence in a model's
answer back to a byte in the owner's own file is complete for the first time, and
no component in it imports another.

musubi emits `fact` and `measure` and never `interpretation` (ADR-0010). It has
no model, so it has no reading to offer.

### With `kiseki`

musubi is a **producer** for `kiseki`'s record contracts, which is a role
`kiseki` documents precisely: PhotoRecord v1, ActivityRecord v1, NoteRecord v1,
each with a schema and a gate of ten questions a new source must answer before it
is added. musubi answers those ten questions, per source, in its own docs, and
the answers are reviewed as part of the PR that adds the emitter.

NoteRecord is the one that needs care. Its producer classifies a note and then
keeps only a category and up to eight labels — the text is deliberately
discarded, and `kiseki` requires a dry run first for exactly that reason.
Classification wants a model, and musubi has none (ADR-0003), so the split is:
musubi's rule-based classifier handles what rules can handle and marks the rest
`other`, and a model-assisted classification is a separate, explicitly invoked
step whose output musubi reads as an input. ADR-0012 makes the dry run mandatory
rather than advisory.

### With `mamori`

One optional adapter, in one file, for one thing: a better screener (ADR-0008).
musubi's built-in screener is patterns plus entropy and is roughly a 70%-recall
instrument by the public benchmarks; `mamori`'s detection pipeline is the
upgrade, and it is the only sibling musubi ever imports.

Note what the adapter is *not* for. musubi does not pseudonymize its output. A
corpus that has been through `mamori` is a corpus of placeholders, and
`tsumugi` + `akashi` already handle protection at the point where text leaves the
machine, which is where it belongs.

### With `akashi`

None, directly, and one property worth naming. `akashi` reports a contradicted
figure with an anchor into a document; if that document came from musubi, the
anchor now resolves through the conversion to the owner's original PDF. The
audit's strongest finding becomes something the owner can open and look at. That
is the whole point of this project, arriving at the far end of the chain.

## 9. The order it gets built in

Each milestone is shippable, is gated by the checks that exist when it ships, and
ends with something that can be demonstrated. One issue, one PR, squash merge,
close the issue after.

### v0.1 — the spine

*The question it answers: given a folder of notes, can musubi produce a clean
corpus in which every character knows where it came from?*

- `domain/`: `span`, `text` (offset-preserving normalization), `trace` (the
  tiling, composition, coverage), `record`, `removal`, `hashing`, `frontmatter`,
  `manifest` as values.
- `ports/`: `source`, `converter`, `screener`, `emitter`.
- The filesystem and Obsidian sources. The Markdown and plaintext converters —
  both nearly verbatim, which makes them the right place to get the tiling
  machinery right before a hard format arrives.
- The cleanser with a small starting ruleset, and the pattern+entropy screener.
- The `tsumugi` folder emitter, staging and atomic promotion.
- `musubi plan`, `musubi sync`, `musubi trace`.
- `tests/test_architecture.py`, the `import-linter` contracts switched on as
  their packages land, the zero-dependency CI job, `mypy --strict`.
- Property tests for the three invariants everything else rests on: **segments
  tile the artefact exactly**, **a traced offset round-trips to the source**, and
  **two runs over the same input are byte-identical**.

Deliberately **not** in v0.1: any format whose conversion is lossy. HTML and PDF
wait for v0.3, because getting the tiling right on a format where the answer is
obvious is the only way to know the machinery is right before using it where the
answer is not.

### v0.2 — the documents become contracts

- `musubi.sync-manifest/1` and `musubi.trace-map/1`, with
  `schemas/sync-manifest-1.json` and `schemas/trace-map-1.json` shipped in the
  wheel, plus the conformance suite.
- `run_id` over exactly the inputs, and the reproducibility property test.
- `musubi verify`.
- **The freeze condition:** each contract freezes once a second program has
  produced and consumed one — not on a date. `musubi trace` reading a map written
  by a different process is the likely second program for the trace map; for the
  manifest it is probably `verify`.

### v0.3 — the formats that are actually hard

- The Notion export source (page ids out of filenames, cross-link rewriting, the
  UUID scaffolding) and the Slack export source (per-day files, `users.json`
  resolution, thread structure, the `<@U…>` mentions).
- The HTML converter, with boilerplate removal expressed as a tiling — the
  removed navigation is a `removal` segment with a rule, not a gap.
- The PDF text-layer converter, with page-level source ranges, refusing anything
  with no text layer.
- The per-source rule packs, and the ten-question gate answered for each new
  source.

This is where traceable coverage stops being 1.0 by construction and starts being
a measurement.

### v0.4 — the corpus, and the floors

- The generated evaluation corpus: fixtures with known answers, built by a
  deterministic tool with no model and no seed, committed, and re-derivable with
  `--check-only` — `tsumugi`'s and `akashi`'s pattern, which both projects say
  earned its cost on the first run.
- `musubi eval`, and `docs/measurements.md` with the residual stated for every
  number.
- Floors in CI, set deliberately below the measured scores. **Floors, not
  targets** — a gate set at today's number makes every honest experiment a build
  failure, and tuning to reach a threshold is what `mamori`'s ADR-0023 records.

The numbers this milestone owes:

| Metric | Definition | Why it decides something |
|---|---|---|
| **Traceable coverage** | share of emitted characters in a `verbatim` or `transformed` segment, per converter, per corpus | ADR-0004 is right or it is not |
| **Trace map size** | map bytes per artefact byte | the cost of the guarantee |
| **Cleansing precision** | firings that removed something the corpus labels as noise | a rule that eats content is worse than no rule |
| **Screener recall** | labelled credentials found, against a public set | ADR-0008 claims ~70%; measure it |
| **Screener precision** | hits that were real, on a clean corpus | a false positive stops a run |
| **Re-read ratio** | cost of a no-change re-sync vs a cold sync | ADR-0006's actual affordability |

This is the milestone that decides whether the thesis is true. If traceable
coverage on real HTML and PDF is low, ADR-0004 is not wrong but the product is
narrower than planned, and the roadmap after this point gets rewritten from the
measurement rather than from the plan. `tsumugi`'s proposal 0002 exists because
that happened there; it is expected to happen here.

### v0.5 — `kiseki`'s records

- The NoteRecord emitter, with the mandatory dry run (ADR-0012) and the
  rule-based classifier.
- The ActivityRecord emitter, from the health exports people actually have.
- The PhotoRecord emitter — a second implementation of `kiseki-ingest`'s job,
  justified only if musubi's version adds the manifest and the refusal
  behaviour; if it does not, this is dropped and the ADR says why.
- The ten-question gate answered in `docs/` for each, reviewed as part of the PR.

### v0.6 — redundancy, the surfaces, and the seam

- Near-duplicate marking: MinHash over shingles with a fixed, recorded
  permutation set and LSH banding (ADR-0011), gated on a precision measurement
  before it is promised. Exact duplicates ship earlier, free, from ADR-0006.
- The MCP server, on the standard library, following `tsumugi`'s ADR-0012.
- The `mamori` screener adapter, and the seam test against the real detector.
- `musubi doctor`.

### After that, in rough order of appetite

The maildir source. Content-defined chunking for large single-file sources, if a
measurement ever shows one exists. A trace map that survives an edit to the
artefact, which is the request every user will eventually make and which needs
its own ADR. Incremental promotion, so a huge sync does not have to be atomic in
one step — with a very careful argument about ADR-0008, because partial
promotion is exactly what fail-closed forbids.

## 10. What would falsify this design

Written down now, while it is still cheap to be wrong.

- **Traceable coverage is low where it matters.** If PDF and HTML land at 60%,
  the guarantee covers the easy formats and the hard ones are exactly the ones
  users have. Measured in v0.4; the honest response is to narrow what musubi
  claims to handle, not to loosen what traceable means.
- **The trace map is too big.** If a map routinely exceeds its document, the
  guarantee costs more storage than the corpus. Measured in v0.4; the fix is
  converter-side, and if there is no fix, the map becomes optional and the
  project is much less interesting.
- **The record key is not stable in practice.** ADR-0006 assumes exports carry
  identity that survives re-export. If Notion or Slack change enough between
  exports that keys drift, every re-sync looks like a full rewrite and
  incremental sync does not exist. Measured against two real exports of the same
  workspace taken weeks apart — which is a fixture that has to be *collected*,
  not generated, and is the one piece of evaluation data musubi cannot make for
  itself.
- **Fail-closed is unusable.** If real corpora contain enough high-entropy
  strings that every run stops, `--allow` becomes reflexive and the gate protects
  nothing. Measured as screener precision in v0.4. If it is bad, the fix is the
  ruleset, not the policy.
- **Nobody exports.** The whole product assumes the owner will produce an export
  (ADR-0007). If that friction is fatal, the answer is not a socket; it is that
  musubi is a library for the people who already have the folder, and the market
  is smaller than hoped.

Each of these has a measurement attached and a milestone it is measured in. A
design whose falsification conditions are not written down is a design that will
be defended instead of tested.
