# 22. The document keeps the day it was written

**Status:** accepted

## Context

`kiseki-notes` reads a document's modification time as the day the note was
written. musubi writes new files, so every document in a corpus carried the
conversion date.

Measured before this decision:

```
source mtimes  : 2025-07-26, 2025-12-23, 2026-05-22
corpus mtimes  : 2026-08-30, 2026-08-30, 2026-08-30
distinct dates in the source : 3
distinct dates in the corpus : 1
VERDICT: TIME AXIS COLLAPSED
```

**Nothing anywhere reports a problem.** `sync` returns 0, the manifest is
correct, `musubi verify` passes, every hash matches. The corpus is internally
consistent; it is a consistent corpus in which every note happens to share a
date. `kiseki-notes` cannot see it either — a vault where everything was written
on one afternoon is a thing that can happen.

This is the day's recurring shape applied to time: not *silently wrong*, but
*silently absent*. ADR-0076 in `kiseki` makes a record one note per day
**because a note being returned to is itself the signal**. A flattened mtime does
not corrupt that signal, it deletes it, and what remains looks like a note nobody
ever came back to.

The reason musubi never carried it is in `domain/frontmatter.py`, and it is
sound: **musubi does not know when a note was written.** The filesystem knows
when it was last touched, which is a different fact, and putting it in the front
matter would make an artefact's content depend on its modification time — so a
re-sync that changed nothing would rewrite the corpus, and ADR-0006's idempotence
claim would be false.

That argument is about **content**. It was applied to a channel it does not
reach.

## Decision

**A document musubi writes keeps its source's modification time.** `Found`
carries `modified_at`, taken from the `stat()` the source already makes for the
size — so discovery still opens nothing (ADR-0007) — and the emitter puts it back
on the staged file. `promote` is a rename, so what is set there is what lands.

**musubi's own records keep the run's time.** The trace map and the manifest are
musubi's account of a run, not documents somebody wrote; backdating them would be
a claim about when the run happened, and a false one.

**Nothing reaches the content.** No `observed_at` in the front matter, and the
front matter's reasoning stands unchanged. Two runs over an unchanged vault still
produce identical bytes, and every hash is still independent of when the corpus
was built. Preserving a file's own metadata is not the same act as asserting a
fact inside the document, and the distinction is the whole of this decision:
**putting a timestamp in the content is a claim; keeping the file's is declining
to destroy one.**

**A failure to set it is not a failure of the run.** A read-only or exotic
filesystem gives a worse corpus, not a broken one, and throwing away a completed
sync over a timestamp would be the wrong trade.

`modified_at` is `None` from a source that does not know, and such a document
keeps the run's time rather than being given a guess.

## Consequences

`kiseki-notes` gets a corpus with a history in it. More generally, the one fact
the filesystem was carrying about each note survives the conversion, which is the
same claim ADR-0004 makes about offsets, applied to time.

`kiseki` is also looking at detecting the flattened case from its side — every
note sharing a date is something `kiseki-notes plan` can warn about, in the dry
run it already has. Both ends is right: **either end alone is a single point at
which this silently returns.**

Verified by removing the change and watching four of the six new tests go red.
The two that pass either way assert idempotence and the `None` default, which are
supposed to hold in both worlds.

## What it costs

**A derived file now carries a timestamp that is not about it.** `documents/a.md`
was written today and says it was written last year. Anything reasoning about the
corpus as a set of files — a backup tool deciding what is new, a sync client, an
editor's recent list — is now told something false about musubi's own output. The
alternative was telling `kiseki` something false about the owner's notes, which is
worse, but this is a real cost and not a free win.

**It makes musubi's output depend on a filesystem's fidelity.** mtime resolution
differs across filesystems, and a corpus copied without `-p` loses this again
silently — the same failure, one step downstream, where musubi cannot see it.
This decision reduces the number of places the time axis dies; it does not get it
to zero, and nothing musubi can do would.

**It is a guarantee to one consumer's reading of one field.** `kiseki-notes`
treats mtime as the written date. That interpretation is `kiseki`'s and could
change, and musubi has now shaped its output around it — mildly, but ADR-0013 was
explicitly about *not* doing that. The defence is that this preserves a property
of the source rather than adopting a consumer's schema, and that a second
consumer wanting the opposite would be asking musubi to destroy information,
which is not a thing two consumers can reasonably disagree about. If one ever
does, this ADR is the thing to reopen.
