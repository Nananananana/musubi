# 0046. A failure that a program can name

**Status:** accepted
**Date:** 2026-09-09
**Context:** `sora`'s R-E1 and R-E2 (`musubi-work/01_sora_errors_requirement.md`), [ADR-0007], [ADR-0020], [ADR-0033]

## The problem

`sora` is the only program that talks to all seven libraries, and the only
place that can answer *is this my fault, or is something broken*. It keeps an
incident log, folds it by **the word before the first colon on stderr**, and
keeps nothing else from the line — because a message can quote a path from
somebody's own machine, and an incident log that holds content is a second
copy of the thing it was watching.

That makes the set of those words an interface. musubi had never published one,
and worse:

```text
musubi: an AWS access key id in notes/setup.md. Nothing was written.
musubi: design/gear.md is outside the corpus at /home/someone/synced
usage: musubi [-h] [--version] {plan,sync,...}
```

**Every failure musubi has folded into one bucket called `musubi`**, every bad
command line into one called `usage`, and `musubi verify` — which exits 1 —
wrote nothing to stderr at all, so a caller had a number and no word for it.

## Decision

**The first line of stderr begins with the kind, and the closed set of kinds is
published as a document.**

```text
CredentialFoundError: an AWS access key id in notes/setup.md. Nothing was written.
```

```bash
musubi errors --json   # musubi.errors/1-draft
```

Each entry carries `kind`, `exit_code`, `outcome`, `retryable`, and one line in
English and one in Japanese. The Japanese is written here rather than
translated downstream, which `sora` asked for and is right: two sentences
written by one hand cannot disagree, and a translation maintained by the reader
drifts from the thing it describes the first time either changes.

**The catalogue is checked against the code, not maintained beside it.** Every
`MusubiError` subclass must appear in it or be named in `NOT_PRINTED` with a
reason, and every name the command line prints is read out of the source of
`main.py`. A catalogue listing six of seven kinds is worse than none: the
seventh arrives at a reader that has never been told about it, which is the
exact failure the exercise was meant to remove.

**`retryable` is false everywhere except one kind**, and that is a fact about
[ADR-0007] rather than a stub. musubi reads a folder that is already on the
disk: no network, no lock, no service, no timeout, so there is no transient
failure to wait out. `Unreadable` — the file system itself — is the exception,
and it is the only one, which is what keeps the field from being a column of
identical values.

Four kinds have no exception class behind them, because they are conditions
rather than raises: `Usage` (argparse, whose output now begins with a name),
`Unverified` (`musubi verify` found faults), `Unreadable` (`OSError`, caught by
name so that a bug still arrives as a bug), and `Unexpected` (a bug — named on
the first line, with the traceback still following underneath for the person
who has to fix it).

## And the question `sora` asked musubi to answer

> **「全件 skip は run として成功なのか」という問い自体が、musubi のものだと思っている。**

It is not a success, and this project had already decided so somewhere else and
not noticed the same shape here. `Manifest.summary` refuses to print

```text
0 emitted, 1 skipped, 0 removals, **100.0% traceable**
```

because it is a number maximised by total failure ([ADR-0033]).
`tests/test_a_report_that_says_nothing_happened.py` fixed two more of them. All
three fixes were for a **person reading a report**, and none of them reached a
caller: a run that read two hundred files and wrote none of them still exited
**0**, which is the most widely read metric musubi has.

So `EverythingSkippedError` is a refusal (exit 3). Units were read; not one
became a document; the folder can be read and nothing in it could be converted,
which is a different problem from an unreadable folder and has a different fix —
often an optional extra that is not installed.

**It is not a threshold**, and `sora` was right not to want to choose one. This
is the single count at which *musubi read your folder* and *musubi read nothing
of your folder* cannot be told apart from outside. One emitted document proves
the run did something; some files failing is a skip list, which is reported and
is normal.

Finding it also corrected an existing refusal that was answering this question
and **saying the wrong thing**. `EmptySourceError` fired whenever no artefacts
were produced, so a folder of unreadable PDFs was refused with the words
*produced no units* — sending its owner to check whether the folder could be
read at all. It could.

## What it costs

**A behaviour change at exit 0.** A pipeline that synced a folder musubi cannot
read now gets a 3 where it got a 0. That is the point, and it will surprise
somebody. `--withdraw-all` remains the "I have looked" flag and now covers
both refusals.

**Two tests that asserted exit 0 for this case now assert 3.** They were not
wrong; they were about a different reader. Their file's docstring names the
third way a run that achieved nothing read as a run that went well, which is
what it was already counting.

**A catch-all `except Exception`.** It is the thing this repository would
normally refuse. It is justified by what it does: it prints a named first line
and then re-prints the traceback, so the developer loses nothing and the reader
gains a bucket called `Unexpected` instead of one per line of Python it
happened to see first.

**The exit codes moved module**, from `interfaces/cli/main.py` to `errors.py`,
so the codes and the catalogue that quotes them cannot come apart. The CLI
re-exports them and the constant register follows.

**A second interface with its own error channel.** The MCP server returns
refusals as tool results with `isError`, never as stderr lines, so
`OutsideRootError` is in `NOT_PRINTED` rather than the catalogue. That is a
boundary worth writing down, not an omission.

## R-E2, and what was found while doing it

`sora` filed the stderr prefix as **a request rather than a requirement**, on
the grounds that a catalogue can be checked and a naming convention cannot.
Both are done, and the request turned out to be the more urgent half: without
it the catalogue would have described names that nothing printed.

The population guard found two real gaps the moment it existed, and both only
under the **full** suite, because the class tree holds what has been imported:

- `OutsideRootError`, in the MCP server, which nothing else in that test file
  loads;
- `MusubiError` itself, raised bare for an MCP root that is not a folder —
  putting the word `MusubiError` on stderr, a kind meaning *an error with no
  kind*. It raises `SourceError` now.

A guard whose population depends on which tests ran before it is a coin toss,
so it imports every module first.

[ADR-0007]: 0007-musubi-reads-exports-never-services.md
[ADR-0020]: 0020-the-console-is-not-the-contract.md
[ADR-0033]: 0033-a-threshold-that-nobody-swept-is-a-number-fitted-to-one-corpus.md
