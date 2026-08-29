# The concept

*This is the conceptual model. What is built lives in `docs/architecture.md`,
which does not exist yet; the plan lives in
[`proposals/0001-the-design.md`](proposals/0001-the-design.md).*

---

## The step nobody guarantees anything about

This family of projects is built on one idea, repeated at every layer: **say
where it came from.**

`kiseki` will not construct an interpretation without evidence. `tsumugi` will
not call something context unless it names the document, the offset and the hash.
`mamori` restores what it removed, to the character. `akashi` reports a
contradicted figure with an anchor into the source that says otherwise.

Four libraries, one discipline, and it stands on a step that has no discipline at
all.

Because somebody's knowledge is not a folder of clean Markdown. It is a Notion
workspace, seven years of Slack, a mail archive and four hundred PDFs. Something
has to convert all of that, and every converter in the world has the same
signature — bytes in, string out — and throws away the correspondence on the way.

So the evidence chain, followed all the way down, ends at a file that a program
invented last Tuesday. The anchor is real. The offset is right. And the thing it
points into is not the thing the owner has.

## What musubi does about it

musubi's converters do not return a string. They return a string **and a tiling**:
an ordered set of segments that covers every character of the output exactly
once, and says, for each one, which bytes of which original file it came from —
or that musubi wrote it.

That is the whole idea, and everything else in the library is a consequence.

```text
"the tent weighs 2.4kg"        synced/gear.md      [1204, 1225)
                                     ↑
                            musubi trace
                                     ↓
"the tent weighs 2.4kg"        ~/docs/gear.pdf     page 3, [1086, 1107)
```

A model's answer cites a package; the package cites a document; the document
cites a byte range in the owner's own PDF. For the first time the chain is
complete, and no link in it imports the next one.

## Why the conversion is where the danger is, too

It is not only that the correspondence is lost. It is that conversion is the one
step in the pipeline where content can be **created** without anybody noticing.

A two-column page read in the wrong order interleaves two arguments into
sentences that were never written. A table flattened into lines pairs the wrong
number with the wrong label. A boilerplate remover takes a paragraph of the
article with the navigation. In every case the output is fluent, plausible, and
undetectable — because every check downstream is defined *against the corpus*,
and the corruption is now part of the corpus.

Which is also why there is no model in a sync. An ingestion layer that "cleans up
the text with an LLM" writes its inventions into the ground truth. `akashi` would
then look at an answer quoting them and report, correctly, that it is grounded.
A fabrication laundered at ingestion time is invisible to every instrument built
to catch fabrications.

## The other half: musubi is the most dangerous component in the stack

It is the one pointed at everything.

The folder musubi reads contains the resignation letter, the notes about
colleagues, the mail archive, the `.env` somebody committed. The folder musubi
writes is built to be sent to a language model.

Every product in the connector category answers this with an API client holding
an OAuth token per service — which means a maintenance tax on every vendor, a
credential store that is the most attacked component in any local application,
and a privacy claim that can only ever be a promise about intent.

musubi answers it by having nothing. No sockets, anywhere, asserted by the build.
No tokens. No model. The input is an export the owner already made; the output is
a folder on their own disk. A program that cannot reach a network cannot leak to
one, and that is a sentence a build log can check.

And when it finds something that looks like a credential, it stops. Not skips —
skipping puts a hole in a corpus nobody reads the log of. It stops, promotes
nothing, and puts a person in front of the problem before the data moves.

## The five projects

```text
[ musubi ]   exports and folders ➔ clean documents that can point back at the byte
     ↓
[ kiseki ]   a photo timeline ➔ personal context, as facts / measures / interpretations
     ↓
[ tsumugi ]  selection ➔ a ContextPackage: what was sent, and what was withheld
     ↓
[ mamori ]   pseudonymization ➔ out to the model, and restoration on the way back
     ↓
[ akashi ]   the answer ➔ which particulars are traceable, and which are floating
```

Each is a separate library, separately installable, with zero runtime
dependencies and no import of its neighbours. They meet at published contracts —
`kiseki`'s record schemas, `tsumugi`'s ContextPackage, and now musubi's
SyncManifest and TraceMap — because a contract is the only kind of seam that lets
five projects release on five schedules.

musubi is the bottom of that stack. It is where the evidence chain either starts
honestly or does not start at all.

## The name

結び — a knot, a joining. Two things tied together, each still itself.
