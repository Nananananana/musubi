# The contracts, for producers and consumers

> This describes the contracts as they stand today. Decisions are recorded in
> `docs/adr/`; proposed changes in `docs/proposals/`.

musubi writes two documents beside the corpus it builds, and both are contracts
rather than implementation details. Anything can produce them; anything can read
them. The schemas ship inside the wheel, because a consumer validating a
document should not have to fetch a schema from the internet, and an offline
tool whose schema lives on somebody else's server is not offline.

| Contract | Schema | Written to |
|---|---|---|
| `musubi.sync-manifest/1-draft` | [`schemas/musubi-sync-manifest-1.json`](../schemas/musubi-sync-manifest-1.json) | `<destination>/manifest.json` |
| `musubi.trace-map/1-draft` | [`schemas/musubi-trace-map-1.json`](../schemas/musubi-trace-map-1.json) | `<destination>/traces/<unit_key>.json` |

Worked examples, produced by the real emitter and validated on every push, are
in [`tests/contracts/`](../tests/contracts/README.md).

## Neither is frozen yet

Both carry `-draft`, and the suffix is the statement: the freeze has not
happened. It happens when **a second program has produced and consumed one** —
not on a date ([ADR-0002](adr/0002-the-sync-manifest-is-a-document.md)). Until
then a field may change meaning, and a consumer written today may need adjusting.

Three things have been proposed as that second program and are not:

- **musubi checking its own output.** `tests/test_invariants.py` validates real
  manifests and real maps against generated corpora, and `musubi verify` checks
  a corpus sitting on a disk. Both are worth having and neither counts: they are
  the producer reading itself, in the same package. The roadmap
  ([`proposals/0001-the-design.md`](proposals/0001-the-design.md) §9) guesses
  that `verify` is the likely second program for the manifest. It is not, and
  that document stays as written — it records what was planned, not what is.
- **A validator.** Checking a document against the schema exercises the schema.
  What the freeze is waiting for is a program that *used* one and found out
  something — and the interesting failures are the ones no schema can express,
  which is the whole of the next section.
- **A consumer written in order to freeze it.** A contract freezes because
  something needed it. Picking a consumer to satisfy the condition is the
  condition run backwards, and leaves a frozen contract with nothing behind it.

Today `musubi.trace-map/1` has a candidate — a resolver written against it
outside this project, taking an anchor through to a byte range in an original
file — and `musubi.sync-manifest/1` has none. Neither is scheduled, because a
date is exactly what this rule refuses.

One ambiguity is inherited along with the rule: read strictly, *a second program
has produced and consumed one* asks the same program to do both, which for a
format musubi is currently the only writer of would mean never. musubi reads it
as the pair — musubi produces, something else consumes — and the wording belongs
to `tsumugi`, so the family should settle it rather than each project deciding
quietly.

Once frozen: a field may be added; none will be removed or change meaning. A
field addition is a schema revision, and an old validator will refuse a newer
document because every object is `additionalProperties: false`. That is
deliberate and fail-closed — a consumer that cannot see the whole of what it was
handed should say so rather than read the part it recognises.

A reader that does not recognise a `contract` value refuses the document rather
than parsing it hopefully.

## What these schemas cannot say

**A schema handed over as "the contract" gets read as the whole of it.** It is
not. JSON Schema 2020-12 cannot compare two properties of one object, so it
cannot express `end >= start`; and it cannot express any statement that needs a
second document, or arithmetic, or the source file. The most important invariant
in the trace map is in that category.

Everything below is part of the contract and is **not** checked by either
schema. A consumer that needs it checks it.

### The trace map

1. **The segments cover every character of the artefact exactly once.** In
   order, no gap, no overlap, ending exactly at `coverage.characters`. This is
   the property the map exists for; a map with a gap answers a query with
   silence, and one with an overlap answers it twice. It is not expressible in
   JSON Schema in any form.
2. **Every span runs forwards.** `end >= start`, for both `out` and `src`, in
   every segment.
3. **A verbatim segment reads the same on both sides.** Checking it needs the
   artefact *and* the source; a schema has neither.
4. **A removal occupies no output.** `out[0] == out[1]` — two members of one
   array, which is exactly what cannot be compared.
5. **`coverage.traceable` is the sum of the `verbatim` and `transformed`
   segments' output lengths**, and is at most `coverage.characters`.
6. **`src` ranges need not be monotonic**, and a reader must not assume they
   are. A two-column page read in reading order produces a map whose source
   ranges jump, and the jump is information rather than a defect.

`tests/test_trace_map.py` and `tests/test_contract_conformance.py` assert 1, 2,
4 and 5 against real output. Property tests over generated documents are what
turn them from *checked on these examples* into *checked at all*.

### The sync manifest

1. **`run_id` re-derives.** It is a hash over the canonical form of exactly the
   inputs ([ADR-0015](adr/0015-a-hash-names-its-algorithm.md)); confirming it
   means re-running, which is what `musubi verify` will be for. No schema can do
   it.
2. **`coverage.units_read == emitted + skipped`**, and
   `traceable_characters <= characters`.
3. **A `removal` or a `finding` names a `unit_key` that appears somewhere in the
   run** — as an artefact, or as a skip.
4. **An artefact's `trace_map` names a file that exists**, and that file's
   `artefact.content_hash` equals the artefact's.

### And what a schema cannot check at all

A trace map and its artefact belong to the same run. **The map does not carry
`run_id`**, and the omission is deliberate: it would change every trace map on
every run that changed anything, so promotion would rewrite the whole corpus and
[ADR-0006](adr/0006-the-unit-of-sync-is-the-record.md)'s incrementality would be
gone. The pairing that matters is checkable anyway — a map carries
`artefact.content_hash`, so a reader holding the artefact can confirm the map is
about the bytes in front of them.

## What these documents are, if they leak

**The whole destination is one classification**
([ADR-0019](adr/0019-a-record-inherits-what-it-describes.md)). `documents/`,
`traces/` and `manifest.json` are the same secret, and a trace map is **not** the
safe half.

That is worth stating plainly, because a trace map looks like metadata and is
therefore the thing most likely to be attached to an issue first. To a reader who
does not have the documents it describes, one contains:

- **the owner's filenames and folder structure**, in full;
- **the document's silhouette** — the length and position of every paragraph,
  line break and link. A length is the shape of a value;
- **what was in it** — a segment's `rule` saying `tracking.mc-eid` says the owner
  is on a Mailchimp list.

The manifest is the same. `removals` records what was taken and where, which is
information about what was there; a manifest from a run that stopped says *this
source contains a credential*.

Two things are deliberately **not** in these documents, and a producer that is
not musubi should keep them out too:

- **A removed value.** Only its `sha256`. The removed thing is usually the
  sensitive thing, and a manifest quoting it would re-publish, into a file people
  commit, exactly what the run was for
  ([ADR-0005](adr/0005-say-what-was-removed-and-by-which-rule.md)).
- **A finding's offset or length.** A finding points at a credential still in the
  owner's file and still valid; an offset and a length are the targeting
  information an attacker would want, and the owner does not need them to act.
  The terminal report has both, because a person looking at their own screen is
  who the run stopped for
  ([ADR-0019](adr/0019-a-record-inherits-what-it-describes.md)).

## Offsets, and what they are counted in

A trace map's `src` offsets are **characters of the decoded text**, and
`source_unit` says so on every document
([ADR-0018](adr/0018-the-map-is-in-characters-and-the-file-says-what-a-byte-is.md)).

They are not bytes, and the reason is worth knowing before writing a consumer:
resolving an interior offset means shifting by a constant inside a verbatim run,
and that constant counts characters. On a byte-measured map the arithmetic is
silently wrong by every multi-byte character before it.

Turning a character offset into a byte offset takes three things — `encoding`,
`bom_bytes` and **the source file** — and a consumer holding the file has all
three:

```python
byte_offset = bom_bytes + len(source_text[:character_offset].encode(encoding))
```

`source_unit` currently has one value. A future locator — a PDF page plus an
offset within it — will be a different one, and an old validator **refusing** it
is the intended behaviour: seeing that it is not a character map is better than
reading one field as another.

## Which folder to read

`<destination>/documents` — and only that one.

Separating the trees makes the correct invocation *available*; it does not make
an incorrect one safe, and an incorrect one is silent. Measured against a real
`tsumugi`:

```text
tsumugi ingest corpus/documents   ->  2 new
tsumugi ingest corpus             ->  5 new
```

The five are the documents, `manifest.json` and the trace maps, indexed by
section heading — so a search for a word that appears in a trace map returns the
*map* of a document rather than the document, and the corpus is holding a
per-character index of itself. `0 skipped, 0 failed`; nothing says anything went
wrong.

`traces/` and `manifest.json` are musubi's own records. They are documents in
the sense of [ADR-0002](adr/0002-the-sync-manifest-is-a-document.md) — read them
as contracts — and they are not documents to *index*.

## Writing a consumer

1. Check `contract`. Refuse a value you do not recognise.
2. Validate against the schema shipped in the wheel:
   `importlib.resources.files("musubi") / "schemas"`.
3. Check the invariants above that you depend on. The schema did not.
4. Treat what you read as carrying the classification of the corpus it describes.
