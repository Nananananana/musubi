# ADR-0034 — A corpus that remembers what it was

**Status:** accepted
**Date:** 2026-09-05
**Git-like history for a corpus, and the one thing it deliberately is not.**

## Context

Asked whether musubi could have git-like functionality, and reviewed with the
same suggestion — *TraceMap 自体を「コミット」として扱い、どの時点のインジェスト結果か
を履歴で辿れるように* — the first thing to establish was how much of it was
already here. Most of it, unused as history:

```text
content_hash    a document is identified by its bytes          content-addressed
run_id          a hash over exactly the inputs that decide     reproducible
determinism     the same inputs give the same id (ADR-0003)    a run has an id
```

What was missing was the link. Each `sync` overwrote `manifest.json`, so a
corpus could say what it **is** and never what it **had been** — and the
question this family exists to answer is a question about the past: *when did
this document enter the corpus, and which run put it there.*

The review also named the trap, correctly: **using git itself makes a large
corpus a large repository**, and suggested keeping ids and metadata and putting
the data elsewhere.

## Decision

**A journal of changes, appended, beside the corpus.** `<destination>/runs.jsonl`
holds one `musubi.run-journal/1-draft` object per line: what the run added,
changed and removed, how many artefacts it left alone, and the run it followed.

**Changes, not snapshots.** An entry names what moved and *counts* what did not.
This is not a space optimisation — it is the difference between a feature that
works on a real corpus and one that works in a demonstration. A manifest for ten
thousand artefacts is megabytes, and a hundred runs of those is a history larger
than the thing it describes. A no-change re-sync writes an almost empty line,
which is the common case.

**Appended, and outside the staging area.** Everything else musubi writes is
staged and promoted together because [ADR-0008](0008-a-credential-stops-the-run.md)
is fail-closed. The journal is the opposite kind of thing: a record that a run
happened, written once the run *has* happened, after `promote()` and after the
withdrawals. A refused run appends nothing.

**An entry has its own id, and it is not the corpus's.** This is the part the
first implementation got wrong, and it took four minutes of running the real
command to find:

```text
add a.md      run 3f34b18e31b8
edit a.md     run 0ecc394e9959
delete a.md   run 1bc3be6e2a7a   <- the id of the run three back
```

`run_id` is over the artefacts' content hashes, so a corpus that returns to a
state it held before returns to the same id. Three entries then answered to
`--since 1bc3be` and the command could not say which history was meant. **A run
id is a tree id. It was never a commit id.** `entry_id` hashes the run, its
parent and its time — which is exactly what a commit has always been, and the
reason git puts the parent inside the id rather than beside it.

**`musubi log` and `musubi diff` read it, and `musubi verify` checks it.** The
last is the one that matters: `verify` now asserts that the history's last entry
names the corpus the manifest names, and that each entry's parent is the
previous entry's run. Without that the file is a *log* — written beside the
corpus, compared against nothing, free to drift for a year before anybody looks.

**And the sentence that is stated everywhere this feature is mentioned:**

> This is history, not storage. musubi cannot restore a document it did not
> keep.

`log` says a document changed on Tuesday and `diff` says which ones. Neither can
give back Monday's text, because the corpus holds one version and the journal
holds only what the change *was*. Rolling back needs content storage, which is a
much larger decision. Saying so is not modesty: *git-like* implies rewind, and a
consumer who assumes it will build on a promise musubi never made.

## Consequences

- The audit question is answerable for the first time. A document under
  question can be asked when it entered the corpus and which run put it there,
  and the run id ties the line to the full `manifest.json` account of that run.
- `musubi diff` folds a range of entries rather than comparing two states,
  because states are what the journal does not keep. Added-then-removed
  cancels; added-then-changed is still added.
- **A document that left and came back is reported as `changed`, even when the
  bytes came back identical.** The fold knows it was removed and knows it was
  added; it does not keep the bytes. *Changed* is the claim that is never false
  about the history where *unchanged* could be — and this is the storage
  boundary showing through in the one place a user meets it.
- A corpus with no journal is not invalid. One written before this ADR keeps no
  history and is otherwise sound.
- `tests/test_invariants.py`'s byte-identical property now excludes `runs.jsonl`
  along with `manifest.json`, for the same reason — both carry `created_at` and
  the two runs are given different clocks — and asserts separately that the two
  histories agree on everything else.

## What it costs

**A file that grows with the number of runs, forever, and nothing prunes it.**
An entry is small, and a daily sync of an unchanged folder writes about 250
bytes; a decade of that is under a megabyte. But there is no `musubi gc`, no
compaction, and no answer yet for somebody syncing every ten minutes. The
absence is deliberate — pruning a history to save space is a decision about
which evidence to destroy, and this project should not make that one casually —
but it is an absence.

**A second file that can disagree with the corpus.** Before this there was one
ledger and `previously_written()` read it. Now there are two documents about the
same runs, and keeping them in step is a real obligation rather than a
theoretical one. `verify` checks the join, which is why the check was written at
the same time as the feature rather than after it — but a corpus is only checked
when somebody runs `verify`.

**And the naming invites the thing it cannot do.** Every reader who sees `log`
and `diff` will eventually type something expecting `checkout`. The commands say
so, the schema says so, this ADR says so, and people will still ask. The
alternative was to avoid the git vocabulary entirely and make the feature harder
to find, which trades a disappointment for an obscurity — and the disappointment
is recoverable by reading one line of output.
