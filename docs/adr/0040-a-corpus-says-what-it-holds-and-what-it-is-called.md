# ADR-0040 — A corpus says what it holds, and what it is called

**Status:** accepted
**Date:** 2026-09-07
**Two places the manifest was short, found by an orchestrator asking careful questions.**

## Context

The `sora` orchestrator's second round (`musubi-work/01_sora_round2.md`) asked
two things that turned out to be about the same property: **the manifest is the
corpus's account of itself, and it was silent where a reader needed it to
speak.**

**R8.3** asked whether a `sync` killed part way is always recovered by the next
one, and offered a reading: *the manifest lands last, so a corpus killed mid-run
is wholly old, and the next sync rebuilds it.* That is right for two of the
three kill points and wrong for the third, and the wrong one loses data.

**R7** asked for a title. The manifest names an artefact by its path —
`feed/2026-09-05/a1b2.html` — which is not a name to put on a screen beside a
citation. Sora said it would otherwise open every document and read the first
line, and named the objection itself: *that is the manifest guessing done by
somebody who cannot see the front matter.*

## The kill points, measured

```text
during staging          destination untouched; next begin() clears it        safe
during promote          documents newer than the manifest; retain() re-converts   safe
after promote,          the withdrawal never happens, and the new manifest
before withdraw         does not list what was to be withdrawn               LOST
```

The third leaves the deleted document on the disk and out of the manifest.
`withdrawals()` compares the previous manifest against the new one, and the new
one has no record of it — so **no later run would ever consider it again**. It
is invisible to `musubi export`, which reads the manifest, and indexed by any
consumer that walks the folder, which is what `tsumugi` does. A corpus goes on
answering questions from a note its owner deleted, which is the exact failure
withdrawal exists to prevent.

Nothing detected it either. Every check in `musubi verify` asks whether what
the manifest names is present; none asked the other way.

## Decision

**A run finishes the withdrawal the last run started.** `Previous` carries
`withdrawn` as well as `written`, and `sync` holds the union. The recovery is
reading a field that was already there: `withdrawn` is assembled and written
into the manifest **before** the promotion, so the *intent* survives the crash
that interrupted the *act*.

**`musubi verify` reports a corpus larger than its own account** — `manifest 6`,
one fault per file under `documents/` or `traces/` the manifest does not name.
The staging area is not among them: it is musubi's own, and a run that died
while staging leaves one for the next `begin()` to clear.

**An artefact carries a `title`**: the document's own front-matter `title`, else
its first heading, else `null`. The heading rule is the *reader's* rule —
`tsumugi` takes a title from the first heading when front matter does not give
one — so a corpus and its consumer name the same document the same way by
agreement rather than by luck.

**`null`, and never the empty string.** A document that states `title:` with
nothing after it has said something; one that says nothing has not. Sora falls
back to the source URL's host name for the second and would fall back wrongly
for the first if they arrived the same.

**Not in `run_id`.** The title is derived from the artefact's own text, which
`content_hash` already covers. In the id it would change every existing corpus
on upgrade, and with it every journal's parent chain. The regenerated
conformance fixture confirms it: same id, new field.

## Consequences

- Sora's reading of R8.3 is corrected in the response rather than confirmed:
  two of three kill points were safe, the third was not, and it is now.
- `musubi.sync-manifest/1-draft` gains a required, nullable `title`. Draft, so
  the version does not move ([ADR-0024](0024-a-field-added-is-a-new-contract.md)).
- `verify` runs eight checks on a two-artefact corpus rather than seven.
- A consumer no longer has to open a document to name it.

## What it costs

**The orphan check reads the whole directory tree on every `verify`.** For a
corpus of ten thousand artefacts that is one walk beside ten thousand hashings,
so it is not the expensive part — but `verify` was previously bounded by what
the manifest listed, and it is now bounded by what is on the disk. A corpus
somebody dropped a large unrelated folder into pays for that folder.

**A false orphan is possible and is the user's file.** Anything under
`documents/` that musubi did not write is reported, including something the
owner put there deliberately. That is the right default — the alternative is a
check that cannot see the failure it exists for — but the fault says *is in the
corpus and not in the manifest* rather than *should not be here*, because
musubi does not know which it is.

**And the title is the document's claim, not a fact about it.** A note whose
first heading is `# TODO` is titled `TODO` in the manifest. musubi is repeating
what the document says, which is the same standing every other front-matter
value has here, and a consumer that wants better has the text.
