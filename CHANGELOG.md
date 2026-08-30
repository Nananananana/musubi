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
- `musubi.errors`, and nothing else. No architecture document — there is no
  architecture yet, and a current-state document written before the code is
  fiction.

[Unreleased]: https://github.com/Nananananana/musubi/commits/main
