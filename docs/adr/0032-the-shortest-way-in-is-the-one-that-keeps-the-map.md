# ADR-0032 — The shortest way in is the one that keeps the map

**Status:** accepted
**Date:** 2026-09-04
**Adds a public surface. Constrained by [ADR-0008] and [ADR-0006], and by
[ADR-0027] for where its settings come from.**

## Context

```python
>>> import musubi
>>> musubi.__all__
['ContractError', 'ConversionError', 'CredentialFoundError', 'MusubiError',
 'SourceError', 'TraceError', '__version__']
```

Six exception classes and a version string. Using musubi from Python meant
importing from `application`, `infrastructure` and `ports`, constructing a
`Settings`, a source and an emitter, and knowing that `run(write=True)` stages
while `sync()` promotes. Pointing it at a single file was impossible: every
source takes a directory, and `musubi plan note.md` answers *is not a folder*.

What the neighbours do, and what everybody tries first:

```python
from markitdown import MarkItDown

MarkItDown().convert("report.pdf").text_content
```

**And the friction landed on exactly the wrong thing.** musubi's whole claim is
that a conversion carries a map back to its source. The only way to hold that
map was to run a sync into a folder and read a sidecar back off disk — so the
one feature that distinguishes musubi from every `bytes -> str` converter was
the feature hardest to reach, while the text, which everyone else also has, came
out first.

## Decision

**`musubi.convert(path)` returns text and the map, for one file, writing
nothing.**

```python
doc = musubi.convert("notes/gear.md")
doc.text, doc.coverage, doc.removals, doc.converter
doc.where(13, 18)  # Where(span=[13:18], unit='characters', kinds=..., rules=...)
```

`musubi.sync(root, into)` is next door for when a folder and a manifest are
wanted. `musubi.media_type_of(path)` answers what musubi thinks a file is.

Four things this is **not**, and each is a way the surface could have gone
wrong:

**Not a second pipeline.** It calls the same converters, the same cleansing
ruleset and the same screener the command line calls, chosen by the same
configuration ([ADR-0027]). A folder set up for `musubi sync` is set up for
this, and `musubi config` explains both. `tests/test_api.py` asserts the text
equals what a real sync writes, minus the front matter.

**Not a layer with privileges.** `api.py` sits beside `interfaces/` in the
architecture table and may import exactly what the CLI may. A convenience
surface that could see more than the command line would be a second place for
policy to live.

**Not a corpus.** One file has no `(source_id, unit_key)`: [ADR-0006] makes
identity a property of a *source*, and a path handed to a function is not one.
So the return value carries no record identity and nothing is written. There is
no front matter either — nothing was emitted, so there is nothing for it to
describe.

**Not exempt from the screener.** [ADR-0008] stops a *run*; the equivalent for
a value is refusing to be one. `convert()` raises `CredentialFoundError`, naming
the rule and never the value.

## Consequences

- `Where` reports the **unit** alongside the span, because `[2:3]` is one
  character or one page and the numbers look identical ([ADR-0025]). A caller
  must read it before doing arithmetic, and the string form says so.
- Writing it found a defect in the answer itself. A **removal occupies no
  output**, and `Span.overlaps` is false for an empty span — correctly, or every
  insertion would collide with the run it sits in. So the first version of
  `where()` reported where a range came from and **silently omitted what had
  been taken out of it**, which is the one thing [ADR-0005] exists to keep
  visible.
- The README now opens with three lines of Python and a comparison table that
  names two rows musubi loses: Office formats, and tables or layout. Saying
  which library to use instead costs nothing and is the difference between a
  page somebody trusts and one they check.

## What it costs

**A public surface is the hardest thing in a library to change**, and this one
was added before the questions it answers are settled. `Document.where` returns
a `Where`; a caller will build on that shape, and the incremental work in #77
may want a unit key on it, the map-size work in #76 may change what a segment
is, and neither of those decisions has been made. The version is `0.1.0.dev0`
and nothing is released, which is the only reason this is acceptable now rather
than after v0.4.

**And it moves where people meet musubi.** The command line leads with what did
*not* happen — what was skipped, what was removed, what share is traceable —
and a function call leads with a return value. `coverage` and `removals` are
fields somebody has to look at rather than lines they cannot avoid reading. The
mitigation is that a credential still refuses and an unconvertible file still
raises; the honest statement is that the reporting posture [ADR-0012] built is
weaker here than on the command line, and this ADR does not claim otherwise.
