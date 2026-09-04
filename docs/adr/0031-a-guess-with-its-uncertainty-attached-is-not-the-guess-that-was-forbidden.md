# ADR-0031 — A guess with its uncertainty attached is not the guess that was forbidden

**Status:** accepted
**Date:** 2026-09-04
**Relaxes the refusal in `domain.text.decode`. Does not change [ADR-0018], and
leaves the domain exactly as it was.**

## Context

`decode` reads UTF-8 and UTF-16-with-a-mark and refuses everything else, on an
argument that is still right:

> A guessed legacy encoding writes mojibake into a corpus that will be sent to a
> model, and it looks exactly like successful ingestion — no error, no warning, a
> file full of plausible nonsense.

Every clause of that is about a guess being **invisible**. The implementation
chose the strongest available answer to invisibility, which was to refuse.

Measured, that answer makes musubi unusable for the person it was built for:

```python
>>> decode("# 設計メモ\n".encode("cp932"))
ValueError: not decodable as UTF-8 or as UTF-16 with a byte-order mark
```

**A vault holding anything written on a Japanese Windows machine before about
2015 is Shift-JIS**, and musubi reports every one of those files as
`undecodable`. So does a `.txt` from Notepad, a French note in Latin-1, and a
Russian one in KOI8-R. The corpus is correct, empty of exactly the old material
somebody most wants to find again, and says so only as a count of skips.

That is a correct library nobody can use, and correctness that is unusable is
not a stronger form of correctness.

## Decision

**The guess becomes visible instead of forbidden**, in three parts.

**The domain does not change.** `domain.text.decode` still reads two encodings
and still refuses. [ADR-0001] holds: no dependency, no detection, no guessing in
the layer whose job is to be checkable.

**Infrastructure may detect, under a setting that defaults to refusing.**
`encoding = "strict"` is the default and behaves as before. `encoding =
"detect"` reads the file and **records the detected encoding with every offset**
— in `Converted.source_encoding`, therefore in the trace map, therefore in
anything that reads one. The reading is in the corpus, not in a log.

**A refusal names what the file is.** Even in `strict`, when the extra is
installed, the message says `looks like cp932 (98% coherent); set encoding =
"detect"` rather than only that the bytes are not UTF-8. A refusal that cannot
be acted on is most of why the refusal was the wrong shape.

Below `CONFIDENT`, `detect` still refuses. A detector that found nothing it
recognised is not an answer, and acting on one is the original failure exactly.

## What the numbers say

`tools/encoding_detection.py`, six languages against seven encodings, comparing
the recovered **text** rather than the label:

| sample | recovered exactly |
|---|---|
| a paragraph | **17 of 19** |
| one line | **16 of 19** |

Both constant failures are French in Latin-1 or cp1252 read as cp1250 — the
single-byte Western encodings, which differ in a handful of accented characters.
Every multi-byte encoding was right at paragraph length.

**Detection gets worse as the file gets shorter**, and the extra short-sample
failure is Russian in KOI8-R read as `shift_jis_2004`: not a near miss, a
different alphabet. A folder of one-line notes is precisely that input.

**And every one of those misses reported 100% coherence.** The confidence number
is a measure of how readable the chosen decoding looks, not of whether it is the
right one, and it will not warn anybody. That is the single most important thing
on this page and it is why the default did not move.

## Consequences

- The policy is one wrapper, `Decoding`, applied by media type rather than by
  asking a converter what it does. A PDF is bytes all the way down and is never
  transcoded; a test asserts every registered converter falls on one side.
- When detection is used, the inner converter is handed the same text re-encoded
  as UTF-8. Character offsets are counted over the text and are therefore
  identical, and `source_encoding` records the **original**, so
  `text[:n].encode(source_encoding)` still yields a byte offset in the owner's
  file. [ADR-0018] is untouched.
- `musubi[encoding]` is `charset-normalizer`: MIT, no dependencies of its own.
- A corpus can now contain documents musubi is not certain it read correctly.
  The manifest says which, per artefact, by naming an encoding that is not
  `utf-8`.

## What it costs

**A corpus can now hold plausible nonsense, and that is a real change of kind,
not of degree.** Before this, everything in a corpus was read by a decoder that
could only succeed or fail. Now a French note can be sitting there, in confident
cp1250, with three characters wrong and 100% coherence recorded beside it.

Three things make the trade defensible and none of them make it free: it is
opt-in, the assumption is written into the artefact rather than a log, and the
failure mode is concentrated in a population the documentation names. What none
of them do is let a reader of the corpus tell a correct cp1250 reading from an
incorrect one **without the original file**. The trace map points at that file,
which is the best answer available and is not the same as knowing.

**The second cost is that a default is now doing load-bearing work.** `strict`
is the safe setting, `detect` is the setting a Japanese user is told to turn on
by the very first refusal they see, and the population where detection is
weakest is not theirs. That is a defensible piece of design and it is also the
shape of a default that gets turned on reflexively — which is what [ADR-0008]
says about `--allow`, in a document about a different subject.
