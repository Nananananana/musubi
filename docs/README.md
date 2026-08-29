# The documents, and what each one is for

musubi's documentation is written so that three different things never get
mistaken for one another:

- **what is true now** — the current architecture and rules;
- **why it became true** — the decisions, as they were made;
- **what might become true** — proposed and planned work.

A reader who cannot tell these apart will implement a proposal as though it
shipped, or "fix" an ADR to match today's code and erase the reasoning that
produced it. Both have a cost that grows with the project, so the separation is
structural: each document says at the top which of the three it is.

This convention is taken from the sibling projects `kiseki`, `tsumugi` and
`akashi`, which learned it the expensive way.

## Responsibilities

| Document | Responsibility |
|---|---|
| `README.md` | For anyone outside: what musubi is, what it solves, what it can do |
| `AGENTS.md` | For contributors and AI agents: the current rules, constraints and state |
| `docs/concept.md` | The conceptual model, and the whole picture across five projects |
| `docs/architecture.md` | The current architecture — **not written yet, on purpose** |
| `docs/sync-manifest.md` | The SyncManifest and TraceMap contracts, for producers and consumers |
| `docs/sources.md` | Per source: its key derivation, its rule pack, and `kiseki`'s ten questions answered |
| `docs/threat-model.md` | What a synced folder and a trace map contain, and what they become if they leak |
| `docs/evaluation-corpus.md` | The generated dataset: its shape, its plants, and what it cannot tell you |
| `docs/measurements.md` | Traceable coverage, map size, screener recall and the re-read ratio, with the tools that produced them |
| `docs/adr/` | Decisions as they were made, with their reasons — history |
| `docs/proposals/` | Proposed or planned work — not necessarily implemented |
| `CHANGELOG.md` | The released history, briefly |

## The rules that keep them apart

- An ADR is not edited to match the present. A decision that no longer holds is
  superseded by a later ADR that says so; the original stays as it was written,
  because the reasoning is the point.
- A proposal is never cited as evidence that something exists. When a proposal
  lands, the current-state documents change and the proposal stays where it is,
  describing what was proposed.
- The current-state documents describe what the code does today. If one of them
  disagrees with the code, one of the two is wrong and the disagreement is a
  defect — not a difference of opinion.
- An architecture document says why, not only what. A rule without its reason is
  a rule the next reader will break for good reasons of their own.
- **A number in a document is measured or it is not written.** Every table of
  scores names the script that produced it, the corpus it ran on, and what the
  number does not cover.

## Where the project is right now

**Nothing is built.** This repository currently contains the design, the
decisions behind it, and the tooling that will enforce them.

Read in this order:

1. [`proposals/0001-the-design.md`](proposals/0001-the-design.md) — the design
   and the roadmap, written before the code and left as written afterwards.
2. [`adr/0004`](adr/0004-a-conversion-carries-a-map-back-to-its-source.md) — the
   decision the rest of the design is arranged around.
3. [`adr/0005`](adr/0005-say-what-was-removed-and-by-which-rule.md) — the
   decision that makes 0004 honest.
4. [`adr/0007`](adr/0007-musubi-reads-exports-never-services.md) — the boundary
   that makes everything else checkable.
5. [`adr/README.md`](adr/README.md) — the rest.

`architecture.md` is deliberately absent. An ADR before the code is legitimate,
because it records a decision that has been made. A current-state document before
the code is fiction.
