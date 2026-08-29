# 7. musubi reads exports, never services

**Status:** accepted

Generalised from `kiseki`'s rule that the core reads documents rather than
devices (`docs/records.md`, ADR-0059).

## Context

The category musubi sits in is "connectors", and every product in it is an API
client. It holds an OAuth token per service, polls or subscribes, and keeps a
local mirror in step with a remote system.

That shape brings three costs, and the third is the one that decides it.

**It breaks.** An API changes and the connector is wrong until somebody fixes it.
Every integration in the category carries a maintenance tax proportional to the
number of vendors it touches.

**It owns credentials.** A tool with a token for Slack, Notion, Google and a mail
provider is a tool that, if compromised, is a compromise of all four. It also
means the tool must have a credential store, which is the single most attacked
component in any local application.

**It cannot be checked.** A program that opens sockets to make its product work
cannot prove it does not open sockets for anything else. Every privacy claim it
makes is a promise about intent. `kiseki` made the opposite bet and can point at
a build matrix asserting no socket opens; that assertion is worth more than any
sentence in a README, and it is only available to a program that needs no network
at all.

## Decision

**musubi has no network code, anywhere, including in adapters.**

`import-linter` and an AST test forbid `socket`, `ssl`, `http`, `urllib`,
`ftplib`, `smtplib` and `asyncio` across the whole package. There is no allow-list
and no adapter carve-out, because unlike `tsumugi` — which needs an outbound path
to ask a model a question — musubi needs nothing from anywhere.

The input is what the owner already has on their disk: an export archive, a
synced folder, a vault, a maildir. The owner exports; musubi reads.

And it reads **a folder the owner named**. Never the home directory, never "every
document on this machine". `kiseki` states the reason exactly: a source that finds
documents somebody forgot they had is a search tool, and this is not one.

## Consequences

There is no token store, no OAuth flow, no rate limiter, no retry policy, no
webhook receiver and no API version to chase. A large fraction of what a connector
product normally is does not exist here, and none of it can break.

It also makes the enterprise argument simple in a way a networked tool cannot
match. "It cannot send your Notion workspace anywhere" is checkable by reading the
import graph, in a build log, on the buyer's own CI.

## What it costs

**The owner has to export.** This is the product's main adoption cost and it is
real: an export is a manual step, it is slow for a large workspace, and some
services make it awkward on purpose. musubi cannot be "always in sync" and does
not claim to be.

What softens it is that every service worth ingesting supports export as a
documented path — Slack, Notion, Google Takeout, Apple Health, most mail clients —
and scheduling that export is the owner's business, which is exactly where the
credential should live.

**No push, so a re-sync is a re-read.** musubi diffs rather than receives events,
which is why ADR-0006 exists and why the cost of a re-read is a number that gets
measured.

**A whole class of source is out of reach.** Anything with no export — a service
that only has an API — is not ingestible by musubi and will not become so. If
that turns out to be where the value is, the answer is a separate program that
exports, run by the owner, whose output musubi reads. Not a socket in here.
