# 0043. A segment is a row of numbers, and the tiling supplies the rest

**Status:** accepted
**Date:** 2026-09-09
**Context:** [#76](https://github.com/Nananananana/musubi/issues/76), [ADR-0004], [ADR-0024], [ADR-0041]

## The problem

The map is the thing musubi exists to produce, and on a real corpus it was
**10.7 times the size of the documents it describes**. The design named that as
a falsification condition of the whole idea:

> **The trace map is too big.** If a map routinely exceeds its document, the
> guarantee costs more storage than the corpus. Measured in v0.4; the fix is
> converter-side, and if there is no fix, the map becomes optional and the
> project is much less interesting.

Minifying the sidecar took it to 4.9x, and the prediction that the rest was
converter-side turned out to be wrong. A map was **within 3% of its own minified
size**, so what remained was not whitespace and not formatting: it was the
segments, at about 71 bytes each, nearly all of it the same five key names and
the same rule strings written out once per segment.

```text
{"out":[0,3],"src":[0,3],"kind":"verbatim"}                            43 bytes
{"out":[3,4],"src":[3,5],"kind":"transformed","rule":"line_ending"}    67 bytes
```

Two things were measured before choosing, and one of them was wrong.

**Merging adjacent removals looked free and bought nothing.** A removal produces
no output, so no query can land inside one and merging two loses no precision —
unlike merging `transformed` runs, which #76 correctly warns changes what
`source_span_of` answers. On the worst real case, 68 of 81 segments were
zero-length removals, and **not one adjacent pair shared a rule**: they alternate
`markup.tag.a`, `boilerplate.nav`, `markup.tag.a`. Merging across rules would
drop the attribution [ADR-0005] exists for. Measured, discarded.

## Decision

**A segment is written as a row of numbers, with the names and the strings
hoisted into tables the file carries.**

```json
"segment_fields": ["out_length", "src_start", "src_end", "kind", "rule"],
"kinds": ["verbatim", "transformed", "synthetic", "removal"],
"rules": ["line_ending"],
"segments": [[3, 0, 3, 0, null], [1, 3, 5, 1, 0]]
```

Nothing about what a segment *means* changes: same spans, same kinds, same
rules, and the same answer to `source_span_of` at every offset. This is a
change of notation.

**The output start is not stored, because the tiling already determines it.**
[ADR-0004]'s invariant is that the segments cover every character of the
artefact exactly once, in order, so each one starts where the last ended.

That is the part worth having beyond the bytes: an invariant that was a rule
somebody checked becomes a shape the format cannot express a violation of. A map
with a gap or an overlap has nowhere to put it.

**The tables travel in the file.** A reader uses the file's own `kinds` and
`rules`, not an order it remembers. That is [ADR-0024]'s rule applied before it
costs anything: if the order lived only in the code, a kind added to the enum
later would reinterpret every map already written — yesterday's `removal`
becoming today's something-else, silently, at every offset. It costs about 120
bytes a file.

**`segment_fields` is checked, not honoured.** A file naming a different layout
is refused rather than rearranged. Resolving an offset against a guessed column
order is precisely the confident wrong answer this project exists to avoid.

**Both shapes are read.** An element that is an object is the older form. A
reader that required the new one would stop resolving every corpus written
before today, which is the mistake [ADR-0041] caught the last time a field
moved, and `kiseki-notes` has been syncing against one for months.

## What it buys

Measured with `tools/scaling.py --only map`, on the same generated corpus as
the original issue:

```text
                     filed      after minifying      now
  traces/            10.7x            4.9x           1.5x
  everything         11.9x            6.1x           2.7x
  one .html map      14.0x            6.4x           1.8x
  one .md map         7.6x            3.4x           1.1x
```

A segment costs 18.9 bytes against 71. The falsification condition asked
whether a map *routinely exceeds its document*; at 1.5x it still exceeds it, and
it is now the same order of magnitude as the corpus rather than an order above.
That is a different sentence about the project, and it is the honest one: this
does not make the map free, it makes it affordable.

## What it costs

**A reviewer can no longer open a map and read it.** `[3, 0, 3, 0, null]` needs
the header above it to mean anything. `_render_trace` used to say *indented
rather than minified: this is the file a reviewer opens*, and minifying already
spent most of that; this spends the rest. `segment_fields` and `kinds` in the
file are what is left of it, and they are why those tables are written out
rather than left to the contract.

**A consumer outside musubi has to be told.** `musubi.trace-map/1-draft` is a
draft and [ADR-0024] permits a draft to change, which is the whole reason the
freeze has not happened. It is still a shape somebody may have written a reader
against. The contract document says both shapes are valid and `musubi trace`,
`musubi verify` and the MCP server all read either, so a consumer using those
sees nothing.

**Half of an invariant stopped being tested and started being structural.**
`test_trace_1` used to assert that each segment starts where the last ended.
Against a derived start, that would be a test of the arithmetic that derived it
— a green about nothing, and one this repository would have written without
noticing. The test now asserts the part that can still be wrong, which is the
total, and says in as many words which half moved and where the other half is
enforced for maps read in the older shape.

**Two decoders would be worse than one.** The writer and the reader are the same
module for the reason the floors register and its report are one function: two
that are supposed to agree and do not is not a failure anybody sees, it is
citations landing in the wrong place. The tests use that module too, rather than
a third decoder written in the test file.

## Consequences

The map stays mandatory. #76's own framing was that if there were no fix, *the
map becomes optional and the project is much less interesting*; there was a fix,
and it was not where the roadmap predicted.

The prediction that failed is worth keeping: §10 said **the fix is
converter-side**. It was not. The converter emits the same segments it always
did; what changed is how they are written down. A guess about where a cost lives
is a guess, and this one was measured before it was acted on — twice, because
the first thing measured turned out to buy nothing at all.

[ADR-0004]: 0004-a-conversion-carries-a-map-back-to-its-source.md
[ADR-0005]: 0005-say-what-was-removed-and-by-which-rule.md
[ADR-0024]: 0024-a-field-added-is-a-new-contract.md
[ADR-0041]: 0041-an-artefact-is-named-for-what-musubi-wrote.md
