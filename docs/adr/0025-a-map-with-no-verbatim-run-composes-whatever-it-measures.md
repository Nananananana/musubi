# 25. A map with no verbatim run composes whatever it measures

**Status:** accepted

## Context

ADR-0018 decided the trace map's source side counts **characters of the decoded
text**, and `source_unit` says so on every document. It also kept the field open,
because a PDF has no decoded text to count: its words live inside content
streams that are usually Flate-compressed, so **there is no byte range in the
file holding the sentence you are reading**, and a character offset would index
something that does not exist.

`domain/trace.py` already carried the placeholder — `OPAQUE = "opaque"`, with a
comment saying *a PDF's locator will be a page*. Nothing produced one.

When the PDF converter tried to, the pipeline refused it:

```text
composition needs both sides in characters, and this map's source is
measured in opaque
```

`followed_by` composes the converter's map with the cleanser's, and it refused
outright on any non-character source. **That guard is stricter than the thing it
protects.** Reading what the composition actually does to the earlier source
side, there is exactly one arithmetic operation:

```python
if earlier.kind is Kind.VERBATIM:
    source = shared.shift(earlier.src.start - earlier.out.start)
else:
    source = earlier.src  # taken whole; no arithmetic at all
```

Shifting an offset by a constant is only valid while both sides count the same
thing. **Every other kind is taken whole**, which is valid whatever the source
counts.

So the constraint was never *both sides must count characters*. It is **a
verbatim run must**.

## Decision

**`followed_by` refuses when the source is not characters *and* the map has a
verbatim run.** A map with no verbatim run composes whatever it measures.

That is precisely the PDF converter's case, and not by accident: **a PDF's
segments cannot honestly be verbatim.** A verbatim claim says the
correspondence holds at every interior offset, and inside a page it holds
nowhere — the text was assembled from operators, not sliced out of a string.
`transformed` says the correspondence holds at the ends of a run and nowhere
inside, which is exactly true. The map that can compose is the map that is
honest, and the two conditions turn out to be the same condition.

**The composition carries the unit through.** It did not: `followed_by` built its
result without passing `source_unit`, which defaulted to `characters`. That
omission was unreachable while non-character maps could not compose at all, and
became a live defect the moment they could — a PDF's map was published saying
its page indices were character offsets. Found by running a sync end to end and
reading the trace map that landed, not by reading the code.

**A reader carries a unit it cannot compute in.** `Corpus.held()` refused
anything but `characters`; it now accepts `opaque` and still refuses a unit it
does not recognise, because reading page indices as character offsets would
point a citation at a confident wrong place. `musubi trace` branches on the unit
rather than assuming: it reports `pages [1:2] (opaque locator)` and says there is
no byte offset, where a character map reports `characters [8:13]` and computes
one.

## Consequences

`musubi.trace-map/1`'s `source_unit` enum gains `opaque`. Both contracts are
`-draft`, so widening it is a change this register may still make — and **this is
what that costs**: a consumer holding the older schema refuses a valid map. Which
is the behaviour ADR-0018 wanted, and a concrete reason the freeze has not
happened. This is the third change to the map's shape this week.

The manifest's stated limits were false and are corrected. They said *source
offsets are counted in characters of the decoded text*, flatly, in a sentence the
document carries with it. A corpus of Markdown and PDF now has **one coverage
number over two meanings of traceable**, and the limits say so rather than
leaving a reader to average them.

## What it costs

**A relaxed guard is a guard that can be relaxed again.** The old rule was
mechanical — one field, one comparison — and the new one asks a question about
the segments. A future kind whose composition *does* need matching units would
pass this check, because the check names `VERBATIM` rather than the property
"has interior correspondence". Nothing enforces that a new kind declares which
it is; the next person adding one has to notice.

**`traceable` now means two things and the headline number does not distinguish
them.** A PDF is 100% traceable and a Markdown file is 100% traceable, and the
first resolves to a page while the second resolves to a character. The limits
say it, `source_unit` says it per map, and the aggregate percentage in the
manifest still says neither. A reader who takes the number and not the sentence
gets a worse answer than before this converter existed, which is a real cost of
supporting the format at all.

**The locator is coarse on purpose and will read as a gap.** musubi could report
a character offset within its own extraction of a page. It would be reproducible
only by musubi — what "character 47 of page three" means depends on the order
this converter walked the text operators — so it would be a precise-looking
number nobody else can check. *Page three* is a claim a person can verify by
opening the file. Somebody will ask for the finer number, and the answer is that
the finer number would be a worse one.
