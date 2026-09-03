# ADR-0027 — The nearest file wins whole, and every value says where it came from

**Status:** accepted
**Date:** 2026-09-04
**Supersedes nothing.** Adds a layer that [ADR-0012]'s posture and [ADR-0008]'s
fail-closed policy both constrain.

## Context

Every option musubi has was a command-line flag. That is correct for a tool run
once and wrong for one run every day over the same folder: `--as notion --into
corpus --screen-entropy --allow aws.access-key:notes/old.md` is a line nobody
retypes, so it becomes a shell alias, and the alias is a configuration file that
no command can print.

There are four established shapes for this in Python, and no reason to invent a
fifth:

| | |
|---|---|
| `pyproject.toml` `[tool.x]` | `ruff`, `mypy`, `pytest`, `hatch` |
| a dedicated `x.toml` | `ruff`, `uv`, `hatch` |
| environment variables | everything that runs in CI |
| flags | everything |

Two decisions are not settled by convention, and both are decisions this project
in particular has to make deliberately.

**What happens when there are several files.** `ruff` merges only when a file
says `extend = `; otherwise the nearest wins whole. Other tools merge every file
in the ancestry. Merging is more expressive and it makes *why is this setting on*
a question with no answer shorter than the whole tree.

**Whether a value can be traced.** No tool in that table can say where an
effective value came from. `ruff config` prints documentation, not provenance.
That is a small gap for a linter and a strange one for musubi, whose entire
product is the ability to say where something came from.

## Decision

**The nearest file wins whole**, and the files that were found above it are
printed rather than silently ignored. There is no merging and no `extend`;
musubi does not have the case that needs it and will not guess at its shape.

**Every effective value carries its origin**, and `musubi config` prints the
origin beside the value:

```text
  source       filesystem                   musubi.toml:source
                                            or: notion, obsidian
  into         elsewhere                    MUSUBI_INTO
  rules        none                         MUSUBI_RULES
                                            or: core
```

Precedence is flag, environment, file, default. A flag that a file can also set
has `default=None` in the parser, so that *not given* is distinguishable from
*given the value the default happens to be* — otherwise a flag can never be
reported as the reason for a setting, and the file could never win.

**An unrecognised key stops the run**, naming the nearest known one. A typo in a
setting name is otherwise silent, and the setting the typist meant to change
stays at its default while the file plainly says it does not.

**`--allow` replaces rather than adds**, like every other flag. That is the
fail-closed direction: losing an allowance stops a run that would have
proceeded, and the opposite rule lets a forgotten line in a file two directories
up keep a credential moving.

**There is no `screener = "none"`.** [ADR-0008] stops a run on a credential and
a corpus that was never screened looks exactly like one that was. A switch for
that is not a setting; it is a different program.

**A setting names an algorithm, never an import path.** [ADR-0001] is about
musubi being pointed at everything its owner has ever written, and a settings
file that can name an arbitrary module is a settings file that can run anything.
Names resolve against a table that ships in the wheel. A third-party converter
is registered by a program that imported musubi deliberately, and
`musubi config` lists it, because the table is read when the question is asked
rather than at import.

## Consequences

- `musubi config` is the fifth command and writes nothing, which makes it the
  same posture as [ADR-0012]'s `plan`, one step earlier: the settings a plan
  would be made with, before the plan.
- Which algorithm ran is already in the manifest — the converter per artefact,
  the ruleset with its version — so a choice made in a file is visible in the
  corpus afterwards and not only in the shell history of whoever ran it.
- Somebody standing three directories down gets *their* file, not the sum of
  three. When that is wrong, the answer is a flag or a different file, both of
  which the origin column will then attribute correctly.

## What it costs

**A setting can now be true without anybody in the room having typed it**, and
that is the whole point and the whole risk. The origin column is the mitigation
and it is only a mitigation: it answers *where did this come from* for a person
who thought to ask. Somebody debugging a corpus that came out wrong is not
usually asking that question yet.

The second cost is narrower and permanent: **the option list is a contract with
a shape no schema checks.** `OPTIONS` names the settings, the parser names the
flags, and the registries name the algorithms; three lists in three files, with
no reason to stay in step. `tests/test_configuration.py` asserts the set
equalities rather than looping over one of them — the shape `iriguchi` used and
`#70` proved on a rebase — but that is a test, not a type, and a fourth list
added later will not automatically be covered by it.
