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
- **Write the consumers' contracts, import neither consumer.** No module under
  `src/` may name `tsumugi` or `kiseki` (ADR-0010).
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

- Version `0.1.0.dev0`. **Nothing is built.** The repository holds the design,
  twelve ADRs, and the tooling that will enforce them.
- **License: Apache-2.0. Python: 3.12+. Runtime dependencies: 0**, checked in CI
  by installing the wheel with no extras and asserting nothing came along.
- `src/musubi/` holds `__init__.py`, `errors.py` and `py.typed`. Every other
  layer is named in the layer table and in `.importlinter` before it exists, so
  that the first module to appear in one is already governed.
- Built: nothing. Planned, in order: v0.1 the spine (`plan`, `sync`, `trace` over
  a vault), v0.2 the contracts and `verify`, v0.3 Notion / Slack / HTML / PDF,
  v0.4 the corpus and the measured floors, v0.5 `kiseki`'s records, v0.6
  redundancy and the surfaces. `docs/proposals/0001-the-design.md` §9 is the
  detail.
- No schema exists yet. `pyproject.toml` carries the `force-include` block for
  `schemas/` **commented out**, because hatchling refuses to build against a
  force-include that resolves to nothing; `tests/test_documentation.py` turns the
  build red the moment a schema exists without it.
- Working notes, review history and experiments are kept **outside this
  repository** and are not published.
