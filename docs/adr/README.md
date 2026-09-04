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
| [0013](0013-one-output-contract-and-the-consumer-adapts.md) | One output contract, and the consumer adapts |
| [0014](0014-the-key-is-normalized-the-content-never-is.md) | The key is normalized, the content never is |
| [0015](0015-a-hash-names-its-algorithm.md) | A hash names its own algorithm, and the algorithm is SHA-256 |
| [0016](0016-a-rule-is-a-matcher-not-a-regular-expression.md) | A cleansing rule is a matcher, not a regular expression |
| [0017](0017-entropy-is-a-tier-not-a-default.md) | Entropy is a tier, not a default |
| [0018](0018-the-map-is-in-characters-and-the-file-says-what-a-byte-is.md) | The map is in characters, and the file says what a byte is |
| [0019](0019-a-record-inherits-what-it-describes.md) | A record inherits the classification of what it describes |
| [0020](0020-the-console-is-not-the-contract.md) | The console is not the contract, and the exit code reports the run |
| [0021](0021-an-empty-source-is-not-a-deletion.md) | An empty source is not a deletion, and the plan says so too |
| [0022](0022-the-document-keeps-the-day-it-was-written.md) | The document keeps the day it was written; musubi's own records keep the run's |
| [0023](0023-the-schemas-live-where-the-instruction-says.md) | The schemas live where the loading instruction says they do |
| [0024](0024-a-field-added-is-a-new-contract.md) | A field added is a new contract, not a wider old one |
| [0025](0025-a-map-with-no-verbatim-run-composes-whatever-it-measures.md) | A map with no verbatim run composes whatever it measures |
| [0026](0026-a-prefix-in-the-middle-of-a-blob-is-not-a-credential.md) | A prefix in the middle of a blob is not a credential |
| [0027](0027-the-nearest-file-wins-whole-and-every-value-says-where-it-came-from.md) | The nearest file wins whole, and every value says where it came from |
| [0028](0028-a-dependency-outside-the-domain-buys-quality-and-still-owes-a-map.md) | A dependency outside the domain buys quality, and still owes a map |
| [0029](0029-a-better-reader-does-not-buy-a-finer-locator.md) | A better reader does not buy a finer locator |
| [0030](0030-an-envelope-is-not-a-contract.md) | An envelope is not a contract |
| [0031](0031-a-guess-with-its-uncertainty-attached-is-not-the-guess-that-was-forbidden.md) | A guess with its uncertainty attached is not the guess that was forbidden |
| [0032](0032-the-shortest-way-in-is-the-one-that-keeps-the-map.md) | The shortest way in is the one that keeps the map |
| [0033](0033-a-threshold-that-nobody-swept-is-a-number-fitted-to-one-corpus.md) | A threshold that nobody swept is a number fitted to one corpus |
| [0034](0034-a-corpus-that-remembers-what-it-was.md) | A corpus that remembers what it was |

[0004](0004-a-conversion-carries-a-map-back-to-its-source.md) is the one to read
first. The rest of the design is arranged around it, and
[0005](0005-say-what-was-removed-and-by-which-rule.md) is what makes it honest.
[0007](0007-musubi-reads-exports-never-services.md) is the boundary that makes
everything else checkable.

Several are borrowed, with thanks, from the sibling projects `kiseki`, `mamori`,
`tsumugi` and `akashi`. Where that is the case the ADR says so and names the
original: a decision someone else already paid for is worth taking, and worth
attributing.
