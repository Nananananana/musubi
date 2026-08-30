# 14. The key is normalized, the content never is

**Status:** accepted

## Context

[ADR-0006](0006-the-unit-of-sync-is-the-record.md) makes `(source_id, unit_key)`
the identity of everything musubi tracks, and [ADR-0003](0003-a-sync-is-reproducible.md)
promises the same input produces the same output on any machine. There is a
Unicode problem sitting exactly between those two, and it is not hypothetical.

**macOS decomposes filenames.** HFS+ and APFS hand back NFD — `é` as `e` plus a
combining acute — while Windows and Linux use NFC, a single code point. A note
called `café.md` in an Obsidian vault has a different byte-level name depending
on which machine wrote it, and the two are the same name to every human who
looks at it. Git carries a `core.precomposeunicode` setting for precisely this,
which is the strongest evidence available that it is a real and recurring
problem rather than a corner case: a project of git's maturity does not add a
configuration option for something rare.

A `unit_key` derived from the raw name inherits all of it. The same vault synced
from a laptop and from a desktop produces two corpora with disjoint keys. Every
re-sync from the other machine looks like a full rewrite: everything deleted,
everything added, incremental sync gone, and `kiseki-notes`' path-hash
`reference` ([ADR-0013](0013-one-output-contract-and-the-consumer-adapts.md))
different for every note.

There is a matching temptation, and it is a trap: normalize the *content* too.
It would make matching easier for the cleansing rules and it is what a text
pipeline usually does.

## Decision

**Unit keys are normalized to NFC. Content is never normalized at all.**

A key is built from parts rather than parsed from a path string:

- each part is normalized to NFC;
- parts are joined with `/`, so a key means the same thing on both sides of the
  platform divide and no separator has to be guessed;
- an empty part, a `.`, a `..` or a part containing a separator is **refused** —
  a key becomes an output filename under ADR-0013, and a key that can climb out
  of its own directory is a path traversal waiting for a corpus to be built
  somewhere writable.

Two units whose keys collide after normalization **stop the run**. Picking one
silently drops a document, which is the failure mode this project exists to make
impossible.

**Case is deliberately untouched.** Folding it would merge `README.md` and
`readme.md`, which are two different files on Linux and two different documents
in somebody's corpus. Case-insensitive filesystems are a separate problem with a
separate answer, and conflating the two would lose data to solve a nuisance.

### And why the content is left alone

Normalizing the owner's text is an unrequested rewrite of what they wrote. NFC
would silently change characters they chose; NFKC — the form that makes matching
easiest — would turn `ｕｒｌ` into `url`, `①` into `1` and `㍿` into a company
suffix, in a corpus that is supposed to be *their documents*.

It would also move every offset. The trace map would faithfully record the whole
file as `transformed` rather than `verbatim`, which is exactly right and is the
point: traceable coverage would collapse across every Japanese document in the
corpus, and it would be telling the truth. A transformation nobody asked for is
still a transformation.

So the line is: **identifiers are normalized because they are musubi's, content
is not because it is the owner's.** Where a cleansing rule needs to match
across forms, it normalizes a copy for matching and removes from the original —
the same discipline `mamori` uses for detection.

## Consequences

`unit_key` is a function, not a string a source hands over, and every source
adapter goes through it. The manifest records the derivation so a reader can see
which sources have the weak `path` form (ADR-0006).

Refusing `..` in a key means the traversal check is done once, in the domain,
rather than in each emitter — where it would eventually be forgotten in one.

## What it costs

**Two files whose names differ only by normalization cannot both be ingested.**
On Linux that is legal and musubi will stop rather than pick. It is the right
failure — the alternative is a corpus that silently contains one of them — but
it is a failure, and somebody will hit it.

**musubi cannot round-trip a name back to its original bytes.** A key says
`café.md` in NFC; the file on the macOS disk is NFD. Anything resolving a key
back to a file has to search rather than concatenate, and the trace map records
the source by key rather than by the exact bytes of its name.
