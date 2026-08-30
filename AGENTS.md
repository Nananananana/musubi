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
  pulling main, run pytest once more.
- **After a merge, read the outcome and not the report.** `Squashed and merged`
  says the merge command succeeded, which is a different claim from *the change
  is on `main`* — #41 merged cleanly into a branch that had already been merged,
  reported success, and left `main` without a line of it. Every merged PR in the
  repository reports `MERGED`; only some of them are on `main`:

      m=$(gh pr view <n> --json mergeCommit --jq .mergeCommit.oid)
      git merge-base --is-ancestor "$m" main && echo on main || echo NOT on main

  Measured: #37 and #39 pass, #41 fails, all three reporting `MERGED`. Then read
  one file the PR changed **out of `main` itself** — `git show main:<path>` —
  because ancestry says a commit arrived and not that it arrived intact.
- **Take a PR's commits from `refs/pull/<n>/head`, never from its branch.** The
  pull ref is pinned to `headRefOid`, so it survives the branch being deleted,
  force-pushed, or pushed to *after* the merge — and a branch pushed to after
  merging gives `git diff main <branch>` a diff against something that was never
  merged, which looks exactly like verification. It exists for closed and
  rejected PRs too, which makes it the way to read what a PR proposed after its
  branch is gone. Verified here: #41's `refs/pull/41/head` is `97c055f` and its
  `mergeCommit` is `a824e5c` — two different commits, and reading the wrong one
  answers a question nobody asked.
- **A backslash escape does not survive a bash heredoc here.** Writing a Python
  file with `python - <<'PY'` turns `\\n` inside the script into a real
  newline, so the generated source has an unterminated string literal. It is
  caught immediately by ruff, and it cost three cycles in one session anyway,
  because the fix is mechanical and remembering is not: **build the escape from
  a placeholder** — write `@NL@` in the text and finish with
  `.replace("@NL@", chr(92) + "n")` — or use the Write tool, which passes
  the bytes through untouched. The same applies to backticks.
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

- Version `0.1.0.dev0`. **v0.1 is done**: `plan`, `sync` and `trace` over a
  vault, both contracts with schemas, and the invariants asserted rather than
  only enumerated. Twenty-one ADRs. Nothing is released and the public API is not
  stable. **v0.2 is under way** — `docs/proposals/0001-the-design.md` §9, with
  `musubi verify` built. **The freeze is not**, and `verify` does not advance
  it: the roadmap guesses `verify` is the second program for
  `musubi.sync-manifest/1`, and it is not, for the reason already accepted for
  `tests/test_invariants.py` — the producer checking itself, in the same
  package. A contract freezes when something else needed it.
- **License: Apache-2.0. Python: 3.12+. Runtime dependencies: 0**, checked in CI
  by installing the wheel with no extras and asserting nothing came along.
- **Built:** `domain/` — `span`, `text`, `trace`, `hashing`, `record`, `removal`,
  `cleansing`, `screening`, `frontmatter`, `manifest`; `ports/` (`screener`,
  `source`, `converter`, `emitter`); `infrastructure/` (`rules`, `screeners`,
  `sources`, `converters`, `emitters`); `application/pipeline.py`;
  `application/sync.py`, `application/trace.py` and `application/verify.py`;
  `interfaces/cli` with **`musubi plan`**, **`musubi sync`**, **`musubi trace`**
  and **`musubi verify`**. A `Span`
  is a half-open range of integer positions and deliberately does not decide
  what a position indexes — the holder says, and the trace map records it. `text.rewrite()` is
  the primitive everything else is made of: deleting is replacing with the
  empty string, inserting is replacing an empty span, and the account of where
  every output character came from falls out of the one code path rather than
  being maintained beside it. Its `Piece`s tile **both** sides, checked on
  construction and by property tests.
- **`verify` checks a folder, not a run**, which is the only thing it is for.
  Every other check in this project runs while the corpus is being written, so
  the files have had no opportunity to change; `verify` reads a corpus that may
  have been copied, synced, restored from a backup or opened by an editor since.
  Hence the one check nothing else can make: each document still hashes to what
  the manifest recorded. **Its checks are a second implementation on purpose** —
  `tests/test_invariants.py` keeps its own arithmetic rather than asserting on
  `verify`'s output, because a single mistake in `verify` would otherwise make
  both agree. **No `jsonschema` at runtime** (ADR-0001): shape is for consumers
  who have it, and `verify` checks what a schema cannot say.
- **Where a corpus keeps its files is the reader's business.** `verify` asks
  `CorpusReader.key_of()` rather than stripping `documents/` itself — an
  application that knew the layout would be a second place that knows it, and
  the two would drift. A path that is not where the layout says is reported as
  a fault rather than raised past the checker.
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
- `infrastructure/sources/`: a source is asked twice — `discover()` opens
  nothing, `read(found)` opens one thing. The split is `kiseki-notes`' and it is
  what lets `plan` account for what will be skipped before a private file has
  been read. Pointing at the home directory or a filesystem root is **refused**
  (ADR-0007). A file symlink is followed only if it resolves inside the root; a
  directory symlink is never followed, because a cycle in an unattended walk is
  a hang.
- `ports/converter.py` + `infrastructure/converters/`: bytes in, text **and a
  map** out, or an `Unconvertible` value saying why not. There is no third
  option, because a converter that produced text without a map would put back
  the hole this project exists to close. `Unconvertible` is a value rather than
  an exception: it is not an error, and a reason that travels as a value cannot
  be swallowed by a bare `except`.
- **A trace map's source side is in characters, never bytes** (ADR-0018). This
  was implemented in bytes first and a test caught why it cannot be:
  `source_span_of` shifts an offset by a constant inside a verbatim run, and
  that constant counts characters. The decoding travels beside the map instead,
  and the command that opens the file converts. Compose in characters; there is
  no re-measure step to get the order of wrong.
- **Separating the trees makes the correct invocation available; it does not
  make an incorrect one safe.** `tsumugi ingest <destination>` reads the trace
  maps and the manifest as documents, reports `0 skipped, 0 failed`, and leaves
  the corpus holding a per-character index of itself. musubi cannot stop that
  and does not claim to — it says which folder to read, at the end of the sync
  and in `docs/contracts.md`. Not by asking a sibling to change its skip list,
  and not by writing an ignore file into somebody's output folder.
- **A claim in a comment is a claim.** The CI job's comment said "the README
  promises `pip install musubi`". The README promised no such thing, and could
  not: on PyPI that name belongs to an unrelated DNSBL checker. A comment that
  justifies a check by citing a promise nobody made is the same defect class as
  a README describing a command that does not exist.
- **The destination is three folders**: `documents/` (what a consumer ingests),
  `traces/`, `manifest.json`. Not sidecars beside the documents —
  `tsumugi`'s corpus walk does not skip `.musubi` and its parser registry claims
  `.json`, so a sidecar beside a document *is* a document, and a corpus would
  end up holding a per-character index of itself.
- Front matter carries `layer` and `producer` and **nothing else**. No `title`:
  `tsumugi` takes a better one from the first heading. No `observed_at`: musubi
  does not know when a note was written, and an mtime there would make a
  re-sync that changed nothing rewrite the corpus. `producer` is
  `musubi.sync/1` — a contract name, not a version, or every release would
  rewrite every artefact.
- A key the owner already stated is left alone; `tsumugi`'s parser uses
  `setdefault`, so writing a second would be musubi arguing with a document
  about itself.
- Staging is what ADR-0008 hangs on. **What is atomic is the decision**, not the
  set: one `os.replace` per file, no half-written document ever readable, and no
  claim that a reader sees the whole corpus appear at once — that would need a
  directory swap, which would mean rewriting every unchanged artefact on every
  run.
- **`trace` is the command the design is for**, and the layer ADR-0018 deferred
  to: the map is in characters, and the byte offset is computed here because
  here is where the encoding, the byte-order mark and the file all are. It also
  checks the source's hash — a file that has moved on means the offsets are
  about a document that no longer exists, and saying nothing would point a
  reader confidently at the wrong place.
- A range that contains a **removal** is told so. A removal occupies no output,
  so it overlaps nothing and a span union covers it silently — `_bears_on` in
  `application/trace.py` is deliberately wider than the arithmetic
  `source_span_of` uses, which is ADR-0005 applied to a query.
- **Publishing a contract means the ADR, the schema and the emitter in one
  commit** — `mamori`'s rule, and musubi is a worked example of breaking it:
  ADR-0002 named two contracts in the first commit and the schemas arrived
  sixteen commits later, which is why #24 had to be filed. Half a contract is
  either "consumable-looking but not consumable" or "a published reading that
  disagrees with the implementation".
- **`tests/test_invariants.py` is the executable form of `docs/contracts.md`'s
  "What these schemas cannot say".** Not a reinforcement of it: an enumeration
  nobody runs hands a consumer "written down but never checked". The tests are
  named for the numbered entries, and a guard fails if the list grows an entry
  nothing runs. Everything there is asserted against a **real sync** of a
  generated vault, never against a document a test assembled.
- **The console's encoding never reaches a document, and never fails a run**
  (ADR-0020). `--json` writes UTF-8 bytes to `sys.stdout.buffer`; the report
  streams are reconfigured with `errors="replace"` so a character a terminal
  cannot show costs a glyph rather than the report. The exit code reports the
  run, not the rendering.
- **Do not patch `sys.stdout` in a fixture.** pytest suspends its capture for
  fixture setup and resumes it for the call phase, reinstating its own object —
  so the patch is silently undone, the test passes under `-s` and fails without
  it, and what is being measured is pytest. `tests/test_console_encoding.py`
  patches inside the test body.
- **Every gate in CI has been seen red** (2026-08-30, on a throwaway
  `proving-the-gates` branch dispatched with `workflow_dispatch`, never
  merged). Nine jobs, six distinct checks, each broken on purpose and watched
  failing at its own step: an unused import for Ruff; a return not matching its
  annotation for Types; `domain` importing `infrastructure` for Layering; a
  false assertion for Test, across all six matrix jobs; `force-include`
  commented out for the wheel; `dependencies = ["idna"]` for the dependency
  count. Before that day CI had 35 successes and **no failure ever** — the
  gates were all working and nothing had shown that they were. **Ruff, Types
  and Layering are sequential inside one job, so each masks the next**: proving
  all three takes three runs, and the later breakages must survive the checks
  ahead of them — the type error is invisible to ruff, and the layering
  violation is import-sorted and typed so Ruff and Types both pass and Layering
  is reached at all. An exit code is evidence only once something has been
  shown that makes it non-zero.
- **`gh` resolves the repository from the working directory, and an empty
  result is not an answer.** `gh run list --branch X` returned nothing with
  exit 0 while the shell had reset to a sibling checkout; empty output reads
  exactly like "no such run". What exposed it was `gh workflow run`, which
  failed loudly and named the repository it was asking. **Pass
  `-R Nananananana/musubi` explicitly, and treat an empty result as unproven
  rather than as a negative answer.**
- **A Hypothesis counterexample is not kept anywhere.** The example database is
  keyed by the test function, so editing the test — including adding a message
  to an assertion so you can see the failing input — changes the key and the
  stored example is silently skipped. It is also gitignored, so it never leaves
  the checkout: measured at v0.1, nine test files here used Hypothesis and the
  suite held **not one `@example`**, meaning no counterexample this repository
  had ever produced had reached CI or a second machine. Same family as the entry above
  and nastier — there the test measured the wrong thing, here it measures the
  right thing and is handed nothing to measure, with nothing broken either
  time. **When a property test hands you a counterexample, pin it as an
  `@example` in the commit that fixes it.** The database will not carry it.
- **The previous manifest is the ledger.** A sync withdraws an artefact whose
  unit is no longer in the source, by reading `<destination>/manifest.json` —
  there is no separate store, because a corpus that already says what is in it
  does not need one, and a ledger that can disagree with the corpus is a second
  source of truth to keep in step. musubi deletes what it *recorded writing* and
  never what it merely found, so a folder somebody put something else in
  survives a sync intact.
- Withdrawal happens **after** promotion. Deleting first and failing to promote
  would leave the corpus missing documents that nothing replaced.
- Both commands take their options from one `_shared()` function. A flag that
  exists on the dry run and not on the real one is the one way the shared
  pipeline cannot stop a plan from ceasing to predict a sync.
- **One pipeline, two entry points.** `plan` and `sync` are `run(..., write=)`
  over the same module. Two implementations of one walk is exactly how a dry run
  stops predicting the real one, and a test asserts the run ids match.
- **Screening is stage two, before conversion.** A secret never reaches a file
  musubi wrote, so a run that stops has nothing on disk to clean up. It also
  means a secret in a file musubi cannot *convert* is still caught, which is why
  the screener reads with `errors="replace"`.
- `run_id` excludes `created_at` and the source's root path. An id embedding an
  absolute path is an id nobody else can re-derive.
- **argparse expands `%` in help strings.** The entropy tier's own number
  contains two, so it is escaped at that boundary and nowhere else.
- Markdown and plaintext are the **same** conversion, and saying so beats
  inventing a difference. Wikilinks, `%%comments%%` and reference links are all
  rewrites of somebody's writing and each needs its own argument.
- **Coverage is 100% except the three symlink branches**, which need a
  privilege Windows does not grant by default. Those tests skip by *capability*
  rather than by platform — they run on Linux and macOS CI, and on a Windows
  machine with developer mode on. Do not "fix" the gap by deleting them.
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
- **Both contracts have schemas**, in `schemas/`, shipped inside the wheel and
  checked there by a CI job — `force-include` does not apply to an editable
  install, so nothing a developer runs locally would notice if the block were
  deleted. `docs/contracts.md` is the page a consumer reads.
- **Validate against real output, never against a document a test assembled.**
  `tsumugi` shipped a frozen contract and a reference producer and had never
  once validated its own real output against its own schema; the first run
  against genuine output found a real bug that had made every package built
  through the library API non-conformant. `test_contract_conformance.py` builds
  a corpus with the real emitter and validates what lands on disk, and runs the
  real command and validates what it prints.
- **A schema handed over as "the contract" gets read as the whole of it, and it
  is not.** JSON Schema 2020-12 cannot compare two properties of one object, so
  `end >= start` is beyond it — and the invariant the trace map exists for, that
  the segments cover every character exactly once, is far beyond it.
  `docs/contracts.md` enumerates what is not checked, where a consumer reads it.
  The property tests are the executable form of that list, not a later
  reinforcement of it.
- **A record inherits the classification of what it describes** (ADR-0019). The
  whole destination is one secret; `traces/` is not the safe half, and a finding
  in the manifest carries no offset and no length.
- Working notes, review history and experiments are kept **outside this
  repository** and are not published.
