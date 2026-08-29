# Architecture decision records

One file per decision that changed a boundary, a default, or a guarantee. Each
says what the situation was, what was chosen, what follows from it, and — the
part that is usually missing — **what it costs**.

A decision recorded before the code exists is still a decision. These were made
while refining the design, and they are why the design looks the way it does.
What is *intended* next lives in
[docs/proposals](../proposals/0001-the-design.md) instead; an ADR records a
decision already taken, and a plan is neither.

An ADR is never edited to match the present. When a decision stops holding, a
later ADR supersedes it and says so.

| # | Decision |
|---|---|
| [0001](0001-the-domain-depends-on-nothing.md) | The domain layer imports only the standard library |
| [0002](0002-the-sync-manifest-is-a-document.md) | The sync manifest is a document, not a type |
| [0003](0003-a-sync-is-reproducible.md) | A sync is reproducible, and no model runs inside one |
| [0004](0004-a-conversion-carries-a-map-back-to-its-source.md) | A conversion carries a map back to its source |
| [0005](0005-say-what-was-removed-and-by-which-rule.md) | Say what was removed, and by which rule |
| [0006](0006-the-unit-of-sync-is-the-record.md) | The unit of sync is the record, not the file |
| [0007](0007-musubi-reads-exports-never-services.md) | musubi reads exports, never services |
| [0008](0008-a-credential-stops-the-run.md) | A credential stops the run, and musubi does not redact it |
| [0009](0009-cleansing-rules-are-data.md) | Cleansing rules are data, and each one names its evidence |
| [0010](0010-write-the-contracts-import-neither-consumer.md) | Write the consumers' contracts, import neither consumer |
| [0011](0011-redundancy-is-marked-never-resolved.md) | Redundancy is marked, never resolved |
| [0012](0012-a-dry-run-comes-first.md) | A dry run comes first |

[0004](0004-a-conversion-carries-a-map-back-to-its-source.md) is the one to read
first. The rest of the design is arranged around it, and
[0005](0005-say-what-was-removed-and-by-which-rule.md) is what makes it honest.
[0007](0007-musubi-reads-exports-never-services.md) is the boundary that makes
everything else checkable.

Several are borrowed, with thanks, from the sibling projects `kiseki`, `mamori`,
`tsumugi` and `akashi`. Where that is the case the ADR says so and names the
original: a decision someone else already paid for is worth taking, and worth
attributing.
