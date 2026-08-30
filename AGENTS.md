# AGENTS.md

Context for AI assistants (and future humans) working on musubi. Read this whole
file before proposing or writing any change.

This file is current state and current rules. It is not a history: why a thing is
the way it is lives in `docs/adr/`, and what might happen next lives in
`docs/proposals/`. `docs/README.md` explains that separation and why it matters.
**A statement here that disagrees with the code is a defect.**

## What musubi is

A local-first Python library that turns the exports and folders somebody already
has — an Obsidian vault, a Notion zip, a Slack archive, a maildir, a shelf of
PDFs — into clean, normalized documents a language-model pipeline can use,
**without losing the correspondence back to the original bytes.** Zero runtime
dependencies. No network anywhere, including in adapters. No model, ever, inside
a sync.

The constitution, to be enforced by construction rather than by promise:

- **A conversion carries a map back to its source.** Every converter returns text
  *and* a tiling of segments over the original. A converter that cannot map its
  output does not emit it (ADR-0004). This is the decision the rest is arranged
  around.
- **Every subtraction is recorded, with the rule that made it.** Cleansing
  deletes real bytes, and a wrong rule is invisible in the output. The record
  carries the rule, the span and a hash — never the value (ADR-0005).
- **Same input bytes, same output bytes.** No model, no wall clock in an id, no
  unordered iteration reaching an output (ADR-0003).
- **The unit of sync is the record, not the file.** Identity is
  `(source_id, unit_key)`; change is `content_hash`. A re-export that changed
  nothing produces an empty diff (ADR-0006).
- **musubi reads exports, never services.** No sockets, no tokens, no API to
  chase. A folder the owner named — never the home directory, never every file
  on the machine (ADR-0007).
- **A credential stops the run, and musubi does not redact it.** Nothing is
  promoted. Refusing needs only that a secret exists; redacting needs to be right
  about where it ends, and `mamori` is the library for that (ADR-0008).
- **Rules are data, and each names its evidence.** A rule with no stated reason
  cannot be reviewed by anyone who was not there (ADR-0009).
- **One output family, and the consumer adapts.** musubi publishes documents,
  a sync manifest and a trace map, and ships no consumer-specific emitter
  (ADR-0013). No module under `src/` may name `tsumugi` or `kiseki` (ADR-0010).
- **Redundancy is marked, never resolved** (ADR-0011). **A dry run comes first**
  (ADR-0012).
- **musubi emits `fact` and `measure`, never `interpretation`.** It has no model,
  so it has no reading to offer, and an interpretation with no author is
  laundering.

## Architecture map

There is no `docs/architecture.md` yet, on purpose: nothing is built, and a
current-state document written before the code is fiction. The planned shape is
`docs/proposals/0001-the-design.md` §4.

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

This table is executable: `tests/test_architecture.py` parses every module and
asserts it, and `import-linter` asserts the direction plus the forbidden-import
contracts. A diagram that stops matching the code turns the build red rather than
quietly becoming fiction.

Three `.importlinter` contracts are **parked** — commented out, because
import-linter refuses a contract naming a package that does not exist yet.
`tests/test_layering_config.py` turns the build red the moment one of them could
be switched on and has not been.

## Conventions

Taken from `kiseki`, `mamori`, `tsumugi` and `akashi`, which paid for them.

- **Everything in the repository is English.** Conversation language may differ;
  committed text may not.
- TDD. One issue, one PR, squash merge, close the issue after.
- **All tests must pass before any commit.** One failure means stop and
  investigate, not proceed. A red commit uses `--no-verify`; a green commit never
  does.
- Test file names are unique across the repository — tests are not a package and
  duplicate basenames break collection.
- Any test that invokes the CLI isolates itself: chdir to `tmp_path` and strip
  `MUSUBI_*`. **A CLI test that writes into a developer's real folder is worse
  here than anywhere else in this family** — musubi's job is to write folders,
  and its test subject is somebody's notes.
- Checks before every green commit: `uv run pytest -q`, `uv run mypy src`,
  `uv run lint-imports`, `uv run ruff check --fix .`, `uv run ruff format .`,
  `uv run pre-commit run --all-files`. If pre-commit rewrites anything,
  `git add` and run it again — a commit whose hooks failed did not happen.
- Checkpoints: after `git commit`, confirm the `[branch hash]` line; after
  `gh pr merge`, confirm `Squashed and merged`; after pulling main, run pytest
  once more.
- Windows: set `PYTHONUTF8=1`. This project reads files written on other people's
  machines, and half its bugs are encodings.
- Writing a repository file from a Python script on Windows: pass
  `newline="\n"`. `Path.write_text` translates, `.gitattributes` says the
  repository is LF, and the pre-commit hook then rewrites the file underneath
  the commit. It is caught every time and it wastes a cycle every time.
- Read-only dumps for an assistant go **outside** the working tree.

## Rules particular to this project

- **Never write an architecture document for code that does not exist.** ADRs
  before code are legitimate; a current-state document before code is fiction.
- **A number in a document is measured or it is not written.** If a claim needs a
  measurement, run it, record the script and the environment, and cite it.
- **State the residual.** Every measurement ships with what it does *not* say.
  The screener's recall names the benchmark it was measured on; traceable
  coverage names the corpus and states that a traceable offset is not a claim
  that the page was read in the right order.
- **Every discarding path carries its reason to the end.** A filter returns a
  shorter list *and* an account. This is invasive to retrofit, so it is done from
  the first filter.
- **Ordering discipline.** No unordered iteration reaching an output, no partial
  sort keys, no wall clock in an id. A sync run twice must be byte-identical, and
  a property test asserts it.
- **Never construct a fixture by hand-writing offsets.** Compute them. `mamori`'s
  dataset convention exists because a hand-written offset that is wrong makes a
  correct implementation fail, and the debugging goes in entirely the wrong
  direction.
- **A new source is not merged until `kiseki`'s ten questions are answered for
  it** (`kiseki` `docs/records.md`), in `docs/sources.md`, in the same PR. The
  third question — what could this reveal that the owner would not choose to
  reveal — is the one that blocks.
- **Anything that changes conversion output is gated on `musubi eval`** once it
  exists. Floors, not targets: a gate set at today's number makes every honest
  experiment a build failure.
- Test fixtures that stand in for real exports are **generated**, deterministic
  and committed. The one thing that cannot be generated is two real exports of
  the same workspace taken weeks apart, which is what ADR-0006's stability claim
  needs; it has to be collected.

## Current state

- Version `0.1.0.dev0`. **v0.1 is in progress**, one issue at a time against the
  milestone. The design and seventeen ADRs are in `docs/`; nothing is released
  and there is no public API to speak of yet.
- **License: Apache-2.0. Python: 3.12+. Runtime dependencies: 0**, checked in CI
  by installing the wheel with no extras and asserting nothing came along.
- **Built:** `domain/` — `span`, `text`, `trace`, `hashing`, `record`, `removal`,
  `cleansing`, `screening`; `ports/screener.py`; `infrastructure/rules/` and
  `infrastructure/screeners/`. A `Span`
  is a half-open range of integer positions and deliberately does not decide
  what a position indexes — the holder says, and the trace map records it. `text.rewrite()` is
  the primitive everything else is made of: deleting is replacing with the
  empty string, inserting is replacing an empty span, and the account of where
  every output character came from falls out of the one code path rather than
  being maintained beside it. Its `Piece`s tile **both** sides, checked on
  construction and by property tests.
- `domain/trace.py` is ADR-0004 in code. A `TraceMap` tiles the artefact
  exactly, and `followed_by` composes two stages into one map from the artefact
  back to the source. Composition never claims the stronger of two kinds, and
  splits a run where the earlier stage changed kind rather than degrading the
  whole of it. `merged()` collapses **only** verbatim runs: merging two
  transformed runs would answer a query with the union of what they replaced,
  which is a worse answer than either gave alone.
- The domain raises built-in exceptions. `errors.TraceError` exists for the
  layer that has a file path to put in the message; the domain has no file.
- `domain/hashing.py`: every hash names its algorithm (`sha256:` + 64 lowercase
  hex), and structured values hash over an RFC 8785 canonical form — for the
  clauses musubi's inputs reach. Floats are **refused**, which removes the one
  clause of the specification that is hard to get exactly right and which
  nothing determining a run needs.
- `domain/cleansing.py` + `domain/removal.py`: a rule matches a **parsed
  parameter name** by `exact` or `prefix`, and there is no regular expression
  anywhere in the cleanser (ADR-0016). Python's `re` backtracks and has no
  timeout, and rules are data users may edit running over documents nobody
  vetted, unattended — restricting the language removes the failure class
  instead of mitigating it. URL finding is a linear scan for the same reason.
  One `Replacement` per query and one `RemovalRecord` per parameter: a query cut
  by three rules is one discontinuity and three things somebody may appeal.
- `domain/screening.py` + `infrastructure/screeners/`: **the default tier is
  signatures, and entropy is opt-in** (ADR-0017). A signature is a prefix, an
  alphabet and a minimum length — no regex, same reason as ADR-0016. Entropy-only
  detection is 21.1% precision on CredData, and under ADR-0008's stop-the-run
  policy four false stops in five makes `--allow` reflexive within a week. The
  entropy tier prints its own numbers where it is switched on.
- **No recall number is claimed for the default tier.** It is unmeasured, and
  this project does not write unmeasured numbers. v0.4 owes it.
- `infrastructure/rules/core.py` is derived from ClearURLs' `globalRules`, with
  the provenance and the two entries deliberately **not** adopted written down
  in the module. Every rule states `evidence` and `since`.
- `domain/record.py`: identity is `(source_id, unit_key)` and change is
  `content_hash`. `unit_key()` takes *parts*, not a path string, normalizes each
  to NFC and refuses `.`, `..`, an embedded separator and an empty part. Keys are
  normalized; **content never is**. `compare()` is the diff, ordered by key, and
  it stops the run on a duplicate key or a mixed source rather than guessing.
- `decode()` reads UTF-8 (with or without a BOM) and UTF-16 that announces
  itself, and **refuses everything else rather than detecting**. A guessed
  legacy encoding writes mojibake into a corpus bound for a model and looks
  exactly like a successful read.
- Four `import-linter` contracts are live; two remain parked. `domain-no-io`
  went live with the first domain module, which is what
  `tests/test_layering_config.py` is for — it turned the build red on the
  commit that made it resolvable.
- 100% line coverage, and it is expected to stay there while the domain is the
  whole of the code. It will not survive contact with the CLI, and chasing it
  there would be a worse use of the time than the tests that matter.
- Planned, in order: v0.1 the spine (`plan`, `sync`, `trace` over
  a vault), v0.2 the contracts and `verify`, v0.3 Notion / Slack / HTML / PDF,
  v0.4 the corpus and the measured floors, v0.5 the folder `kiseki-notes` can
  read, v0.6 redundancy and the surfaces.
  `docs/proposals/0001-the-design.md` §9 is the detail.
- No schema exists yet. `pyproject.toml` carries the `force-include` block for
  `schemas/` **commented out**, because hatchling refuses to build against a
  force-include that resolves to nothing; `tests/test_documentation.py` turns the
  build red the moment a schema exists without it.
- Working notes, review history and experiments are kept **outside this
  repository** and are not published.
