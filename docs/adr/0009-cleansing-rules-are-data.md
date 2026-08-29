# 9. Cleansing rules are data, and each one names its evidence

**Status:** accepted

The shape is `mamori`'s language packs (ADR-0008), applied to a different kind of
rule.

## Context

What counts as noise is per-source and it changes. Notion emits block UUIDs and
title-plus-UUID filenames. Slack emits `<@U024BE7LH>` mentions, join and leave
messages, and internal file ids. Web pages carry `utm_*`, `fbclid`, `gclid`,
`mc_eid` and a long tail of vendor parameters. Mail carries tracking pixels and
list-unsubscribe scaffolding. Every one of these is a small, specific, verifiable
fact about a format.

Written as code, they become a growing pile of regular expressions in a module
nobody wants to touch, with no way to answer the two questions that actually get
asked: *why is this being removed?* and *is this rule still correct?*

The reference catalogue for the URL half of the problem is ClearURLs, whose
rule set is publicly maintained and covers the vendor tail properly. Depending on
it is not available (ADR-0001) and would be the wrong shape anyway — it is a
browser extension's data, updated on its own schedule.

## Decision

**A cleansing rule is a data record, and the ruleset is a versioned, vendored
artefact.**

```text
id           tracking.utm
kind         tracking_parameter
applies_to   url_query
pattern      ^utm_[a-z_]+$
evidence     Google Analytics campaign parameters; ClearURLs `utm_*` family
since        2026-08-30
```

- `evidence` is required. A rule with no stated reason for existing cannot be
  reviewed by anyone who was not there when it was written, and every rule
  outlives that person.
- `since` is required, so staleness is measurable. `musubi rules --stale` names
  rules not reviewed within a year.
- The vendored ruleset records where it was derived from and when, with
  attribution. Borrowing a catalogue somebody else maintains is right; pretending
  it was ours is not.

Adding a source's quirks is a data change and a test fixture, never a new branch
in the cleanser. The cleanser holds the algorithm; the packs hold the rules.

## Consequences

`musubi rules --list` prints the whole enforced policy, with reasons, without
running anything. That is the document a security reviewer actually wants, and it
is generated rather than written.

A rule is testable in isolation, and a false positive gets a regression fixture
naming the rule that produced it. Rules and fixtures grow together.

Per-source packs also keep the blast radius small: a Slack rule cannot fire on a
Notion page, because `applies_to` scopes it.

## What it costs

A vendored catalogue goes stale, and the tail of tracking parameters is long and
growing. musubi will lag the upstream catalogue, permanently. `since` and
`--stale` make that visible instead of invisible, which is the most this design
can honestly offer.

There is also a real risk of over-collection in the rule set: it is easy to add
"remove anything that looks like an id" and end up deleting content. ADR-0005 is
the counterweight — every rule's firings are counted and reported, so a rule that
eats a corpus is visible in the manifest before it is visible in a wrong answer.
