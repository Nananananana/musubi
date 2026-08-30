# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The design, before the code: `docs/proposals/0001-the-design.md`, thirteen
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
- `span.resolve`, shared by `Rewritten` and `TraceMap`, and `Span.__bool__`,
  which is `True` always: `__len__` had made an empty span falsy, and
  `resolve(...) or Span(0, 0)` silently replaced a correct `[3:3]` with `[0:0]`.
- The `domain-no-io` layering contract, switched on by the arrival of the first
  domain module, as `tests/test_layering_config.py` requires.
- `musubi.errors`, and nothing else. No architecture document — there is no
  architecture yet, and a current-state document written before the code is
  fiction.

[Unreleased]: https://github.com/Nananananana/musubi/commits/main
