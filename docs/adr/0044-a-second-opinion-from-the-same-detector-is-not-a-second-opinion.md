# 0044. A second opinion from the same detector is not a second opinion

**Status:** accepted
**Date:** 2026-09-09
**Context:** [#82](https://github.com/Nananananana/musubi/issues/82), [ADR-0031], [ADR-0033], [ADR-0017]

## The problem

`encoding = "detect"` reads a file that is not UTF-8 and records what it
assumed ([ADR-0031]). `CONFIDENT = 0.3` refuses a detection below it, on the
reasoning that a detector which recognised nothing is not an answer.

That reasoning is sound and the number does much less than it looks like it
does. Measured with `tools/encoding_detection.py`, **every miss reported 100%
coherence**: French in Latin-1 read as cp1250, Russian in KOI8-R read as
`shift_jis_2004`, all confidently. The threshold cannot separate a right
reading from a wrong one. It excludes only the case where the detector found
nothing at all.

#82 proposed three ways forward and was explicit that the first needed
measuring rather than assuming.

## What was measured

**The runner-up does not separate them either.** `charset-normalizer` returns
ranked candidates; the question was whether a *rival reading* — another
candidate that decodes the same bytes to different text — marks the failures.

```text
  a rival reading exists    right    WRONG
  no                           11        0
  yes                           6        2
```

It fires on eight readings to find two wrong ones. As a gate that is roughly
the entropy tier's published precision of 21.1%, which [ADR-0017] made **opt-in
and off by default** for exactly this reason.

There is a real signal in it, and it points the other way: a reading with *no*
rival was right every time here. That is not something to act on per document
either — it is eleven cases — and turning it into a threshold would be fitting a
number to one generated corpus, which [ADR-0033] exists to refuse.

The runner-up was also examined by score gap, before the rival test. Two of the
three misses had the correct encoding sitting at **rank two with a chaos gap of
exactly 0.0000** — and so did a case the detector got right. The gap does not
separate them.

## Decision

**musubi records which readings are guesses, and does not rank them.**

- `Artefact.encoding` and `Artefact.encoding_detected` go in the manifest.
- The run report says how many documents were read that way, and in which
  encodings.
- `CONFIDENT` does not move. Raising it would exclude nothing that is wrong and
  would start refusing files that read correctly, which is a threshold tuned to
  make a metric look better.

This is #82's third option, and after the measurement it is the only one the
evidence supports. It does not fix detection. It stops the corpus being quiet
about the fact that detection happened.

**The issue's premise about the manifest was wrong**, which is why this is more
than a print statement. #82 says *the manifest already records the encoding per
artefact*. It did not — only the trace map did. So *how much of this corpus
rests on a guess* meant opening every sidecar, and could not be answered from
the one document that describes the run.

## What it costs

**Two fields on a draft contract.** `musubi.sync-manifest/1-draft` gains
`encoding` and `encoding_detected`, both required. A consumer holding the older
schema refuses a valid manifest, which is what a draft is for and part of why
the freeze has not happened.

**A number that cannot be acted on.** The report now says *seven of forty read
by detecting the encoding*, and a reader who wants to know **which seven are
wrong** is no better off than before. The honest answer is that nothing here
knows, and saying so out loud invites the question. That is still better than a
corpus in which the question does not arise.

**A false symmetry to avoid.** `encoding_detected` is not a quality signal and
must not be read as one. A detected `cp932` on a Japanese vault is right almost
every time; a detected `cp1250` on French prose is wrong. The flag says *this
was guessed*, and nothing about whether the guess was good.

**The rival test is now in the tool and not in the code.** Somebody will
reasonably want to use it. The measurement is committed with the numbers beside
it so that the next person reaches the same conclusion in a minute rather than
building it first.

## Consequences

#82 stays open. Detection is no better than it was; what changed is that a
corpus now says where it guessed. Closing it would claim a fix that the
measurement above explicitly denies.

The two options that remain untried are still the ones #82 listed. **Using the
file's neighbours** — a vault is usually written in one encoding, so a detection
that disagrees with fifty files beside it is suspect — is real signal and a
design change, because `Source` reads one unit at a time on purpose. It is the
only remaining idea with evidence behind it, and it is a bigger change than
this one.

[ADR-0017]: 0017-entropy-is-a-tier-not-a-default.md
[ADR-0031]: 0031-a-guess-with-its-uncertainty-attached-is-not-the-guess-that-was-forbidden.md
[ADR-0033]: 0033-a-threshold-that-nobody-swept-is-a-number-fitted-to-one-corpus.md
