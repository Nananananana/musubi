# ADR-0028 — A dependency outside the domain buys quality, and still owes a map

**Status:** accepted
**Date:** 2026-09-04
**Refines [ADR-0001], which is unchanged for the domain.** Constrained by
[ADR-0004] and [ADR-0007].

## Context

[ADR-0001] gave musubi zero runtime dependencies, for a reason that has not
weakened: it is pointed at the folder holding everything its owner has ever
written, and every dependency is code with unsupervised read access to it.

It also has a cost that has become visible now that there is something to
measure. Main-content extraction is a research area with published benchmarks
and a decade of work in it. musubi's `html@1` is a scan of tags written in an
afternoon, and it does not win:

| Converter | Boilerplate rejected | Content kept | Traceable |
|---|---|---|---|
| `html@1` | 3/6 | 3/3 | 93.5% |
| `trafilatura@1` | **6/6** | 3/3 | **99.7%** |

*One generated page, `tools/html_coverage.py`. The fixture has the shape of a
real page and none of the mess; what it answers is the relative question.*

Half the planted boilerplate survived `html@1` — a cookie banner, a newsletter
box and a footer, in a corpus a model will answer from. **A guarantee that is
true of text nobody wants is not worth much.**

The obstacle was never licensing or trust. It was [ADR-0004]: every extraction
library in the world has the signature `bytes -> str`, and the correspondence is
the product. Taking the dependency appeared to mean giving up the map.

## Decision

**Outside the domain, a dependency is allowed. Optional, never required.**

- `domain/` stays standard-library only. [ADR-0001] is unchanged there, and the
  architecture test still asserts it.
- `pip install musubi` still installs nothing. Every default converter is still
  musubi's own.
- An extra that is installed is **offered, not claimed**: it adds a name a
  settings file can select ([ADR-0027]), and changes no folder's output on its
  own. A dependency appearing in an environment must not change what a corpus is
  built with.
- Only permissive licences. `PyMuPDF` is the fastest PDF reader in Python and is
  AGPL-3.0; a library whose users vendor it into their own products cannot hand
  them that, and an extra is still a dependency the user ships.

**And the map is recovered rather than given up.** `domain/alignment.py` takes
the extractor's text and finds it in the source: a run that occurs verbatim is
`verbatim` with exact offsets, a run that does not is `transformed`, and a
stretch of source that produced no output at all is a `removal` ([ADR-0005]),
which is how the boilerplate that was rejected stays visible in the map.

The alignment is a forward scan with a bounded window, not a diff.
`difflib.SequenceMatcher` over characters is quadratic, and [ADR-0016] already
refuses regular expressions on exactly this ground: a scan that runs unattended
over arbitrary documents must not be able to hang. Extraction is
order-preserving and local, so a forward scan is not an approximation here — it
is the right algorithm for this input.

**What the alignment produces is a measurement, not a promise.** Traceable
coverage falls out of it, per document, into the manifest. The trade a
third-party extractor makes is therefore a number a reader can see rather than
an argument they have to accept.

## Consequences

- Alignment recovered *more* coverage than `html@1` builds by construction —
  99.7% against 93.5% — because trafilatura emits fewer, longer verbatim runs
  and `html@1` emits many short ones separated by synthetic structure. That was
  not the expected result and is the reason this ADR is an acceptance rather
  than a proposal.
- [ADR-0007] does not become negotiable because the code doing the fetching
  belongs to somebody else. Every adapter is run in a test with the socket
  module broken.
- An adapter never imports its dependency at import time. A missing extra is a
  converter that is not registered, never an `ImportError` from
  `import musubi`, and `musubi config` prints what is missing and what to
  install.
- Alignment is now a general bridge. Any extractor that returns text — a PDF
  reader, a document converter, something written next year — can be adapted
  without a fifth argument about ADR-0004.

## What it costs

**A verbatim segment now means two different things, and the map does not say
which.** In `markdown@1` it means *this character was carried through by code
that knew it was carrying it*. In an aligned converter it means *this string was
found at this offset, in order, in the source*. The second is inference. It is
sound inference — twelve characters or more, forward-only, within a bounded
window — and it is still inference: a document that repeats a paragraph
verbatim can have the second occurrence attributed to the first's position when
the extractor dropped something in between.

That is a real, if narrow, way for a citation to point at a confident wrong
place, which is the failure this project exists to prevent. It is accepted here
because the alternative was to keep a map that is exact about text that kept
half the cookie banner. It is **not** accepted silently: the segments carry
`align.*` rules, the manifest names the converter, and a reader who cares which
kind of verbatim they have can tell from the artefact.

The second cost is ordinary and permanent: **a supply chain.** `musubi[html]`
brings trafilatura and, behind it, lxml, courlan, htmldate, justext and their
dependencies. All Apache-2.0, BSD or MIT, and all of them code that will read
the owner's folder. The mitigation is that it is opt-in, that the default
install still has none of it, and that turning it *off* is deleting a line from
a settings file rather than a migration.
