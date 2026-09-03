# ADR-0026 — A prefix in the middle of a blob is not a credential

**Status:** accepted
**Date:** 2026-09-04
**Supersedes nothing.** Refines [ADR-0017]'s signature tier and is bound to
[ADR-0008]'s cost model.

## Context

[ADR-0017] chose signatures over entropy because entropy-only detection scores
21.1% precision on CredData, and [ADR-0008] makes every false positive expensive
in a specific way: **a hit stops the whole run**, nothing is promoted, and the
owner is looking at a sync that refused to happen.

`Signature.find` scanned for the prefix anywhere in the text and then counted
how far the alphabet ran. It did not ask what came *before* the prefix. So
`AIza` occurring by chance inside a base64url run, followed by enough characters
of the same alphabet, was reported as a Google API key — and a base64url run of
that length is not exotic. It is one embedded image.

Measured with `tools/screener_false_stops.py`, 300 blobs of 100,000 characters
per population, seed 20260904, over all 21 signatures:

| Population | Documents that would stop a run |
|---|---|
| base64 | 1.00% |
| **base64url** | **3.33%** |
| hex (lower) | 0.00% |
| hex (upper) | 0.00% |

Five different signatures fired: `google.api-key`, and four GitHub token forms.
Nothing fired on hex, because a hex alphabet cannot spell any of the prefixes.

100,000 characters is a 75 kB image pasted into a note. **One note in thirty
carrying one such image would stop a sync**, with a message naming a credential
that is not there, in a document the owner cannot see anything wrong with.

## Decision

A match is rejected when the character immediately before the prefix is one the
signature's **own body alphabet** would have accepted.

Not a generic word boundary. Per-signature, because the alphabets differ and the
difference is the whole point: AWS access key ids are uppercase and digits, so
`deadAKIA…` in a lowercase hex listing is still reported — the uppercase run
there is genuinely anomalous — while `DEADBEEFAKIA…` in an uppercase listing is
not, because `F` is a character that key format allows.

A signature with no body (`minimum=0`, a PEM header that names itself) has an
empty alphabet and is unaffected.

Re-measured, same seed, same populations: **0.00% on all four**.

## Consequences

- The failure mode that remains is the mirror one: a genuine prefix at the start
  of a *longer* token. `AKIA` + thirty characters still matches, because the
  scan has no maximum length. Vendor formats are fixed-length and a `maximum`
  would close it; that is a per-signature evidence change rather than a
  structural one, and is filed rather than done here.
- Recall is not measured by this. The number above is a **precision** number on
  a synthetic population, and `docs/measurements.md` — which v0.4 owes — is
  where recall against a labelled set belongs. This ADR claims the false stops
  went away; it does not claim nothing else did.
- A credential written with no separator after a run of its own alphabet is now
  missed. `keyAKIAIOSFODNN7EXAMPLE` is not reported. This is the deliberate
  trade, and it is the one every published scanner makes.

## What it costs

**A rule that used to be "the prefix appears" is now "the prefix starts
something", and the second one has a boundary somebody can be on the wrong side
of.** The scan is still linear and still cannot backtrack, so the cost is not
performance. It is that the signature list has grown a second property that has
to be right — the alphabet was previously only used to measure the body, and it
now also decides what counts as the beginning. A signature whose alphabet is
wider than the vendor's real one used to be merely imprecise; it now also
swallows its own matches.
