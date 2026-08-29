# 8. A credential stops the run, and musubi does not redact it

**Status:** accepted

## Context

The data musubi reads contains secrets. Not hypothetically — a `.env` committed
into a notes vault, an API key pasted into a Slack channel at 2am, a database URL
in a runbook, a private key in an attachment. musubi's output is a folder built
to be fed to a language model, so a secret that survives ingestion is a secret on
its way out of the building.

There are three possible behaviours and only one of them is defensible.

**Skip the unit.** The corpus silently loses a document. Nobody reads the log of
an unattended job, so the hole is discovered — if ever — as a wrong answer with
no explanation.

**Redact and continue.** This requires being right about *where* the secret is,
character for character. Getting the boundary wrong writes most of the key into
the corpus, which is worse than useless because it looks handled. It also makes
musubi a redactor, and there is already one in this family that does it properly.

**Stop.** Nothing is promoted, and a person is looking at the problem before the
data moves.

## Decision

**A credential stops the whole run. musubi refuses; it does not redact.**

A run writes into a staging area and promotes atomically on success. A screener
hit means nothing is promoted — not the offending unit and not the ones that
already converted cleanly. The error names the source, the unit key and the rule
that fired, and never the value.

The division of labour with `mamori` is deliberate. **Refusing requires only
being right that a secret exists. Redacting requires being right about exactly
where it starts and ends**, and those are very different difficulties. musubi
takes the easy half and leaves the hard half to the library built for it.

An owner who has looked and decided a hit is a false positive passes
`--allow <rule>:<unit_key>`, and the allowance is recorded in the manifest. An
exemption nobody can see is an exemption that outlives its reason.

### The screener, and what it is actually worth

The default screener is stdlib-only: high-signal patterns for the credential
formats that have them, plus a Shannon-entropy filter for the ones that do not.

That combination has a known ceiling, and it is stated rather than discovered
later. On the public CredData benchmark, entropy-based filtering reaches roughly
70% recall; the 2026 state of the art replaces entropy with a byte-pair-encoding
"token efficiency" measure and reports around 98.6% recall at materially better
precision. musubi cannot ship a BPE tokenizer under ADR-0001, so **musubi's
built-in screener is approximately a 70%-recall instrument and the documentation
says so on the same page as the guarantee.**

The upgrade path is a `Screener` port with an optional `mamori` adapter, which is
the only place in musubi allowed to know `mamori` exists. musubi measures its own
screener against a labelled corpus in v0.4 and publishes the number.

## Consequences

Precision matters more than recall for the *default* rules, because a false
positive stops a run and a run that cries wolf gets `--allow`-ed reflexively.
The built-in ruleset is therefore conservative, the entropy threshold is
deliberately high, and everything looser is opt-in.

Fail-closed also applies to the screener itself: if a configured screener cannot
be constructed, the run stops rather than proceeding unscreened.

## What it costs

A corpus with one legitimate-looking high-entropy string in it — a base64 test
fixture, a checksum table, a UUID column — cannot be synced until somebody
allows it. That friction is on purpose and it is still friction, and it is the
most likely reason a user gets annoyed with musubi in its first week.

And a ~70% instrument means roughly three in ten secrets pass. musubi's promise
is therefore narrow and honest: it is a gate that catches the common shapes and
stops when it does, not a guarantee that nothing sensitive reaches the corpus.
Anyone needing that guarantee runs `mamori` over the output, which is what
`mamori` is.
