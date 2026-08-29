# 1. The domain layer imports only the standard library

**Status:** accepted

Borrowed, with thanks, from `mamori` (ADR-0001), `kiseki` (ADR-0003) and
`tsumugi` (ADR-0001). Each of them paid for it; the reason it applies here is its
own.

## Context

musubi is pointed at a folder. Not a document, not a database export — a folder,
and it is the folder holding everything its owner has ever written: the vault,
the mailbox, the Slack archive, the notes about other people, the draft of the
resignation letter, the scan somebody filed once and forgot.

Every runtime dependency is a third party with unsupervised read access to that
folder. Not "could theoretically" — it runs inside the process that opens the
files, on every sync, unattended, for years. And the 2026 ingestion libraries
that would save the most work here are precisely the ones with the largest
transitive trees: a document converter arrives with an image stack, a model
runtime and a telemetry client, and the telemetry client is a joke that writes
itself given what this library is for.

There is a second reason, and it outlasts the first. musubi's central claim
(ADR-0004) is that a conversion can carry a map back to its source. No existing
converter returns offsets, so no existing converter can implement the claim
anyway. The dependency would buy text musubi cannot use.

## Decision

**`domain/` imports the standard library and nothing else, and the package as a
whole declares zero runtime dependencies.**

The domain is handed strings and bytes and hands back records, traces and
manifests. It does not open a file, it does not know what a path is, and it does
not know that Notion exists.

Enforced three ways:

- `tests/test_architecture.py` parses every module under `src/musubi/` and
  asserts nothing in the domain imports a name outside
  `sys.stdlib_module_names`.
- `import-linter` asserts the direction between layers, and that the domain
  touches no I/O module at all.
- A CI job installs the built wheel into a clean environment and asserts the
  installed distribution count is one.

Optional extras may exist for adapters — ADR-0008's screener is the first
candidate — and are never required to sync anything.

## Consequences

Format support is written here rather than imported. A Markdown reader, an HTML
reader, a PDF text-layer reader, a zip walk: all hand-written, and all
deliberately incomplete in the way `tsumugi`'s Markdown parser is deliberately
incomplete. Being wrong about a nested list produces a worse *section*; it cannot
produce a wrong *offset*.

That is the trade, and it is only acceptable because of ADR-0004. A converter
that reports spans over the original can be shipped incomplete, because its
errors are visible and bounded. A converter that emits free-floating Markdown
cannot, because its errors are invisible.

## What it costs

PDF is the honest one. A hand-written text-layer extractor will handle a
straightforward text PDF and will not handle a scanned page, a two-column
academic paper with ligature substitutions, or a form. `docling` would handle all
three and score better than anything written here.

The answer is not that musubi will match it. The answer is that musubi reports,
per document, what share of its output is traceable, and refuses to emit what it
cannot map (ADR-0004) — so a PDF corpus musubi handles badly is *visibly* handled
badly rather than silently converted into plausible noise. OCR and layout models
are a real need, and they belong to a program the owner runs before musubi, whose
output musubi then reads as it reads any other source (ADR-0007).
