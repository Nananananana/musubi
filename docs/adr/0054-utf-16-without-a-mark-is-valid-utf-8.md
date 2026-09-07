# 0054. UTF-16 without a mark is valid UTF-8

**Status:** accepted
**Date:** 2026-09-12
**Context:** [ADR-0031], [ADR-0033], [ADR-0039], [#82](https://github.com/Nananananana/musubi/issues/82)

## The defect

A UTF-16 file with no byte-order mark decodes as UTF-8 without an error. Every
ASCII character becomes itself followed by a NUL, so the decode **succeeds**,
the reading is recorded as `utf-8`, and the corpus holds the document
interleaved with NUL characters.

Measured, on one file:

```text
  with-bom.md    WRITTEN  coverage 43/87 (49%)  NULs=0   readable: True
  le-no-bom.md   WRITTEN  coverage 86/130 (66%)  NULs=43  readable: False
  utf8.md        WRITTEN  coverage 43/87 (49%)  NULs=0   readable: True
```

**The broken document scored better.** `traceable_coverage` was 66% against the
correctly-read file's 49%, because the mangling doubled the body and made
musubi's own front matter — which is synthetic, and counts *against* coverage —
a smaller share of it. The number a reader trusts went **up** as the document
became unreadable.

`musubi verify` held. The manifest was internally consistent. Nothing anywhere
said a thing. That is [ADR-0039]'s shape, arriving through the success path
rather than the guessing one, and it is the exact failure the whole project
exists to make impossible.

It is not exotic input. Editors and export tools on Windows write UTF-16
without a mark, and the owner's vault is on Japanese Windows.

## Decision

**A UTF-8 decoding that contains a NUL is refused**, with the reason named:
*UTF-16 without a byte-order mark reads exactly this way, one NUL per ASCII
character.*

This is the rule [ADR-0031] already applies to the escape character, from the
other direction. ISO-2022-JP is seven-bit, so a Japanese file in it decodes
cleanly into its own escape sequences and comes back as `$B@_7W...` reported as
`utf-8`; `decode` refuses that on the grounds that *an escape character is not
something prose contains*. A NUL is not something prose contains either.

**It does not get ISO-2022's recovery, and that distinction is the interesting
part.** For a stateful encoding `decode` re-reads the bytes by name and checks
the reading against them by round trip — an equality, not a probability — which
works because an ISO-2022 file declares its character set inline. UTF-16
declares nothing. **Every even-length byte string decodes and re-encodes as
UTF-16 unchanged**, so a round trip is satisfied by any file at all and proves
precisely nothing. Recovering here would be guessing, which is what [ADR-0031]
forbids, so the answer is to stop.

`encoding = "detect"` reads all three UTF-16 shapes correctly — checked — and
the strict refusal reaches that advice through the machinery that was already
there.

## What it costs

**A file that genuinely holds a NUL is now refused.** A `.md` or `.txt`
containing one is almost certainly a binary file with a text extension or a
corrupted one, and `encoding = "detect"` is the way through for a case where it
is neither. It is one character, and the alternative is the measurement above.

**Only NUL.** BEL, VT and form feed still pass into a corpus, and that is
deliberate: they are odd but they are not *evidence of a mis-encoding*, which
is the test both this and the escape rule apply. A rule about "control
characters" in general would be a tidier sentence and a worse one.

**A property strategy narrowed again.** `tests/test_converters.py` generates
arbitrary text and already excluded `\x1b`; it now excludes `\x00` for the same
reason. Generating one would be generating a document musubi deliberately does
not accept.

## Consequences

**Coverage cannot be trusted to fall when a reading goes wrong**, and this is
the second time that has been demonstrated rather than argued. [ADR-0033]
found `traceable_coverage` at 100% over no characters; this found it *rising*
as a document was mangled. Both times the metric moved the reassuring way.

The generalisation is worth stating plainly, because it constrains what the
numbers in `docs/measurements.md` are for: **coverage measures whether an
offset resolves, and a mis-decoded document resolves perfectly.** Every
character of the mojibake had a place in the source, because it really did come
from there. What was wrong was upstream of anything the map can see.

Found by running degenerate inputs through a real sync — empty files, lone
byte-order marks, a 200 kB single line, control characters — rather than by
reading the decoder. The 200 kB line found something too, and it is a separate
finding.

[ADR-0031]: 0031-a-guess-with-its-uncertainty-attached-is-not-the-guess-that-was-forbidden.md
[ADR-0033]: 0033-a-threshold-that-nobody-swept-is-a-number-fitted-to-one-corpus.md
[ADR-0039]: 0039-a-fixture-whose-answer-is-known-and-the-two-things-it-found.md
