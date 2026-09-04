# The schemas moved into the package

The contracts now live in [`../src/musubi/schemas/`](../src/musubi/schemas/):

| contract | file |
|---|---|
| `musubi.run-journal/1-draft` | [`musubi-run-journal-1.json`](../src/musubi/schemas/musubi-run-journal-1.json) |
| `musubi.sync-manifest/1-draft` | [`musubi-sync-manifest-1.json`](../src/musubi/schemas/musubi-sync-manifest-1.json) |
| `musubi.trace-map/1-draft` | [`musubi-trace-map-1.json`](../src/musubi/schemas/musubi-trace-map-1.json) |

This directory is a signpost and nothing else. Three of the four siblings keep
their schemas at the repository root and it is where a reader looks first, so
the pointer stays; **the files do not, because two copies of a contract are two
contracts as soon as somebody edits one.**

They moved because `docs/contracts.md` tells a consumer to load them with
`importlib.resources.files("musubi") / "schemas"`, and while they lived here that
sentence was **false in an editable install** — a build-time `force-include`
copied them into the wheel, so the instruction held for somebody who ran
`pip install musubi` and for nobody working on musubi. Nothing in the repository
ran the sentence it published.

[ADR-0023](../docs/adr/0023-the-schemas-live-where-the-instruction-says.md) has
the reasoning and what it costs. [`docs/contracts.md`](../docs/contracts.md) is
what a consumer should actually read.
