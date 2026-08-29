# 3. A sync is reproducible, and no model runs inside one

**Status:** accepted

## Context

Ingestion is the layer everything downstream stands on. `tsumugi` indexes what
musubi wrote; `akashi` audits answers grounded in what musubi wrote; `kiseki`
reads records musubi produced. If the same input folder can produce two different
corpora, every guarantee above it is conditional on which day the sync ran, and
none of them say so.

The tempting non-determinism is a model. "Use an LLM to clean up the extracted
text" is default advice in 2026, and it is the single most damaging thing that
could be put in this position. It would rewrite the owner's sentences, produce a
different corpus every quarter, and write invented content into documents that
`akashi` would then *correctly* report as grounded — because it would be in the
sources, having been put there by the ingestion layer. A fabrication laundered
into the corpus is undetectable by every check downstream, because every check
downstream is defined against the corpus.

The subtler non-determinism is ordering. A directory walk in filesystem order, a
set iterated, a dict keyed by something unsorted, a wall clock in an artefact:
each makes two runs differ in ways nobody notices until a diff is enormous for no
reason.

## Decision

**Same input bytes, same output bytes.** Byte for byte, across runs, machines and
operating systems.

- **No model anywhere in a sync.** Not for extraction, not for cleaning, not for
  classification. Where a decision genuinely needs one — classifying a note for
  `kiseki`'s NoteRecord is the known case — the model runs in a separate,
  explicitly invoked step whose output musubi reads as an input, and the manifest
  records that it did.
- **Total ordering everywhere.** Sources are walked in sorted order, records are
  emitted in a defined order, and every iteration that reaches an output is over
  a sequence rather than a set or a mapping.
- **No wall clock in an artefact or in a `run_id`.** The run's timestamp appears
  in the manifest as metadata and is excluded from the id, so two runs over the
  same input share an id and the diff between their artefacts is empty.
- **No absolute path in a derived value.** An id that embeds one makes the corpus
  machine-specific, and a corpus that cannot be rebuilt on another machine cannot
  be checked by anyone but its author.

A property test runs a sync twice over the same fixture and asserts the outputs
and the ids are identical.

## Consequences

`musubi verify` becomes possible: hand it a manifest, re-derive the run from the
inputs the manifest names, and report whether the `run_id` matches. That is the
difference between a log and a receipt.

It also constrains the roadmap. Near-duplicate detection (ADR-0011) must be
deterministic, which rules out sampled MinHash with a random seed and requires a
fixed, recorded permutation set. Anything that wants to adapt has to adapt as a
function of its input, never of its history.

## What it costs

The cleaning musubi can do is bounded by what a rule can express. A model would
produce nicer Markdown from a badly structured HTML page; musubi produces the
mechanical version and says what share of it is traceable.

Determinism also forbids the obvious optimisation of skipping work on mtime
alone, because mtime is not a function of content. ADR-0006 pays for that with
content hashing, and the cost of a re-read becomes a number that gets measured
rather than assumed.
