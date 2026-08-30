# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The design, before the code: `docs/proposals/0001-the-design.md`, eighteen
  architecture decision records, `docs/concept.md`, and the documentation rules
  that keep current state, history and plans apart.
- The tooling that will enforce the design: the layering asserted by AST over
  every module, the `import-linter` contracts (three of them parked until the
  packages they name exist, with a test that turns the build red the moment one
  could be switched on), and a CI job that installs the wheel into a clean
  environment and asserts the runtime dependency count is zero.
- ADR-0013 narrows ADR-0010: musubi publishes one output family and ships no
  consumer-specific emitter. `kiseki` already has its own producers, and
  `kiseki-notes` reads exactly the folder musubi writes.
- `domain/span.py`: a half-open range of integer positions, which deliberately
  does not decide what a position indexes. A span over an artefact counts
  characters; a span over a PDF counts something else. The holder says, and the
  trace map records it.
- `domain/text.py`: `rewrite()`, the primitive every later stage is built out
  of. Deleting is replacing with the empty string, inserting is replacing an
  empty span, and the account of where every output character came from falls
  out of the one code path. Its pieces tile both the output and the source,
  checked on construction and by property tests. Plus `normalize_line_endings()`
  and `decode()`, which reads UTF-8 and UTF-16-with-a-BOM and refuses everything
  else rather than detecting — a guessed encoding writes mojibake into a corpus
  bound for a model and looks exactly like a successful read.
- `domain/trace.py`: `TraceMap`, the tiling ADR-0004 describes. Segments are
  `verbatim`, `transformed`, `synthetic` or `removal`, the kind is derived from
  the rewrite rather than declared by the converter, and the tiling of the
  artefact is checked on construction. `followed_by` composes two stages into
  one map from the artefact back to the source; it never claims the stronger of
  two kinds, and it splits a run where the earlier stage changed kind rather
  than degrading the whole of it. `traceable_coverage` publishes its numerator
  and denominator beside it.
- `domain/hashing.py`: `content_hash` and `hash_of`. Every hash names its own
  algorithm (ADR-0015), so a later change is a data change an old reader can
  refuse rather than a silent reinterpretation. Structured values are
  canonicalized by RFC 8785's rules for the clauses musubi's inputs reach —
  UTF-16 key ordering, minimal separators — and floats are refused, which is the
  one clause the specification makes hard and musubi never needs.
- `domain/record.py`: `Unit`, `unit_key` and `compare`. Identity is
  `(source_id, unit_key)`; change is `content_hash` (ADR-0006). Keys are built
  from parts, normalized to NFC, and refuse `.`, `..` and embedded separators
  (ADR-0014) — macOS hands back decomposed filenames and everything else hands
  back composed ones, so a key derived from a raw name makes one vault into two
  corpora. Content is never normalized: that would be an unrequested rewrite of
  what the owner wrote, and it would move every offset the trace map reports.
- `domain/removal.py` and `domain/cleansing.py`: the cleanser, and the record of
  what it took. A rule matches a parsed parameter name by `exact` or `prefix`
  (ADR-0016) — no regular expression runs over anybody's corpus, because
  Python's engine backtracks with no timeout and rules are user-editable data
  meeting arbitrary documents in an unattended loop. Finding a URL is a linear
  scan for the same reason. Every firing produces a `RemovalRecord` with the
  rule, the span and a hash — never the value (ADR-0005).
- `infrastructure/rules/core.py`: the first pack, derived from ClearURLs'
  `globalRules` with attribution, the date it was taken, and the entries
  deliberately not adopted — `[a-z]?mc` would strip `amc` and `bmc` from
  somebody's links.
- `domain/screening.py`, `ports/screener.py` and `infrastructure/screeners/`:
  the credential gate. The default tier is **signatures** — a prefix, an
  alphabet and a minimum length, checked by a linear scan — and entropy is a
  second tier that is off by default (ADR-0017). Entropy-only detection scores
  21.1% precision and 70.4% recall on CredData, and under ADR-0008's
  stop-the-run policy four false stops in five would make `--allow` reflexive
  inside a week. The entropy tier carries those numbers in the code, to be
  printed where it is switched on. Twenty-one signatures, each with its evidence
  and review date.
- `ports/source.py` and `infrastructure/sources/`: `FilesystemSource` and
  `ObsidianSource`. Two stages — `discover()` opens nothing and reports what it
  will skip and why; `read(found)` opens one thing. The walk is sorted at every
  level (ADR-0003) and the key is the path relative to the root, declared as the
  weak `path` derivation (ADR-0006). Pointing at a home directory or a
  filesystem root is refused (ADR-0007), a file symlink is followed only if it
  resolves inside the root, and a directory symlink is never followed.
- `ports/converter.py` and `infrastructure/converters/`: `MarkdownConverter`,
  `PlainTextConverter` and the media-type registry. Bytes in; text and a
  `TraceMap` out, or an `Unconvertible` value with its reason. Decoding and line
  endings are both real transformations and the map says so.
- A `TraceMap` now carries `source_unit`, and it is `characters` (ADR-0018). The
  byte version was implemented first and a test caught why it cannot work: an
  interior query shifts an offset by a character delta, which on a byte-measured
  map is wrong by every multi-byte character before it. The decoding travels
  beside the map; the command that opens the file converts. The verbatim
  equal-length check moved from `Segment` to `TraceMap` on the way, which is
  where it belonged.
- ADR-0014, ADR-0015, ADR-0016, ADR-0017 and ADR-0018.
- `span.resolve`, shared by `Rewritten` and `TraceMap`, and `Span.__bool__`,
  which is `True` always: `__len__` had made an empty span falsy, and
  `resolve(...) or Span(0, 0)` silently replaced a correct `[3:3]` with `[0:0]`.
- The `domain-no-io` layering contract, switched on by the arrival of the first
  domain module, as `tests/test_layering_config.py` requires.
- `musubi.errors`, and nothing else. No architecture document — there is no
  architecture yet, and a current-state document written before the code is
  fiction.

[Unreleased]: https://github.com/Nananananana/musubi/commits/main
