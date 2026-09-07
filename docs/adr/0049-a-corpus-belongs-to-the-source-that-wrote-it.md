# 0049. A corpus belongs to the source that wrote it

**Status:** accepted
**Date:** 2026-09-10
**Context:** [ADR-0002], [ADR-0021], [ADR-0046], [ADR-0048]

## The defect

Syncing a second source into a destination **deleted the first source's
documents**, silently.

```text
  after syncing A: ['from-a.md']
  after syncing B: ['from-b.md']
  withdrawn by B's run: ('documents/from-a.md', 'traces/from-a.md.json')
```

Exit 0. Nothing on stderr. `musubi verify` passed afterwards, because the
corpus really was consistent with the manifest that had just replaced it.

It follows from the design rather than from a bug in it. The manifest is an
account of **one run** ([ADR-0002]), and withdrawal takes out whatever the
previous manifest recorded that this one does not ([ADR-0021]). A second source
pointed at the same folder does not add to a corpus; it replaces one.

**That is a reasonable design and it was written down nowhere.** So the first
person to type the wrong `--into` finds it out by losing a corpus, and the
command that exists to prevent exactly this — `plan`, which reports what would
be deleted — reported the deletion as ordinary withdrawal, because from inside
the run that is what it was.

## Decision

**A sync whose destination was written by a different source is refused.**

```text
DifferentSourceError: this corpus was written by vault and is being synced by
'filesystem'. A destination belongs to one source: the manifest is an account
of one run, so this run would take out every document the other source wrote
(2 file(s)). Nothing was written and nothing was deleted. Pass --withdraw-all
to replace the corpus, or sync into a different folder.
```

The same shape as the two refusals beside it. The two readings — *I am
replacing this corpus* and *I meant a different folder* — are indistinguishable
from here, and one of them destroys work, so a person decides.
`--withdraw-all` is the gesture they already have for saying they have looked,
and the refusal states the count so that agreeing to it is agreeing to
something.

**Not** the other available fix. Withdrawal could have been narrowed to the
syncing source's own artefacts, since `source_id` is recorded per artefact —
and that would make a two-source corpus possible. It would also make one that
**fails `musubi verify`**: the manifest describes one run, so the other
source's documents become orphans the moment they are not withdrawn. Supporting
several sources in a destination is a real design and this is not it; refusing
is the honest answer until somebody does that work.

## What it costs

**A first sync after upgrading with a source name that has changed is
refused.** Re-syncing a folder as `filesystem` that was synced as `obsidian`
now stops. That is the same class of mistake and the same answer, and it costs
one `--withdraw-all` to say so deliberately.

**A destination cannot be shared, and the docs now say so** rather than
leaving it to be discovered. `musubi export` is the join: a line per document
from each corpus, with the `corpus` field on every line saying which it came
from.

**One more refusal for a caller to know about**, which is what the catalogue
in [ADR-0046] is for. It carries `DifferentSourceError` with `retryable: false`,
so `sora` records it and does not retry.

## And the guard it broke on the way in

`main` decided a refusal from a hand-written tuple of exception classes:

```python
except (CredentialFoundError, EmptySourceError, EverythingSkippedError) as refusal:
    return _stderr(..., REFUSED)
```

It named **two of the three refusals the day a third arrived**. So the new
refusal — which had just stopped a corpus being deleted — exited **1**, which
is the code that tells an orchestrator to *retry*. A test caught it, and the
fix is the same one this session keeps arriving at: the exit code is read out
of the published catalogue, so `musubi errors --json` and the process cannot
disagree about what a failure means.

That is the fourth hand-written list of cases to go stale in a week
([ADR-0047] has two of the others, [ADR-0048] a third). The pattern is not that
people forget; it is that a list beside a thing has no reason to change when
the thing does.

[ADR-0002]: 0002-the-sync-manifest-is-a-document.md
[ADR-0021]: 0021-an-empty-source-is-not-a-deletion.md
[ADR-0046]: 0046-a-failure-that-a-program-can-name.md
[ADR-0047]: 0047-a-fourth-contract-that-three-documents-knew-nothing-about.md
[ADR-0048]: 0048-a-record-that-does-not-say-is-not-a-record-that-says-no.md
