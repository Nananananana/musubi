# 6. The unit of sync is the record, not the file

**Status:** accepted

## Context

Idempotence is the property the spec asks for first: syncing the same data twice
must not dirty the store. The obvious implementation is to hash each file and
skip the ones that have not changed.

It does not survive contact with real exports.

A **Slack export** is one zip holding tens of thousands of messages in per-day
JSON files, plus `users.json`, `channels.json` and integration logs. Re-exporting
the same workspace a week later produces a different archive byte for byte — new
files at the end, regenerated metadata, a different zip ordering — while
essentially every message in it is unchanged. File hashing reports that
everything changed.

A **Notion export** is worse in a different way. Nested pages come out as
Markdown files whose names are the page title plus a 32-character UUID, and the
UUID is regenerated per export. Every cross-page link points at those filenames.
Re-export and every path changes, every link changes, and nothing the owner wrote
changed at all.

An **Obsidian vault** is the case where file hashing works perfectly, which is
why the mistake is easy to make: the first source anyone implements behaves.

## Decision

**A source yields records, and a record — not a file — is what musubi tracks.**

Every record carries:

- `unit_key`: an identifier stable *across exports of the same data*. The channel
  id plus the message timestamp for Slack; the Notion page id parsed out of the
  filename rather than the filename; the vault-relative path for a note; the
  Message-ID for mail.
- `content_hash`: `sha256` over the record's normalized content, and over nothing
  else. Not over the file. Not including the export's own timestamps, the zip
  entry metadata, or the filename UUID.

Identity is `(source_id, unit_key)`. Change detection is `content_hash`. A
re-export that produces identical records produces an empty diff, whatever the
bytes of the archive did.

**A source adapter must state its key derivation, and it goes in the manifest.**
A source that cannot produce a stable key is not implemented until it can, or it
declares the fallback explicitly.

## Consequences

The known fallback is a folder of files with no internal identity — a shelf of
scanned PDFs, a directory of exported HTML. There the key is the path relative to
the declared root, and the consequence is stated rather than hidden: **moving a
file looks like a delete plus an add.** The manifest names the derivation as
`path`, so a reader can see which sources have that weakness.

Content addressing per record also makes near-duplicate detection (ADR-0011)
cheap to reach: the exact-duplicate case is already free, and only the fuzzy case
needs new machinery.

## What it costs

Every source adapter is more work than a directory walk, and every one needs its
own argument about identity. That is the point — the argument is where the
correctness is — but it means the cost of a new source is dominated by thinking
rather than by parsing.

Re-reading is not free, either. musubi cannot trust mtime (ADR-0003), so
detecting that nothing changed requires reading and hashing every record. Whether
that is affordable is a measurement, not an assumption: `tsumugi` found its
re-ingest was 5.5x cheaper than a cold build and that this, not the cold number,
was the one that mattered. musubi measures the same ratio, in v0.4, and reports
it per source.

Content-defined chunking (FastCDC and its successors) is the technique that would
make a large single-file source incrementally cheap. It is deliberately not here:
the record-level split already handles every export whose shape is known, and CDC
earns its complexity only for large opaque files, which musubi has not yet been
shown to have.
