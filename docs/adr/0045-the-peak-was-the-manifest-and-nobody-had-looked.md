# 0045. The peak was the manifest, and nobody had looked

**Status:** accepted
**Date:** 2026-09-09
**Context:** [#80](https://github.com/Nananananana/musubi/issues/80), [ADR-0002], [ADR-0008], [#84](https://github.com/Nananananana/musubi/issues/84)

## The problem, as it was filed

#80 measured that a run holds roughly the whole corpus in memory — 1.5x, 1.3x,
1.3x of the input, linear and not falling — and named three causes:

> - `run()` accumulates `artefacts`, `removals`, `findings` and `skipped` for the
>   whole run, because the manifest is one document describing the whole run.
> - `DocumentEmitter` stages everything and promotes together, because ADR-0008
>   is fail-closed.
> - `Source.read()` returns `bytes` — the whole unit — because a converter takes
>   bytes.

It concluded that the second is load-bearing, that a fix means a very careful
argument about ADR-0008, and that neither remaining option is urgent.

**All three are wrong about where the peak is**, and the number was stale.

## What was measured

Re-measured before anything was built, it was **1.9x, 1.8x, 1.8x** — not the
1.3x the documentation had said for months. Nothing had noticed, because
`tools/scaling.py` prints and no test compares. That is [#84]'s finding about
the converter scores, in a second place.

Then, phase by phase through a 400-note run:

```text
  after previous + begin    peak    2,053   0.00x
  after run (all staged)    peak  595,598   0.56x
  after render(manifest)    peak 2,008,425  1.89x     <- here
  after promote             peak 2,008,425  1.89x
```

The accumulation #80 blames is real and it is **0.56x**. The peak is
`render()`, which adds **1.33x of the whole input** transiently to produce a
269 kB file. Split further: the nested dict is 0.53x, and `json.dumps` building
every piece and then joining them is the rest.

It is transient, which is why it never showed up in what the run retained, and
why a snapshot taken after the run attributed nothing to it.

## Decision

**The manifest is streamed to its file instead of being built as one string.**

`manifest.chunks()` yields pieces via `JSONEncoder.iterencode`; the emitter
writes each one. `manifest.render()` stays for the callers that genuinely want
a string — `musubi plan` prints one — and is now `"".join(chunks(...))`.

```text
   notes      input         peak  peak/input
     100    273,200      256,086        0.9x
     200    546,400      429,301        0.8x
     400  1,092,800      820,399        0.8x
```

**1.9x to 0.8x**, and ADR-0008 was never touched. The staging area is still
staged whole and promoted together, because that was never the problem.

**And a ceiling, so it cannot drift again.** `tests/test_memory_ceiling.py`
gates the ratio the way the converter register gates a quality score, with the
same care about headroom: set above the measurement, with the gap and the reason
written down. It was checked against the old behaviour and fails at 2.04x.

`stage_manifest` now refuses a bare `str` by name. A string is iterable one
character at a time, so passing one would write the correct file the slowest
possible way and nothing would say so — and it caught four callers in the tests
the moment it existed.

## What it costs

**A second way to write a file in the emitter.** `_write` takes a string,
`_write_chunks` takes pieces, and both go through one `_staged_path` so they
cannot come to disagree about what is inside the staging area. Two writers is
one more than one.

**A refusal where a convenience would have worked.** `stage_manifest` could
have joined a string quietly. It raises instead, which turns a slow correct
call into a loud broken one — the right trade only because the slow version is
undetectable.

**The nested dict is still built whole**, and that is the 0.53x this does not
fix. Streaming that too means writing JSON by hand around a generator of
artefacts, and the manifest is the one document here whose exact bytes are a
contract. Not worth it at this ratio; the note is here so the next person knows
the remaining half is known rather than missed.

**The ceiling is a test that syncs 100 notes**, so the suite is a few seconds
slower on every run. That is the price of a number that is checked rather than
printed, and #84 is the argument for paying it.

## Consequences

**#80 stays open, and its headline is now wrong in a useful way.** A run no
longer holds the whole corpus; it holds 0.8x of it. But the growth is still
**linear** — the accumulated artefact list is real — so the 20 GB shelf ADR-0007
describes still fails. What changed is the constant, by a factor of 2.4, and
what changed more is that the cause is now known.

**The lesson is about the diagnosis, not the fix.** #80 named three plausible
causes from reading the code, and the one that mattered was in none of them.
Reading the code says where memory *could* go; only measuring says where it
does. The fix was an afternoon and the argument with ADR-0008 that the issue
braced for never happened.

[ADR-0002]: 0002-the-sync-manifest-is-a-document.md
[ADR-0008]: 0008-a-credential-stops-the-run.md
[#84]: https://github.com/Nananananana/musubi/issues/84
