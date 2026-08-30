# 16. A cleansing rule is a matcher, not a regular expression

**Status:** accepted. Refines
[ADR-0009](0009-cleansing-rules-are-data.md), which said rules are data and left
open what a rule's `pattern` field contains.

## Context

[ADR-0009](0009-cleansing-rules-are-data.md) sketched a rule with a `pattern`
field and an example that was a regular expression. Writing the first ruleset
made two things obvious.

**The expressive power is not needed.** The reference catalogue for this problem
is ClearURLs, whose global rules are the industry's accumulated answer to *what
is a tracking parameter*. Read as a list, almost all of it is literals and
prefixes: `fbclid`, `gclid`, `msclkid`, `mkt_tok`, `_openstat`, `twclid`;
`utm_*`, `ga_*`, `otm_*`, `vn_*`; and a handful of small alternations
(`mc_(eid|cid|tc)`, `itm_(campaign|medium|source)`) that are three literals each.
The regex syntax is a compact notation for a list, not a use of regular
languages.

**The cost is not small.** Python's `re` is a backtracking engine with no
timeout, and RE2 — the standard answer, which guarantees linear time by
forbidding backtracking — is not available under
[ADR-0001](0001-the-domain-depends-on-nothing.md). The literature is consistent
that with a backtracking engine and patterns you do not control, catastrophic
backtracking can be *mitigated* and not *removed*; Stack Overflow in 2016 and
Cloudflare in 2019 are the well-known outages.

Now put that next to what musubi is. Rules are data users may edit (ADR-0009).
musubi runs unattended over a folder nobody is watching. The documents are
arbitrary — a corpus contains code samples, base64 blobs, minified JavaScript
somebody pasted into a note. That is a user-editable pattern meeting adversarial
input inside an unsupervised loop, which is the exact shape of the problem.

## Decision

**A rule matches a *parsed parameter name*, by one of two forms: `exact` or
`prefix`.** There is no regular expression anywhere in the cleanser.

```text
id           tracking.utm
kind         tracking_parameter
match        prefix
value        utm_
evidence     Google Analytics campaign parameters; ClearURLs global rule utm(?:_[a-z_]*)?
since        2026-08-30
```

Matching is `str.startswith` or `==` against a name musubi has already parsed
out of a URL's query string. It is O(length of the name), it cannot backtrack,
and no ruleset anybody writes can make a sync hang.

Restricting the language *removes* the failure class rather than mitigating it.
That is the whole trade, and it is available only because the catalogue turned
out to be a list.

**The URL is parsed structurally, not matched.** A hand-written linear scanner
finds URLs, splits the query at `&`, and hands each name to the rules. `urllib`
is not used — not only because ADR-0007 forbids it wholesale, but because it
returns *values* and musubi needs *offsets*: a removal is a span in the source
(ADR-0005) and a discontinuity in the trace map (ADR-0004), and neither can be
built from a parsed dictionary. It is ADR-0004's argument about converters,
arriving again one layer down.

### What is deliberately not adopted from the catalogue

ClearURLs carries `[a-z]?mc`, which strips `mc` and every single letter followed
by `mc`. It would remove `amc`, `bmc` and twenty-four others from any URL that
had them. In a browser that is a tolerable false positive; in a corpus it
silently changes a link in somebody's notes. It is left out, and this paragraph
is the record of the decision rather than an absence nobody can find.

The catalogue's `(?:%3F)?` prefixes exist to catch doubly-encoded URLs in a
browser's address bar. musubi parses structurally, so it has no equivalent
problem and no equivalent rule.

## Consequences

A rule is reviewable by somebody who does not read regular expressions, which is
most of the people who would want to audit what an ingestion tool removes from
their documents. `musubi rules --list` prints a table rather than a pattern
language.

The matcher is total and deterministic: exact before prefix, then longest prefix,
then rule id. Two rules can both match, and which one is reported has to be the
same on every run (ADR-0003) rather than a property of dictionary order.

## What it costs

**A rule that genuinely needs a regular expression cannot be written.** The
honest answer for the first one that does is a new `match` form with its own
bounded semantics — `suffix`, or `contains`, or an explicit alternation list —
not an escape hatch back to `re`. Each new form is a decision with a cost, which
is the correct amount of friction.

**Some catalogue entries take several rules.** `mc_(eid|cid|tc)` becomes three,
and the ruleset is longer to read than the regex it came from. It is also
greppable, countable, and individually attributable when one of them turns out
to be wrong, which is what ADR-0005's per-rule accounting is for.
