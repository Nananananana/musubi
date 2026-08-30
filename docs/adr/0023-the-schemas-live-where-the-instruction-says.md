# 23. The schemas live where the instruction says they do

**Status:** accepted

## Context

`docs/contracts.md` tells a consumer how to load a schema:

> Validate against the schema shipped in the wheel:
> `importlib.resources.files("musubi") / "schemas"`.

The schemas lived at the repository root, and a hatchling `force-include` copied
them into `musubi/schemas/` at build time. Measured in this checkout, before
anything changed:

```
resolved to: C:\dev\musubi\src\musubi\schemas
exists     : False
```

**The sentence musubi publishes to its consumers was false in an editable
install.** It held for somebody who ran `pip install musubi` and for nobody
working on musubi — and **nothing in the repository ran it**, so nothing said so.

There was a CI job building a wheel, opening it, and asserting both files are
inside and parse. That job is real coverage of a real question, and it exists
because `force-include` does not apply to an editable install: delete the block
and nothing a developer runs locally notices. `tsumugi` and `akashi` were checked
and have the same configuration, and neither reads its own schemas at runtime, so
in both the deletion is invisible forever.

But the job checks that a path exists inside a built artefact. It is not the
sentence. **A published instruction that nothing runs is the shape this project
keeps finding**, and finding it in the instruction for loading the contract is
worse than finding it anywhere else: the audience is exactly the people musubi
has no other way to reach.

`kiseki` does not have this hole. `kiseki-conformance` keeps its schemas inside
the package tree and reads them with `importlib.resources`, so they resolve in an
editable install and a break fails a test rather than a release.

## Decision

**The schemas move into `src/musubi/schemas/`, and `musubi.schemas` is the
accessor that reads them.** hatchling ships files inside the package without a
`force-include` — measured, not assumed — so the block is gone rather than
replaced.

**musubi's own conformance tests load through the accessor**, which is the point:
`tests/test_contract_conformance.py` now reaches its schemas by the same sentence
`docs/contracts.md` gives a consumer. The instruction is exercised on every run.

`path_to()` accepts the identifier **with or without `-draft`**, because a
consumer reads `musubi.trace-map/1-draft` out of a document it is holding and
should not have to strip a suffix to find the schema for it. An unrecognised
identifier raises rather than returning a guess, matching the rule the contract
already states for readers.

**A signpost stays at `schemas/`, and no schema does.** Three of the four
siblings keep theirs at the repository root and it is where a reader looks first,
so `schemas/README.md` points at the new location. The files do not stay,
because **two copies of a contract are two contracts as soon as somebody edits
one** — this is the option `kiseki`'s ADR-0005 takes, publishing in two places
with a byte-identity test, and it is declined here. A test can keep two copies
equal; it cannot answer *which one is the contract* when somebody is reading the
wrong one.

A test asserts no `.json` returns to the root and that the signpost names every
schema that exists.

## Consequences

The wheel is unchanged in content: both contracts at `musubi/schemas/`, verified
by building one. The CI job that opens a wheel stays, because *is it in the
artefact* remains a different question from *does the sentence resolve*, and
today they have different answers only in the direction that is now fixed.

`musubi.schemas` is a new layer in the architecture test, allowed to import
nothing of musubi's and restricted to the standard library. A schema is what
musubi promises rather than something it decides, and a consumer holding only a
document must be able to load one without pulling in a pipeline.

## What it costs

**The root `schemas/` is now a redirect, and a redirect is a thing that rots.**
If the files move again and nobody updates it, a reader is sent somewhere empty
with more confidence than if the directory had never existed. The test that the
signpost names every schema catches a schema being added; it does not catch the
whole target directory moving, and nothing here does.

**The links in `docs/contracts.md` got longer and worse.**
`../src/musubi/schemas/musubi-trace-map-1.json` is a path with a build layout in
it, offered to somebody who does not care about the build layout. The reason it
is not `schemas/` is entirely internal to musubi, and the consumer pays a little
of that in ugliness.

**musubi now has a module whose only purpose is to be run by its own tests.**
Nothing in `plan`, `sync`, `trace` or `verify` imports `musubi.schemas` — the
runtime does not validate against schemas (ADR-0001 puts `jsonschema` in dev),
so the accessor exists for consumers and for the test that proves the sentence is
true. That is a real thing to be uneasy about: a module with no internal caller
is a module whose breakage only a test reports. The defence is that its breakage
*is* what the test is for, and the alternative was a sentence with no caller at
all.
