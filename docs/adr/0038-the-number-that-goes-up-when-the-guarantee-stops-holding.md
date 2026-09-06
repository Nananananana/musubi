# ADR-0038 — The number that goes up when the guarantee stops holding

**Status:** accepted
**Date:** 2026-09-07
**Publishing `answer_width` where numbers are actually read, and the corpus it has no answer for.**

## Context

[ADR-0033](0033-a-threshold-that-nobody-swept-is-a-number-fitted-to-one-corpus.md)
found that `traceable_coverage` can move the wrong way. A map with one
`transformed` segment covering the whole document is **100% traceable** and
says nothing: every offset resolves, to the entire file. Measured on a real
alignment, the failing window reported the *higher* coverage.

So `answer_width` was added — ask about one character, how much source comes
back — and it was added to `TraceMap`. Filed as #81, which says the rest:

> **It is not in the manifest.** `answer_width` is on `TraceMap` and reachable
> from `musubi.convert(...)`, and the manifest — which is where people actually
> read numbers — still publishes coverage alone.

A corpus built with `musubi[html]` where the extractor and the source disagree
produces exactly this shape: high coverage, useless map. The number a reader
trusts has to be the one that moves when the guarantee stops holding, and it
was in a Python property nobody reading a corpus would find.

## Decision

**The manifest publishes the numerator, not the ratio.** Each artefact carries
`answered_source_units` — how much source its map hands back, summed over every
traceable character — and `coverage` carries the sum. A reader divides by
`traceable_characters`.

The numerator travels because **a corpus's width is a sum of numerators over a
sum of denominators, not a mean of the per-document widths.** A four-character
document answering with forty and a forty-thousand-character one answering
exactly average to 5.5, which is alarming about a corpus that is 99.99% exact.
The weighted answer is 1.0009. Publishing the ratio per artefact would have
invited the mean.

**And a run of mixed formats has no such number.** A PDF's map answers in pages
and a Markdown map answers in characters; their sum adds pages to characters.
So each artefact now states its `source_unit` in the manifest as well as in its
map, `coverage.source_units` lists the set, and `Coverage.answer_width` returns
`None` when it holds more than one. `traceable_coverage` survives the same
corpus because its numerator and denominator are both *output* characters; this
one does not, and the manifest says so rather than being averaged into
nonsense. The report says it in words: *no single number — this corpus measures
its sources in characters and opaque, and their sum has no dimension.*

**An absent numerator is `None`, never 0.0.** A manifest written before this
field omits it, and a width of zero would claim that a character resolves to no
source at all — a number no real map can produce. Inventing a value for an
absent one is the shape #81 was filed about, one field along.

**`source_unit` in the manifest is worth having on its own.** A reader deciding
whether two artefacts' numbers may be added had to open every sidecar to find
out.

**Neither field enters `run_id`.** The id is over the outputs, and both are
derived from maps the id already covers. Adding them would have changed the id
of every existing corpus on upgrade, and with it every journal's parent chain.
The regenerated conformance fixture confirms it: same `run_id`, new fields.

**And `verify` adds it up.** `answered_source_units` joins `characters` and
`traceable_characters` in the totals check, and `manifest 5` asserts that
`coverage.source_units` is exactly what the artefacts state. A published number
that nothing adds up is a number free to drift — and this one exists to catch
another number lying.

## Consequences

- `musubi plan`, `sync` and `verify` print the width under the percentage, and
  name the unit: *one character resolves to 2.67 source characters*. A reader
  who stops after the headline has seen it, because `Manifest.summary()` carries
  it too.
- Measured on the conformance corpus, the arithmetic is legible: a CRLF
  answers with 2, and a 27-character URL collapsed to 5 characters answers with
  27. `gear.md` is 2.67, and 135 of its 222 units are that one URL.
- `musubi.sync-manifest/1-draft` gains three fields, all required. Draft, so
  the version does not move ([ADR-0024](0024-a-field-added-is-a-new-contract.md)).
- Closes #81.

## What it costs

**Three more numbers in a document that already has a lot of them.** The
manifest is read by people deciding whether to trust a corpus, and each number
added is one more that can be misread. The defence is that this one is
published *next to* the number it qualifies and never instead of it, and that
the report spells out what it means in a sentence rather than printing a
figure.

**The mixed-corpus rule is a refusal, and refusals get worked around.** A
consumer that wants one number for a corpus of PDFs and Markdown will divide
`answered_source_units` by `traceable_characters` itself and get the nonsense
this declines to print. `source_units` is published beside the total precisely
so that doing so is a choice made with the evidence in hand, but nothing stops
it. The alternative — omitting the total on a mixed corpus — would stop it and
would also stop the legitimate use of grouping by unit.

**And the width still has no good value.** [ADR-0033] made it threshold-free on
purpose: there is no number written down that separates a healthy corpus from a
sick one, and a reader compares against the same corpus yesterday. Publishing
it more widely does not change that, and #84's per-converter floors are where
that question actually gets answered.
