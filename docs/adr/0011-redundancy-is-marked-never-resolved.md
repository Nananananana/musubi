# 11. Redundancy is marked, never resolved

**Status:** accepted

Borrowed from `tsumugi` (ADR-0008 and ADR-0015), where the same rule is about
passages rather than documents.

## Context

An ingestion layer sees the same content more than once, constantly. The PDF
attached in Slack is also on the desktop. The Notion page was exported twice, in
March and in August. The meeting notes exist as an Obsidian note and as a mail
thread quoting them. A corpus built from three sources is a corpus with a large
overlap.

The obvious move is to deduplicate — pick a winner, drop the rest, hand
downstream a clean set. It is also the move that destroys information musubi has
no right to destroy.

Which copy is canonical is a question about the owner's intent, not about the
bytes. The March export may be the version they care about. The Slack copy may be
the one their colleague annotated. And "near-duplicate" is a threshold, so
resolving it means deleting a document on the strength of a similarity score,
irreversibly, unattended, in a job nobody watches.

The technique matters here too. SimHash is cheap and is fundamentally a
bag-of-words signature, which makes long documents spuriously similar to one
another — the well-known failure mode where documents past a few thousand
characters start colliding. MinHash over shingles with LSH banding gives a
tighter estimate of Jaccard similarity and is what large-corpus pipelines settle
on. Neither is exact, and neither should be trusted with a delete.

## Decision

**musubi marks redundancy. It never removes, merges or picks a winner.**

An exact duplicate — same `content_hash` under ADR-0006 — is reported as such and
both records are kept. A near duplicate is reported as a pair with its estimated
similarity, the method that produced it, and the parameters in force. Downstream
decides, or the owner does.

Determinism applies (ADR-0003): the permutations used for MinHash are fixed and
recorded in the manifest, so a similarity reported today re-derives tomorrow.

## Consequences

The corpus musubi produces is larger than a deduplicating pipeline's. That is the
correct trade for this family: `tsumugi` already marks and does not purge, and
handing it a set with unmarked deletions would silently remove the evidence that
two sources agreed — which is itself a fact worth having.

The exact-duplicate half is free, because records are already content-addressed.
Only the fuzzy half needs machinery, which is why it is deferred to a later
milestone and gated on a measurement rather than shipped alongside the spine.

## What it costs

A marked pair is a decision handed to the caller, and most callers will not want
to make it. musubi's answer is to make the marking good enough to act on
mechanically — the pair, the score, the method, both anchors — rather than to
make the decision on their behalf.

Fuzzy detection is also O(pairs) without banding and imprecise with it. The
parameters that trade recall against precision are published, and the measurement
that sets them is scheduled before the feature is promised.
