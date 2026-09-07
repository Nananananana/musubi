# 0047. A fourth contract that three documents knew nothing about

**Status:** accepted
**Date:** 2026-09-10
**Context:** [ADR-0046], [ADR-0023], [ADR-0002]

## The problem

[ADR-0046] added `musubi.errors/1-draft` — a contract, declared in the code,
printed by a command, and consumed within a day by `sora`. It shipped:

- **no schema**, where the other three ship one inside the wheel;
- **no line in `docs/contracts.md`**, which still said *All three carry
  `-draft`*;
- **no entry in `schemas.CONTRACTS`**, so `path_to("musubi.errors/1")` raised
  for the one contract most likely to be looked up by name;
- **no row in the `schemas/` signpost.**

Nothing failed. The whole suite was green, four gates were green, and a
contract had been published in the sense that a program was already reading it
and in no other sense at all.

## Why nothing failed

Every guard around contracts read its population **from the wrong end**.

```text
test_the_contract_strings_in_the_code_are_the_ones_the_schemas_accept
    named two contracts by hand, out of four. It could not have noticed the
    journal either; the journal happened to be correct.

test_the_schema_is_a_schema
test_the_schema_says_it_describes_shape_only
    parametrised over [TRACE_MAP, SYNC_MANIFEST]. Two of four, by hand.
```

A guard that starts from the schemas that exist can only ever say *the schemas
that exist are fine*. It cannot say anything about a contract that has no
schema, which is the failure worth catching.

The one guard that **did** work is the one whose population came from the
files: `test_a_published_schema_is_packaged_with_the_wheel` walks
`src/musubi/schemas/*.json` and requires each to appear in the signpost. It went
red the moment the schema existed. That is the difference in one repository, in
one session.

## Decision

**The population is the contracts the code declares.**

```python
_DECLARES = re.compile(r'^[A-Z_]*CONTRACT[A-Z_]* = "(musubi\.[^"]+)"', re.M)
```

Every contract found that way must ship a schema reachable through `path_to`,
appear in `docs/contracts.md`, and match the pattern its own schema accepts.
The document is checked in the other direction too: a contract described there
and declared nowhere sends a consumer looking for something musubi never
writes.

**And the convention is not allowed to guard itself.** A second rule scans for
anything shaped like `musubi.<name>/<n>-draft` and requires it to be one of the
declared ones, so a contract assigned to a differently named constant is caught
rather than being invisible to every guard above.

`musubi.errors/1-draft` now ships a schema, has a section in
`docs/contracts.md`, is registered in `schemas.CONTRACTS`, is in the signpost,
and has a valid fixture that is **real command output** plus two
counter-examples.

## `musubi.sync/1` is not a contract, and the first guard demanded a schema for it

`frontmatter.PRODUCER` is `"musubi.sync/1"` — what musubi calls itself in a
document's metadata. Its own comment says it is contract-shaped and not a
version, deliberately, so that a release does not rewrite every artefact in a
corpus that has not changed.

The first version of the population regex swept it up and asked where its
schema was. The fix is the naming convention above rather than an exclusion
list, because the distinction is real: a contract is a constant named for being
one.

## What it costs

**A convention is now load-bearing.** `*CONTRACT = "musubi...."` is how a
contract is recognised, and somebody who declares one differently gets a
failing build with an explanation rather than a silent omission — which is the
trade, and it is why the second rule exists.

**Four hand-maintained lists became one derived population**, but the lists
themselves remain: `schemas.CONTRACTS` is still a dict somebody edits, and the
signpost is still a table. What changed is that forgetting either now fails.

**A schema for a document that is not written to a corpus.** The other three
describe what lands on a disk; this one describes musubi. It is the same shape
of artefact and it is worth saying out loud, because a consumer looking for
`errors.json` in a destination will not find one.

## Consequences

The contract's freeze condition is worth recording while this is fresh.
`musubi.errors/1` has the strongest candidate of the four and is the youngest:
`sora` asked for it because it was already scraping names off `stderr`, holds
it in its own `KNOWN` table, checks it in CI, and has stopped inferring
`retryable` in favour of the published value. That is a program that used one
and found something out — the condition — rather than a consumer written in
order to freeze it, which `docs/contracts.md` names as the condition run
backwards.

It is **not frozen here.** The wording belongs to `tsumugi` and the ambiguity
in it is unresolved, so the candidate is recorded in `docs/contracts.md` and
raised, which is what a seam decision gets rather than a quiet unilateral one.

[ADR-0002]: 0002-the-sync-manifest-is-a-document.md
[ADR-0023]: 0023-the-schemas-live-where-the-instruction-says.md
[ADR-0046]: 0046-a-failure-that-a-program-can-name.md
