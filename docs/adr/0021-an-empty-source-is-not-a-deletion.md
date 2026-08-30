# 21. An empty source is not a deletion, and the plan says so too

**Status:** accepted

## Context

`sync` withdraws artefacts whose units the source no longer has. The previous
manifest is the ledger (ADR-0009): musubi deletes what it *recorded writing*,
and never what it merely found, so a folder somebody else keeps files in
survives a sync intact.

That safety property is also what makes the failure total. When a source yields
**zero** units, `held - written` is every path the manifest recorded, and the
whole corpus goes — precisely and completely, exit 0, a report reading
*0 documents, 6 withdrawn.*

Measured before this decision, not read:

```
after a normal sync : 3 artefacts, ['a.md', 'b.md', 'c.md']
after the empty sync: 0 artefacts, 6 withdrawn
  documents left    : []
VERDICT: CORPUS DESTROYED, no error raised
```

**musubi cannot tell "the owner deleted everything" from "the source became
unreadable."** Both are a directory that resolves and holds nothing:

- an external or network drive unmounted, its mount point still present
- a cloud-sync folder (Dropbox, iCloud, OneDrive) that has not populated
- a drive letter reassigned under a configured path
- a typo that lands on a real empty directory

ADR-0001 points musubi at *the folder that holds everything the owner has ever
written.* `sync` is the one command here that deletes, and it runs unattended
against that folder. `errors.py` already states the standard this violated —
musubi fails closed, and it fails closed *loudly*, because the alternative to
raising is not a visible error but a corpus that is quietly wrong.

The bug did not come from reading the code for defects. It came from the `seam`
session naming why a zero goes unquestioned — *an empty result is only doubted
when it contradicts expectation* — after `gh run list` returned empty and was
read as an answer. The same shape in tooling cost nothing. Here it deletes a
corpus.

## Decision

**A run that read nothing, against a corpus that exists, refuses.** It raises
`EmptySourceError`, promotes nothing, deletes nothing, and names the flag —
`--withdraw-all` — that the operator passes once they have looked at the source.

**Zero is not a threshold chosen for caution.** It is the only count at which
the two readings cannot be separated. **One surviving unit proves the source is
readable**, and every withdrawal beside it is a deletion somebody asked for. So
there is no percentage, no "more than N", and nothing to tune: the condition is
exactly the ambiguous case and nothing wider.

Two consequences follow from making it a refusal rather than a warning:

**A first sync into an empty destination is not the ambiguous case.** With no
previous manifest there is nothing to withdraw and nothing to be wrong about.
Refusing there would mean musubi could not be pointed at a folder before it had
anything in it.

**`plan` computes and reports the withdrawal too.** It did not before — the
arithmetic lived inside `sync`, so the dry run reported what would be written
and stayed silent about what would be deleted. That is not a dry run of the same
command, and deletion is the half an operator would want the warning about.
`--withdraw-all` therefore goes in `_shared()`, on both commands: a flag that
exists on the real run and not on the dry one is exactly how a plan stops
predicting a sync.

## Consequences

An operator whose vault genuinely is empty now types a flag they did not have to
type before. That is the cost, and it is paid on the rare intentional case so
that the common accidental one stops.

`plan --json` now renders a manifest whose `withdrawn` is populated. The schema
already carried the field; what changed is that the dry run fills it.

The guard was verified by removing it and watching the tests go red — three of
the seven new tests fail without it, and the four that assert *ordinary
withdrawal still works* correctly pass either way.

## What it costs

**A refusal is a thing that can be wrong, and this one is wrong in a specific
direction.** A source that legitimately empties — every note deleted on purpose
— now stops a scheduled run and waits for a human. If musubi is wired into
something unattended, that is an alert at 3am for a corpus nobody wanted
anyway. The alternative was silence in the case where the drive was merely
unplugged, and between a false stop and a silent deletion this project takes the
stop.

**`--withdraw-all` is a flag that, once someone puts it in a cron line to make
the alert go away, disables this decision permanently and invisibly.** The same
shape as `allow-direct-references` in `pyproject.toml`: the danger is not the
loud failure, it is the one-line fix that converts it into a quiet one. Nothing
here prevents that, and nothing can — what can be done is to say so at the
place where the flag is written, which is why the help text names the
consequence rather than the condition.

**It does not detect the general case.** A source that returns *some* of its
units — a partially mounted drive, a sync client halfway through, a permissions
change that hides one subtree — withdraws the rest and this decision says
nothing. That failure is quieter than the one being fixed and strictly harder:
there is no count at which "half a vault" and "half a vault deleted" become
distinguishable from inside. This ADR fixes the case that is decidable and
leaves the one that is not.
