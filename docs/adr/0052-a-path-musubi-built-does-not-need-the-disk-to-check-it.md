# 0052. A path musubi built does not need the disk to check it

**Status:** accepted
**Date:** 2026-09-11
**Context:** [ADR-0007], [ADR-0008], [#80](https://github.com/Nananananana/musubi/issues/80)

## What was measured

A cold sync of 300 documents, profiled again after the trace-map and manifest
work, put `Path.resolve()` back at **12%** — a number `docs/measurements.md`
records as *fixed* at 7%. It came back because a refactor routed both writers
through one checked helper, which was the right shape and put the syscall on
every write instead of every other one.

The same profile said trace composition was 24%. **It is not.** `cProfile`
charges per call and composition is tens of thousands of very small Python
calls; timed directly it is about 5%. That correction is worth as much as the
fix: the first thing measured was the wrong thing, and acting on it would have
meant rewriting the composition algorithm for a twentieth of the run.

So the counts became the measurement and the clock the corroboration:

```text
                        before    after
  _getfinalpathname      3,627      620
  nt.mkdir               1,206       10
  nt.stat                3,013    1,216
  nt.replace               601      601     the real work, untouched
  _io.open                 903      903
```

Six thousand syscalls for 300 documents — twenty per document — asking the
filesystem about paths musubi had just built itself.

## Decision

**The staging write path checks containment lexically. The two paths that
delete still ask the disk.**

`_under(root, relative)` refuses an absolute or drive-qualified `relative`
before joining — `Path("/etc") / "/etc/passwd"` is `/etc/passwd` on POSIX, so
joining first and checking after would be checking the wrong thing — and then
compares `os.path.normpath(root / relative)` against the root. `normpath`
collapses `..` before the comparison, which is the whole of what `resolve()`
was doing for a key musubi controls.

**Why that is not weaker where it is used.** `begin()` removes the staging
area and makes it again, so everything under it was written by this run and
musubi creates no symbolic links. The only thing left to defend against is a
key that walks out with `..`, and that is arithmetic on a string.

And `resolve()` never defended against the other case anyway: resolving and
then opening is two operations, and a link appearing between them is exactly
the race the syscall looks like it prevents. A check that reads as a defence
and is not one is worse than the arithmetic, because somebody trusts it.

**Withdrawal and retention keep resolving.** Withdrawal deletes what a
*previous manifest* names, and a manifest is a file somebody can edit. A test
asserts the two paths use different checks on purpose, so a later tidy-up that
unified them would fail rather than quietly widen what musubi will delete.

**And a directory is made once.** `mkdir(exist_ok=True)` is a syscall whether
or not the directory is there, and it ran once per file written in both the
staging and the promotion loops: a flat vault of three hundred notes made two
directories twelve hundred times.

## What it costs

**Two containment checks where there was one**, and the difference between them
is a security boundary. That is the real price, and it is paid in a test that
asserts the difference rather than in a comment that hopes for it.

**A lexical check cannot see a symbolic link.** Stated plainly because it is
the thing somebody will worry about: if a future change lets something other
than this run write into the staging area before promotion, this check stops
being sufficient and the ADR stops being true. `begin()` wiping the area is the
premise, and it is one line away from being someone's optimisation.

**A set of directories held for the length of a run.** Bounded by the number of
distinct folders in the corpus rather than by its size, which is the shape
[#80] cares about: a vault with ten thousand notes in twenty folders holds
twenty paths.

## Consequences

**1.49s → 1.19s**, interleaved A/B, three rounds each, every "after" below
every "before" on a laptop noisy to ±15%.

The lesson that generalises is not about paths. It is that a profiler's
attribution and a stopwatch disagree in a predictable direction — call-heavy
pure Python is inflated, syscalls are not — and that the way through is to
count something exact. The syscall counts do not move between runs, between
machines, or with what else the laptop is doing.

[ADR-0007]: 0007-musubi-reads-exports-never-services.md
[ADR-0008]: 0008-a-credential-stops-the-run.md
