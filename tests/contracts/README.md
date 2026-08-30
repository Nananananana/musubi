# Contract fixtures

Worked examples of the two documents musubi writes, and counter-examples that
must be refused.

## The valid ones came off a disk

`trace-map-valid.json` and `sync-manifest-valid.json` are **real output**: a
real vault, read by the real source, converted by the real converter, cleansed
by the real ruleset, written and promoted by the real emitter. The only edit is
the source `root`, replaced with `/home/owner/notes` so that a published example
does not name somebody's disk — a field that is excluded from `run_id` for
exactly that reason.

They are generated rather than written, and that is the point. `tsumugi` shipped
a frozen contract and a reference producer and had never validated its own real
output against its own schema; the helpers built documents by hand and validated
those. The first run against genuine output found a genuine bug, in a default
that was the empty string where the contract said `minLength: 1`. Every package
built through the library API was non-conformant and nobody had looked.

So `test_contract_conformance.py` does not trust these files. It builds a corpus
with the real emitter and validates what lands on the disk, and it runs the real
command and validates what it prints. These are here for a third party writing a
consumer, who deserves a document to write it against rather than a docstring to
write it from.

The example note is chosen to have everything a document can have: its own front
matter, a heading, CJK text whose characters are not its bytes, a tracking
parameter to remove, and CRLF line endings from whichever machine wrote it.

## The invalid ones are one edit each

Every `*-invalid-*.json` is the valid document with exactly one thing wrong, so
that a `diff` against the valid example shows precisely which rule it exercises.
A schema nothing fails is not a schema.

| Fixture | The rule it exercises |
|---|---|
| `trace-map-invalid-unknown-contract` | a reader refuses a version it does not recognise |
| `trace-map-invalid-verbatim-names-a-rule` | nothing happened to a verbatim run, so there is nothing to attribute |
| `trace-map-invalid-removal-without-a-rule` | everything that is not verbatim says what did it |
| `trace-map-invalid-span-of-three` | a span is two offsets |
| `trace-map-invalid-bare-digest` | a hash names its own algorithm (ADR-0015) |
| `trace-map-invalid-unknown-kind` | the four kinds are the four kinds |
| `trace-map-invalid-extra-key` | a field nobody declared |
| `trace-map-invalid-no-coverage` | the denominator is not optional |
| `sync-manifest-invalid-unknown-kind` | a run is a plan or a sync |
| `sync-manifest-invalid-no-limits` | a manifest with no limits claims it has none |
| `sync-manifest-invalid-interpretation` | musubi has no model, so it states no interpretation (ADR-0010) |
| `sync-manifest-invalid-removal-carries-the-value` | a removal carries a hash, never the value (ADR-0005) |
| `sync-manifest-invalid-finding-carries-the-value` | and neither does a finding |
| `sync-manifest-invalid-no-key-derivation` | a source declares how it derived its keys (ADR-0006) |
| `sync-manifest-invalid-unhashed-run-id` | an id is a hash that names its algorithm |
| `sync-manifest-invalid-negative-coverage` | a count is not negative |

## What is not here

Everything the schema cannot express, which includes the invariant the trace map
exists for. `docs/contracts.md` enumerates it; `test_trace_map.py` and the
invariant tests are where it is checked. A fixture set cannot substitute for a
property test, and neither can substitute for the other.
