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
- Checks before every green commit: `uv run pytest -q`, `uv run mypy`,
  `uv run lint-imports`, `uv run ruff check --fix .`, `uv run ruff format .`,
  `uv run pre-commit run --all-files`. If pre-commit rewrites anything,
  `git add` and run it again — a commit whose hooks failed did not happen.
- Checkpoints: after `git commit`, confirm the `[branch hash]` line; after
  pulling main, run pytest once more.
- **Tell the `release` session when a pull request opens**: repo, number,
  title, whether `base=main`, and the CI state. No reply expected; it does not
  gate anything and does not merge. The reason is not process for its own sake —
  #64 went from open to merged in a minute, so nobody read it before the owner
  decided, and what went unsaid was that its headline number is a **fall**
  (traceable coverage 26/76) that is the milestone working as designed rather
  than a regression. A number that looks like a step backwards needs somebody to
  say it is not, and that somebody has to have read it first.
- **`uv run mypy` with no argument, never `mypy src`.** The scope lives in
  `pyproject.toml` and covers `src/` *and* `tests/`; naming a path on the command
  line narrows it back and the run still says `Success`. From `mamori` via
  `iriguchi`: **a checker whose scope is narrower than what it protects fails
  silently by construction.** Measured here — 43 of 66 files were being checked,
  and the 23 unchecked ones held an annotation the library had outgrown
  (`validator(schema: Path)` had been taking a `Traversable` since #58, surviving
  only because both happen to have `read_text`). The tests are where the
  properties v0.2 rests on are generated, so leaving them out was leaving out the
  evidence.
- **Do not stack pull requests. `gh pr create --base main`, always.** A PR whose
  base is another PR's branch merges *into that branch*, and if the base has
  already merged to `main` the content goes nowhere — `MERGED`, no error, no
  warning, `main` untouched. GitHub retargets a stacked PR only when its base
  branch is **deleted**, which a squash-merge does not always do. This happened
  to #41 and then, after being warned about and planned around, to **#59 on the
  same day**.
- **The ADR-numbering guard is not asking you to stack.** When a second ADR
  cannot be numbered because the first is unmerged, that is
  `test_adr_numbers_are_unique_and_contiguous` saying **one ADR at a time**, not
  *make a stack*. #59 was stacked as a workaround for a guard that was giving
  correct advice. Land the first, then write the second.
- If a stack is genuinely unavoidable, **retarget the moment the base lands** —
  `gh pr edit <n> --base main` — and recover a stranded PR from
  `refs/pull/<n>/head`, never from the squash commit, whose label describes a
  different change than its contents.
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
  only enumerated. Twenty-five ADRs. Nothing is released and the public API is not
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
- **A document keeps its source's modification time; musubi's own records keep
  the run's** (ADR-0022). `kiseki-notes` reads mtime as the day a note was
  written, and musubi writing new files made every note in a corpus share the
  conversion date — with `sync` returning 0, the manifest correct and `verify`
  passing. Not silently wrong: **silently absent**, and a vault where everything
  was written on one afternoon is a thing that can happen, so neither end could
  see it. **The timestamp never reaches the content** — no `observed_at` in the
  front matter, and the front matter's reasoning is unchanged. Putting a
  timestamp in a document is a claim; keeping the file's own is declining to
  destroy one. A `stat` that fails is not a failed run.
- **Two checks exist only where two halves meet** (`tests/test_links_and_bindings.py`).
  Every local markdown link is **resolved**, not pattern-matched — which closes
  the gap ADR-0023 recorded as open, because a redirect whose target directory
  moves breaks a link the filesystem can answer about (measured: renaming
  `src/musubi/schemas/` breaks five). And an identifier in
  `musubi.schemas.CONTRACTS` must be accepted by the `contract` pattern of the
  schema it maps to: rename one side and **every other test still passes**,
  because the conformance tests validate against whatever file they were handed
  and the documents carry whatever the code writes. Each half agrees with
  itself. From `akashi`, whose warning travels with it — **every project binds
  the two differently, so the rule has to be written for musubi rather than
  copied**, or it passes vacuously.
- **The schemas live in `src/musubi/schemas/`, and the conformance tests load
  them the way `docs/contracts.md` tells a consumer to** (ADR-0023). They used
  to sit at the repository root with a build-time `force-include`, which made
  the published sentence `importlib.resources.files("musubi") / "schemas"`
  **false in an editable install** — true for whoever ran `pip install musubi`,
  false for everybody working on musubi, and run by nothing. hatchling ships
  files inside the package with no `force-include`; that was measured, not
  assumed. `schemas/` at the root is a signpost and a test keeps a `.json` from
  returning there: **two copies of a contract are two contracts the moment
  somebody edits one**, and a byte-identity test can keep them equal without
  answering which one a reader is holding.
- **`NotionSource` keys by the page id, and says so as `notion-page-id`.** Not
  `path`, which would be a lie, and not the title, which changes. The key becomes
  the output filename (ADR-0013), so a corpus of Notion pages has hexadecimal
  names — and **loses nothing**, because Notion writes the title into the
  document's first line as an `# ` heading (measured on a real export: the
  filename's title and the H1 are the same string).
- **A file with no page id is skipped, never keyed by path instead.** Mixing two
  derivations under one `key_derivation` makes the manifest's statement true for
  some units in a run and false for others, with nothing saying which.
- **Whether a Notion page id survives a re-export is still unmeasured**, and the
  source does not pretend otherwise. ADR-0006 contradicts itself — its Context
  says the filename UUID is regenerated, its Decision keys by it — and a real
  export shows **three UUIDs on three layers**, so the two statements may be
  about different numbers. One counterexample from a second export decides it. If
  it says no, the derivation falls back to `path` and the manifest says `path`.
- **A Notion export carries no per-page date.** Every entry shares the export's
  timestamp, to the second. So the source reports `modified_at=None` rather than
  handing on a date that is uniform and looks like history — ADR-0022's failure
  arriving from the other direction. `kiseki-notes` warning that a Notion corpus
  shares one date is **correct**, and `docs/sources.md` says so.
- **`musubi verify` compares a corpus with its own manifest, and that is not
  fidelity.** A corruption that happened *before* the hash was taken is recorded
  in the hash, and `verify` reports `all hold` — measured, by replacing every
  non-ASCII character in `render()`: the corpus said `# ????` where the vault
  said `# ギア設計` and the exit code was 0. **A hash agreeing with itself only
  proves the damage was deterministic** (from `kiseki` via `manager`). This is a
  boundary rather than a bug — `verify` answers about a folder with no run in
  sight — so the report says it, the docstring says it, and a test pins it. What
  compares a corpus with the file it came from is `musubi trace`; what catches
  it during a run is ADR-0004's verbatim equality.
- **"Is the output well formed" and "is the value the one that went in" are
  two questions, and they want different poisons.** Substituting characters
  *after* encoding gives invalid UTF-8, which the encoding tests catch.
  Substituting them **while the value is still a `str`** leaves output that is
  valid UTF-8, valid JSON, and wrong. From `mamori` through `manager`, after
  `tsumugi` aimed the first poison at the second question and caught nothing.
- **For a character-measured converter, fidelity is structural and free.** A
  `verbatim` segment must read the same on both sides (ADR-0004), so a
  substituted character makes the map's own invariant false — measured: the
  str-stage poison in the emitter fails **eight** tests, `trace 3` among them.
  **A PDF's segments are all `transformed`**, which claims no interior
  correspondence, so that invariant has nothing to catch. The same poison there
  failed **two** tests, and both by accident: they happened to use non-ASCII
  examples. `test_what_the_page_showed_is_what_the_text_holds` asserts it on
  purpose, and the poison now fails six.
- **A PDF's map counts pages, not characters** (ADR-0025). Its words are inside
  Flate-compressed streams, so no byte range in the file holds them and a
  character offset would index text that does not exist. `src` is a page range,
  `source_unit` is `opaque`, and **every segment is `transformed`** — a verbatim
  claim means the correspondence holds at every interior offset, and inside a
  page it holds nowhere. **The map that composes is the map that is honest**:
  `followed_by` refuses a non-character source only when a *verbatim* run is
  present, because shifting an offset by a constant is the only arithmetic it
  does on that side.
- **A page with no text layer never renumbers the pages after it.** Page three
  stays `src[2:3]` when page two was scanned. Reporting it as page two would send
  a reader to the wrong page with full confidence, which is the one thing a
  locator must not do.
- **`traceable` means different things per converter and the totals do not say
  so.** A PDF at 100% resolves to a page; a Markdown file at 100% resolves to a
  character. The manifest's `limits` say it and each map's `source_unit` says it;
  the aggregate percentage says neither. **A reader taking the number and not the
  sentence gets a worse answer than before PDF existed.**
- **The HTML converter is where coverage becomes a measurement.** Boilerplate
  is a `removal` segment with a rule (`boilerplate.nav`), never a gap; entities
  are `transformed` because `&amp;` is five characters in and one out; `# ` and
  paragraph breaks are `synthetic` with an empty source span. **Every character
  of the source is in exactly one segment.** `convert_charrefs` is **off** and
  that is not a preference — with it on, `html.parser` folds entities into the
  surrounding text and the offsets stop lining up, producing plausible text over
  a wrong map.
- **Do not resolve an entity with `html.unescape`.** It implements HTML5's
  longest-prefix rule, so `&notarealentity;` comes back as `¬arealentity;` — it
  matches the real `&not` and leaves the rest. Applied to a reference the parser
  has already isolated, that invents a character the page does not contain.
  `html.entities.html5` is looked up directly instead, and an unrecognised name
  stays as written.
- **Whitespace in HTML is two things.** Between blocks it is markup indentation
  and belongs nowhere; **inside a line it is a word boundary**, and dropping it
  turned `See <a>this</a> &amp; that` into `See this& that`. Both cases have a
  test, because the first fix for one broke the other.
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
- **A setting arrives from four places and says which one.** `--flag` beats
  `MUSUBI_*` beats the nearest `musubi.toml` beats the default, the nearest file
  wins **whole** rather than merging, and `musubi config` prints the origin
  beside every value plus the files it found and did not read (ADR-0027). Every
  flag a file can also set has `default=None` in the parser: an `argparse`
  default cannot be told apart from a typed value, so without it the file could
  never win and the origin column would credit the wrong layer.
- **A setting names an algorithm, never an import path.**
  `infrastructure/algorithms.py` is the table and `musubi/config.py` is the
  composition root that reads it — the row the architecture map has always
  reserved for `config.py`, now occupied. musubi is pointed at everything its owner has
  written, so a settings file that can name a module is a settings file that can
  run anything. A converter from elsewhere is registered by a program that
  imported musubi deliberately, and is then nameable because the table is read
  when the question is asked rather than at import.
- **A refusal is only as good as the inputs it was pointed at, and the six in
  `tests/test_the_refusals_that_did_not_fire.py` were each already written.**
  Overlapping replacements were refused and an insertion *inside* one was not,
  because an empty span overlaps nothing by definition. A credential prefix was
  found and never asked whether it *started* anything, so 3.33% of base64url
  documents stopped a sync (ADR-0026). A PDF with no text layer was refused and
  one whose stream inflates to 64 MB killed the process, which is not
  fail-closed but *absent*. All six passed 871 tests. When adding a refusal, the
  question is not whether it fires -- it is which neighbouring input it does not
  fire on, and that input is the test.
- **Do not use a character the data can contain as a separator.** A Notion
  origin is `outer.zip!Part-1.zip!Title <id>.md` and was split on `!` to read
  the entry back, so a page called `Done!` was listed by `plan` and could not be
  opened by `sync`. The fix is not an escaping rule: the path is **rebuilt by
  the same expression that built it** and compared whole, so there are not two
  sides to keep in step.
- **Decompression is unbounded unless somebody bounds it.** `zlib.decompress`
  and `ZipFile.read` both size their buffer from a number the file supplies.
  musubi reads archives downloaded from services and PDFs from anywhere, so
  `MAXIMUM_STREAM_BYTES` and `MAXIMUM_ENTRY_BYTES` are limits with reasons
  attached, and passing one is a refusal with a token in the manifest.
- **A cp932 fixture made of ordinary Japanese proves nothing.** `設計メモ` and
  `テントは 2.4kg。` round-trip through cp932 without a mark, so every test in
  `test_console_encoding.py` would have passed with musubi's encoding handling
  deleted — and the comment above the fixture claimed it was unencodable, which
  was true of the em dash **musubi** prints and false of the note. The fixture
  now carries `𩸽` (U+29E3D), outside cp932 and outside the BMP, and
  `test_the_fixture_can_actually_break_a_cp932_console` asserts that **before**
  the rest of the file runs. From `seam`, who found the same in its own
  fixtures, along with the reason for the ordering: **print nine passes and then
  a caveat, and the reader takes the number.** `kiseki`, `mamori` and `tsumugi`
  each found it in their own on the same day; Japanese text is *usually*
  representable in cp932, which is exactly what makes it a comfortable and
  useless sample.
- **`COMMANDS` in the CLI is a module-level table so a test can read it.**
  ADR-0020's promise is about musubi, not about the three commands that existed
  when it was written — `verify` landed after it and
  `tests/test_console_encoding.py` never pointed a narrow console at it. It
  survives (measured: exit 0, heading arrives as `musubi verify ? …`), but
  nothing said so. A guard now reads the table and turns red when a command has
  no cp932 coverage, verified by adding a fifth and watching it fire.
- **A redirect is not the console path, and until now nothing here tested it.**
  Python picks the *locale* encoding for a redirected stream and the console's
  for a terminal; they are configured separately. Every cp932 test in this
  repository patches `sys.stdout` in-process, which exercises one of the two.
  `tests/test_redirected_document.py` starts a real process with `stdout` going
  to a file and `PYTHONUTF8` cleared. From `akashi`, which wrote a `cp932` JSON
  report its own `recheck` refused — **it wrote a document it could not read**,
  because the rule lived in the reading side's docstring and the writing side
  had none.
- **`docs/contracts.md` names the encoding for the corpus and inherits it for
  the JSON**, and the distinction is the whole point. `manifest.json` and the
  trace maps are JSON, and RFC 8259 §8.1 **already** requires UTF-8 for JSON
  leaving a closed ecosystem — so writing it down there is a **pin**, not a
  missing rule. A document in `documents/` is Markdown or plain text, which say
  nothing about encoding, so the contract **grants** it: UTF-8 with LF, on every
  platform. **That third one is where the real gap was**, and it is where it
  matters most — a map's offsets are *character* offsets, so a corpus written in
  the producing machine's locale would mean different things on different
  machines and **every map over it would still validate**.
- **Do not write "a contract that does not name its encoding is one its own
  producer gets wrong."** It is too broad, and `akashi` withdrew it after
  measuring: RFC 8259 was in force the whole time and its implementation broke
  it. The correct form is **a requirement already in force can be broken by an
  implementation**, and the reason the broad version is worse is that it
  **exonerates the producer** — which was `akashi` itself.
- **`empty_parameter_set_mark = "fail_at_collect"`** is set, from `iriguchi`
  through `manager`. pytest's default marks an empty parameter set as **skip**,
  which spells *there were no cases* exactly the way it spells *this does not
  apply* — and unlike `for x in []`, nobody wrote it. Verified by emptying a
  collection and watching collection fail rather than skip.
- **What that closes is emptiness, not bias, and the two need different tools.**
  A population of zero is countable; a population of forty that is all the same
  value is not. None of the PDF converter's three defects was a vacuous loop:
  two had tests that ran and only ever saw `characters`, and one had no test at
  all. **What found them was a new input, not a new check** — writing the
  converter and putting a sync through it.
- **`tests/test_what_is_read_and_written.py` is a set equality, deliberately.**
  A `for` passes on empty and a `parametrize` skipped on empty; **an empty set
  is not equal to a non-empty one**, which closes the one place pytest cannot
  see into — a plain assertion in a single test. It pins the suffixes a source
  reads and checks both directions against the converter registry, so a format
  cannot silently stop being ingested and a converter cannot become unreachable.
- **Guard a collection where it is built, not in the tests that loop over it.**
  `for x in things: assert ...` passes when `things` is empty, so ten invariant
  tests were one strategy edit away from all going green while checking nothing.
  Measured: loosening `a_vault`'s `min_size` to 0 turns **21 tests red** with the
  guard in `maps()` and would have turned none red without it. The same guard is
  now on `CORE.rules` and `SIGNATURES`; `_modules()`, `_adr_files()` and
  `_refusals()` already had it. From `akashi` via `manager` — check 27.
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
- **A field added to a published contract is a new identifier** (ADR-0024), not
  a wider old one. Every object is `additionalProperties: false`, so measured:
  a manifest with one extra field and a manifest that is genuinely malformed are
  **both rejected, both as `ValidationError`** — a consumer holding the older
  schema cannot tell *I am out of date* from *this document is wrong*, and those
  want opposite responses. Bumping the identifier moves the signal to step 1 of
  *Writing a consumer*, the `contract` check, which runs **before** validation.
  Same defect as the trace map's fourth resolution rule: one value carrying two
  situations that need different handling. Free to fix now and not after a
  freeze — `tsumugi` measured that loosening a frozen schema does not help,
  because consumers ship a vendored strict copy that goes on refusing.
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
