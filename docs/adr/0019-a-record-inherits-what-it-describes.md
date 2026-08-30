# 19. A record inherits the classification of what it describes

**Status:** accepted

The criterion is `mamori`'s, from its ADR-0032, and it is taken here with thanks:

> A record may state only what is derivable from the artefact it describes.

## Context

musubi writes three things into a destination: `documents/`, `traces/` and
`manifest.json`. Separating the trees was right for its own reason — a sidecar
beside a document is ingested *as* a document, because `tsumugi`'s corpus walk
does not skip `.musubi` and its parser registry claims `.json`
([ADR-0013](0013-one-output-contract-and-the-consumer-adapts.md)). But
separating them creates a thing that can travel alone, and nobody had asked what
it says when it does.

**Apply the criterion to a trace map.** Its contents are derivable from the
*pair* — the artefact and the source. To a reader holding the artefact, every
offset in it is a correspondence they could have computed. To a reader holding
neither, it is a new disclosure, and a substantial one:

- **The owner's filenames and folder structure**, in full, in `artefact.path`
  and `source.unit_key`. `kiseki`'s NoteRecord contract refuses to carry a
  filename at all, and states why in a sentence musubi cannot improve on:
  *`2026-resignation.md` says as much as its contents.*
- **The document's silhouette.** A segment list is the length and position of
  every paragraph, every line break, every link. `mamori`'s objection to
  publishing lengths applies exactly: *a length is the shape of a value.*
- **What was in it.** A segment's `rule` says `tracking.mc-eid`, which says the
  owner is on a Mailchimp list; `referral.ref`, which says there were affiliate
  links.

So the honest answer is that a trace map is **not** the safe half of the output.
It is at least as sensitive as the document it describes, and it is the half
most likely to be shared first *because it looks like metadata* — which is the
failure `mamori`'s ADR names.

**Apply the criterion to the manifest.** `removals` and `skipped` are the
appealable parts and are meant to be read
([ADR-0005](0005-say-what-was-removed-and-by-which-rule.md)). A removal records
a tracking parameter, whose length is the shape of a marketing tag; the span is
what makes an appeal possible, and it earns its place.

`findings` is different in kind, and the difference is what this ADR changes. A
finding points at a credential that is **still in the owner's source file and
still valid**. A manifest carrying its offset and its length is a document that
says *there is an AWS key in `notes/setup.md`, twenty characters long, starting
at 44*. The owner does not need that to act — they will open the file and search
— and it is precisely the targeting information an attacker would want.

## Decision

**The destination is one classification.** `documents/`, `traces/` and
`manifest.json` are the same secret. A trace map inherits the classification of
the documents it describes, and it is never the thing shared first on the
grounds that it holds no values.

**A finding in the manifest names what and where by unit, and no more.** The
rule, the label, the unit key, and the hash. **No span and no length** — the
`Finding` value keeps both, and the terminal report prints them, because a
person looking at their own screen is the audience ADR-0008 stops the run for.
It is the same split ADR-0005 already made for removals — values to the
terminal, hashes to the file — carried to the record that points at something
still live.

**A trace map does not carry the `run_id`**, and the omission is deliberate. It
would make map and manifest checkable as a pair, and it would also change every
trace map on every run that changed anything, so promotion would rewrite the
whole corpus and [ADR-0006](0006-the-unit-of-sync-is-the-record.md)'s
incrementality would be gone. The pairing that matters is checkable anyway: a
map carries `artefact.content_hash`, so a reader holding the artefact can
confirm the map is about the bytes in front of them.

## Consequences

`docs/contracts.md` states the classification where a consumer reads it, and
`.gitignore` treats a whole destination as the corpus rather than matching a few
filenames.

The rule generalises. Any future record — a redundancy report, an evaluation
output — is classified by what it describes, and the question *what does this
say to somebody who does not have the thing it is about* gets asked before it is
written rather than after it has been shared.

## What it costs

**A consumer wanting to highlight a finding in place has to re-screen.** It has
the source, so that is cheap, and the alternative is publishing an offset into a
live secret to save it the work.

**Nothing in the tooling enforces the classification.** musubi can write the
sentence and cannot stop somebody attaching `traces/` to an issue. What it can
do is make the sentence findable at the moment the folder is looked at, which is
what the docs and the ignore rules are for.
