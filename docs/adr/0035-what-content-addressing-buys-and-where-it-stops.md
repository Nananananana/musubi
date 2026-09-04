# ADR-0035 — What content addressing buys, and where it stops

**Status:** accepted
**Date:** 2026-09-05
**A hash per touched path, and the one limit it does not move.**

## Context

[ADR-0034](0034-a-corpus-that-remembers-what-it-was.md) recorded paths and
verbs — added, changed, removed — and had to publish a limit as a consequence:

> A path that was removed and later added back is reported by `musubi diff` as
> `changed`, even when the bytes came back identical.

That was honest and it was also avoidable. The journal was recording *which*
documents moved and throwing away the one fact musubi already had about each of
them, which is the fact the whole library is organised around: what they hash
to. And a second thing fell out of the same omission — **a rename was
invisible.** A document moved from `documents/stove.md` to
`documents/cooking.md` is a `removed` and an `added` in a journal of paths, and
nothing distinguishes it from a deletion that happened to coincide with an
unrelated new file.

Both are the same missing field.

## Decision

**An entry records a content hash for every path it names.** For `added` and
`changed`, the hash the artefact now has; for `removed`, the hash it had when
it left — the last thing known about a document that is no longer there, and
the half of a move that says where it came from.

**A fold over a range is now arithmetic rather than a verb machine.** For each
path: what it held when the range began, against what it holds now. The answer
is exactly what `changes()` gives for the two end states, so the divergence
ADR-0034 published is gone rather than documented. The property test asserts
the equality outright instead of naming an exception to it.

**`musubi diff` and `musubi log` report a move as a move**, once, with the two
names. `Change.summary()` counts it once too: a run that renamed one file used
to read *1 added, 1 removed* — two events, neither of which happened.

**A pair is made only where a hash matches exactly one path on each side.** Two
files with identical content — an empty note, a stub copied twice — are not
evidence about which became which, and they stay in `added` and `removed`,
which is what they are.

**And a line without hashes is folded conservatively and said to be.** A
journal that spans this change has entries of both kinds; a reader that
rejected the older ones would turn a history with less detail in its early part
into no history at all. Those paths fall back to the verb, `Change.exact` is
false for the whole answer, and the report says which half of a mixed history
the reader is looking at.

**The field is added to `musubi.run-journal/1-draft` rather than making a `/2`.**
[ADR-0024](0024-a-field-added-is-a-new-contract.md) governs a
*frozen* contract; this one carries `-draft`, which is the statement that it may
still change meaning. Doing it now, before anything outside musubi reads one, is
the whole point of the draft period.

**What does not move: musubi still cannot give a document back.** A hash is an
identity, not a copy. `musubi diff` can now say *this came back exactly as it
was*, and it still cannot produce what was there in between. The sentence from
ADR-0034 stands unchanged, and it is the reason this ADR exists as a separate
decision rather than as an amendment to that one — **the storage boundary moved
by exactly one notch, and saying which notch is the useful part.**

## Consequences

- `musubi blame` became possible and is here: for every artefact in the corpus,
  which run put it there and which run last changed it.
- `musubi log --path <document>` answers `git log -- <path>`, which is the shape
  the audit question is actually asked in — not *what did Tuesday's sync do*
  but *what has happened to this document*.
- **`blame` abstains where the history cannot reach.** An artefact that predates
  the journal, or one whose corpus was copied in, prints as *not in this
  history*, and the report says how many did. Attributing it to the oldest run
  it happens to sit beside would be a confident wrong answer in the one place
  this library exists to prevent one — and it would be invisible, because the
  answer would look exactly like a real one.
- An entry grows by about 80 bytes per touched path. It grows with **the work**
  and not with the corpus, which was ADR-0034's constraint: a no-change re-sync
  still writes almost nothing.

## What it costs

**A rename is inferred and can be wrong in one direction.** Delete `a.md` and,
in the same run, add `b.md` with byte-identical content that has nothing to do
with it, and this reports a move. The inference is sound about the *bytes* and
is a guess about the *intent*, and no amount of hashing closes that gap —
musubi does not watch the filesystem and cannot see a `mv`. The pairing rule
keeps the guess from spreading (identical content on either side stops it), and
the report says `(same bytes)` rather than *renamed*, which is the claim that
is actually true.

**And it puts a second copy of a hash in a second file.** The manifest already
records every artefact's `content_hash`; the journal now records some of them
again. They are written by the same run from the same values, so they cannot
drift within a run — but a corpus restored half from a backup can have a
journal that hashes to one thing and a manifest that hashes to another.
`musubi verify` grew the artefact-by-artefact check with this decision
(`journal 3`) rather than leaving it as an invitation -- a duplicated fact that
nothing compares is the shape ADR-0034 already named about the journal as a
whole. What remains is that the duplication is real: two files now say the same
thing, and the reason to accept it is that the second one has to stand alone
when the first has been replaced.
