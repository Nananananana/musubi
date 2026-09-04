# ADR-0033 — A threshold that nobody swept is a number fitted to one corpus

**Status:** accepted
**Date:** 2026-09-04
**A policy about constants, and the three changes it produced.**

## Context

A release meets documents nobody has seen. Every hand-chosen number in this
library was chosen against the corpus in front of somebody on one afternoon, and
until it is swept, nobody knows whether it sits on a **plateau** — a wide range
of values giving the same answer, so the choice was not load-bearing — or on a
**cliff**, where it was fitted whether or not anybody meant to fit it.

Ten module-level numeric constants gate behaviour. Swept with
`tools/sensitivity.py`, three things came out.

**`MINIMUM_RUN` is on a broad plateau.** Values from 1 to 80 give identical
coverage, identical segment counts, identical everything, collapsing only past
the length of a paragraph. The comment said *about two words*; the sweep says
the number does not matter, which is the best possible answer.

**The PDF kerning cut is a cliff.**

```text
   kerning  reads as
      -179  'thetent'
      -180  'the tent'
```

Word spacing is a property of the **font**, which `pdf_text@1` does not read.
Real producers put a space anywhere from under 200 thousandths of an em to about
330, so documents land on both sides and **no single value is right for all of
them**.

**And `traceable_coverage` can move the wrong way.** This is the serious one.
The metric is the share of output in a `verbatim` or `transformed` segment. When
alignment matches nothing, the whole output becomes one `transformed` segment
against the whole source — and every offset resolves, to the entire document:

```text
window     coverage   matched
    64      100.0%          0     nothing aligned
 65536       98.1%          1     aligned correctly
```

**The failure reports the higher number.** The headline metric of ADR-0004 is
maximised by the map being useless.

## Decision

**Three kinds, and every constant is one of them.** A `bound` refuses or
degrades loudly when passed. A `measurement` is derived by a named script. A
`threshold` changes what the output is, and must cite a sweep, a published
measurement of its tier, or a filed issue. `tests/test_thresholds.py` is the
register, and **a new numeric constant in `src/` that is not in it fails the
build.**

**A threshold on a cliff becomes a setting.** `WORD_GAP` left the code and
became `pdf-word-gap` in `musubi.toml`, with the sweep in the documentation and
`pdfium@1` named as the way to stop choosing at all — it reads the font metrics
and needs no threshold.

**A threshold whose job the caller can do exactly is deleted.**
`alignment._is_blank` was `out.length * 8 <= src.length and out.length <= 8`:
two unmeasured numbers deciding whether a stretch was recorded as a removal or
folded into a transformed run, and therefore deciding what the map says. Its
docstring justified guessing from lengths because *the caller holds the strings
and this does not* — which was true only because the caller was not passing
them. It passes them now and the question is `strip()`.

**And a misleading metric gets the number that catches it, rather than being
redefined.** `TraceMap.answer_width` answers *ask about one character, how much
source comes back*: 1.0 for a map that answers a character with a character, 166
for the failed alignment above. Threshold-free on purpose — there is no good
value written down, and a cut-off would be one more constant nobody measured.
`traceable_coverage` keeps its definition, which was never wrong; what it lacked
was a companion.

## Consequences

- Ten constants are registered, four of them thresholds, and each threshold
  cites something. The register is checked in both directions, so an entry for
  a deleted constant fails too.
- The AST walk that finds constants missed `-180.0` at first, because a negative
  literal is a `UnaryOp` rather than a `Constant`. **A register that cannot see
  the shape a new threshold will be written in is a register with a hole in it**,
  and a threshold added as a negative number would have walked straight past it.
- `CONFIDENT` in the decoder stays a threshold and stays cited as unresolved:
  every miss in `tools/encoding_detection.py` reported 100% coherence, so it
  cannot separate a right reading from a wrong one. It only excludes a detector
  that recognised nothing, which is a smaller job than it looks like it is doing.

## What it costs

**The register is a second place that has to be right.** It is a hand-written
list beside the code, and the guard only checks that every constant *appears* —
it cannot check that the classification is honest. Somebody can register a cliff
as a bound and the build stays green. What the guard buys is that the number
cannot be added in silence; the judgement is still a person's.

**And `pdf-word-gap` moves a decision onto the user that they cannot make well.**
Nobody knows their PDF's font metrics. The setting exists because there is no
value that works for every file, and the honest answer for most people is not to
tune it but to install `musubi[pdf]` — so this ADR has added a knob whose best
documentation says to use something else.
