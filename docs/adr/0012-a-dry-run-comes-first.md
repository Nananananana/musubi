# 12. A dry run comes first

**Status:** accepted

Generalised from `kiseki`'s NoteRecord contract, which requires a producer to
show what it would record before it records anything.

## Context

`kiseki` states the reason in one sentence: a misclassified photograph can be
looked at again; a misclassified note cannot, because the text is gone.

musubi is that situation everywhere. It removes bytes under rules (ADR-0005), it
converts formats it may handle badly (ADR-0004), it stops on things it believes
are credentials (ADR-0008), and it writes a folder somebody will point a language
model at. The first run over a real vault is the run most likely to be wrong,
because it is the run where none of the rules have met this particular corpus
yet.

An ingestion tool whose first action is to write is a tool whose mistakes are
discovered afterwards.

## Decision

**`musubi plan` is a first-class command, it writes nothing, and it is the
default posture of the project.**

`plan` reads everything a sync would read and reports what would happen: the
records it found and their keys, the artefacts it would write, the conversions it
would refuse, the removals each rule would make, the credential hits, and the
traceable coverage it would achieve. The output is a manifest of the same shape
as a real run's, marked as a plan.

`musubi sync` is the second command, and it stages before it promotes (ADR-0008),
so even the real run is reversible until the last step.

**For any path that discards text irreversibly, a plan is mandatory.** The known
case is `kiseki`'s NoteRecord, where the producer classifies a note and then
keeps only a category — the text is deliberately not carried, and `kiseki`'s own
contract already requires the two-step. musubi implements it as a rule rather
than a courtesy: `sync` refuses to run such an emitter unless a matching plan for
the same input exists, identified by its `run_id`.

`plan --show-removals` is the one place values are printed rather than hashed,
and they go to the terminal only, never to a file (ADR-0005).

## Consequences

Every emitter is written so that its decisions can be computed without being
applied. That is a real design constraint and a useful one — it is the same
constraint that makes the whole pipeline a pure function of its inputs
(ADR-0003), reached from a different direction.

It also gives the project its demonstration. `musubi plan ~/vault` over somebody
else's real notes prints what would be removed and what would be traceable,
without writing a byte, which is the only honest way to introduce a tool like
this.

## What it costs

Two commands where one would do, and a first run that takes twice as long. For a
large export that is minutes, and it is the correct place to spend them.

The mandatory-plan rule can also be gamed — a plan run and immediately forgotten,
`sync` satisfied by an id nobody read. musubi cannot fix that and does not
pretend to. What it can do is make the plan cheap to read and make the manifest
record that the plan was consulted, which is where an auditor would look.
