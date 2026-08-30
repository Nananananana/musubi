# 17. Entropy is a tier, not a default

**Status:** accepted. Corrects the configuration
[ADR-0008](0008-a-credential-stops-the-run.md) proposed, while keeping the
principle it stated.

## Context

[ADR-0008](0008-a-credential-stops-the-run.md) decided two things. The policy —
**a credential stops the whole run, and musubi does not redact** — stands
unchanged. The configuration it sketched does not: it said the default screener
would be *"high-signal patterns for the credential formats that have them, plus
a Shannon-entropy filter for the ones that do not."*

ADR-0008 also wrote down the principle that turns out to contradict its own
sketch:

> Precision matters more than recall for the *default* rules, because a false
> positive stops a run and a run that cries wolf gets `--allow`-ed reflexively.

Now put the measured numbers against that. On the public **CredData** benchmark,
entropy-only detection scores **21.1% precision and 70.4% recall**. Roughly four
out of five entropy hits are noise, and roughly three in ten real secrets slip
past anyway.

Under a stop-the-run policy, 21.1% precision is not a gate. It is an obstacle
course. Four out of five stops would be a base64 test fixture, a checksum table,
a UUID column, a minified bundle somebody pasted into a note — and `--allow`
would become reflexive inside the first week, at which point the gate protects
nothing at all. ADR-0008 predicted this failure mode and then configured for it.

Meanwhile the ground has moved the other way. GitHub's secret-scanning partner
programme has pushed the industry towards **identifiable token prefixes**, and
the adoption is not marginal: twenty-eight new detectors from fifteen providers
in March 2026 alone, and another wave in June. `ghp_`, `github_pat_`, `sk-ant-`,
`xoxb-`, `AKIA`, `sk_live_`, `AIza`, `npm_` — a prefix plus a fixed alphabet and
a length is a signature with precision near one *by construction*, because the
issuer designed it to be recognisable.

The 2026 answer to entropy's weakness is a byte-pair-encoding "token efficiency"
measure, which reports 98.6% recall at 57.3% precision on the same benchmark.
musubi cannot ship a BPE tokenizer under
[ADR-0001](0001-the-domain-depends-on-nothing.md), so that door is closed and
saying so is part of the record.

## Decision

**The default screener is signatures only. Entropy is a second tier, off by
default, and it prints its own numbers where it is turned on.**

A signature is a prefix, an alphabet and a minimum length — checked by a linear
scan, with no regular expression, for the same reason as
[ADR-0016](0016-a-rule-is-a-matcher-not-a-regular-expression.md). `AKIA`
followed by sixteen uppercase alphanumerics is an AWS access key id and is very
little else.

The entropy tier is available as `--screen entropy` and is documented with
"21.1% precision on CredData" beside the flag rather than in a footnote,
because somebody turning it on is choosing to trade stopped runs for coverage
and should be told the rate they are buying.

**No number is claimed for the default tier.** Its recall against a labelled
corpus is unmeasured, and this project does not write unmeasured numbers. The
measurement is scheduled in v0.4, along with the false-positive rate on a clean
corpus, and it may well argue for moving the boundary between the tiers.

Every signature carries `evidence` and `since`, exactly as a cleansing rule does
(ADR-0009). A credential format is a fact about a vendor, and vendors change
them.

## Consequences

The screener is honest about being narrow rather than broad and wrong. What it
catches, it catches almost certainly; what it misses, it misses visibly, and
`docs/` says which is which on the same page as the guarantee.

It also composes properly with the rest of the family. A user who needs real
coverage runs `mamori` over the output, which is a detection pipeline built for
exactly that and is measured for it. musubi's screener is the gate at the door,
not the search of the building.

## What it costs

**Recall, in an amount nobody has measured yet.** A secret with no recognisable
format — a password in a config line, a database URL with credentials inline, a
bare hex key — passes the default tier. That is a real hole and it is the reason
the entropy tier exists at all rather than being deleted.

**A signature list goes stale**, faster than a tracking-parameter list, because
vendors rotate formats and new vendors appear monthly. `since` makes the lag
measurable; it does not close it.

**A PEM header in a document about PEM headers stops the run.** Somebody
explaining key formats in their notes will hit it. That is the correct behaviour
under ADR-0008 — musubi cannot tell an explanation from the thing it explains —
and `--allow` exists for it, recorded in the manifest.
