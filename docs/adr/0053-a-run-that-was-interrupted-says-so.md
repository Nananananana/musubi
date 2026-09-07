# 0053. A run that was interrupted says so

**Status:** accepted
**Date:** 2026-09-12
**Context:** [ADR-0008], [ADR-0046], [ADR-0049]

## What was probed

musubi has no lock. `begin()` removes the staging area and makes it again, so a
second run into the same destination takes the first one's files with it — and
a scheduled sync overlapping a manual one is an ordinary Tuesday.

`errors.py` says so in as many words, in the justification for `retryable`:
*there is no network, no lock, no service and no timeout*. Nothing had asked
what happens.

Constructed deterministically, with the second run's `begin()` landing after
four of six documents had been promoted:

```text
  run A promote() raised FileNotFoundError after 4 files
  corpus: 6 documents, 4 carry run A's edit, manifest lists the old 6
  verify: FAULTS (8)
  after a normal sync: 6 carry the edit, verify holds
```

**The design holds.** The manifest is promoted last ([ADR-0008]), so what a run
cut short leaves is a corpus **ahead of its own account** rather than a mixture
of two runs: `verify` names every document that disagrees and the next ordinary
sync repairs all of it. That is what `promote()`'s docstring has always claimed
about a crash, and a second run is a crash with a cause.

## The defect was how it arrived

`promote()` let the `FileNotFoundError` out. At the command line that is caught
as an `OSError` and reported

```text
Unreadable: the file system refused: [WinError 3] ...
```

which is a sentence about the machine. **The machine was fine.** A person reads
that and goes to look at their disk; an orchestrator files it under a kind that
means *the environment*, next to a full disk.

## Decision

**`InterruptedRunError`**, named, catalogued, and `retryable: true` — because
running the sync again is exactly the repair.

The message says how far it got, that `musubi verify` will name the documents,
that running it again fixes it, and that a destination takes one run at a time.
`docs/using-a-corpus.md` says the same where a user reads.

**Detected on the file, not the folder.** The first version of this checked
whether the staging directory was gone and never fired once: `begin()` removes
the directory *and makes it again*, so it is there and empty. What is actually
missing is the file this run staged, and that is what the guard looks at.

## What it costs

**A second `retryable` kind**, which is the field's first real distinction:
`Unreadable` and this one are both about the machine rather than the data, and
every other failure gets the same answer however many times it is asked. The
catalogue test now asserts that property rather than counting to one.

**A guard on the promotion loop's hot path.** One `exists()` per failed replace
— which is to say, none at all on a run that works, because it is inside the
`except`.

**It is a message, not a lock.** Two runs still collide; the first one now
explains itself. A lock is a different decision with its own failure modes —
stale files, crashed holders, a `--force` somebody will reach for — and it is
not obviously worth taking for a condition that `verify` detects and the next
run repairs.

## Consequences

This is the third constraint this month that was **reasonable, designed for,
and written down nowhere**: one source per destination ([ADR-0049]), one run at
a time, and before them the skip vocabulary. Each was found by asking what
happens rather than by reading what should.

The pattern in all three is that the *code* handles the case correctly and the
*person* is not told. ADR-0008's promotion order was doing its job here before
anybody checked; what was missing was the sentence.

[ADR-0008]: 0008-a-credential-stops-the-run.md
[ADR-0046]: 0046-a-failure-that-a-program-can-name.md
[ADR-0049]: 0049-a-corpus-belongs-to-the-source-that-wrote-it.md
