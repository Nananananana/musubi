# 0051. A title the document actually wrote

**Status:** accepted
**Date:** 2026-09-11
**Context:** [ADR-0040], [ADR-0001], `sora`'s reply of 2026-09-11

## Two defects in one field, found by checking what a consumer had written down

`sora` reported back with no new requirements and a note about how it will read
`artefacts[].title` when it starts showing one:

> `title` が `null` なのは**文書が何も言わなかった**とき、`""` なのは
> **意図して何も言わなかった**とき。ホスト名に落ちてよいのは前者だけ。

That is exactly what `docs/contracts.md` told them to do, and it is a branch
for a value **musubi has never once produced**.

### The empty string never arrived

[ADR-0040] decided it plainly, and the contract repeated it to consumers:

> `null` and the empty string are different answers and a consumer must not
> collapse them. A document that states `title:` with nothing after it has said
> something; a document that says nothing has not.

`title_of` returned `value or None`, so a stated-empty title and a document
that said nothing both arrived as `null`. The test guarding it is the clearest
statement of the problem in the repository, because **its docstring was the
justification for the distinction and its assertions destroyed it**:

```python
def test_an_empty_title_is_none_and_not_the_empty_string() -> None:
    """... A consumer that cannot tell them apart falls back for the wrong one."""
    assert title_of("---\ntitle:\n---\n\n# A heading\n") is None
```

### And a quoted title kept its quotes

Worse in practice, and unrelated to any decision:

```text
  title: "A name"          ->  '"A name"'
  title: "gear: a list"    ->  '"gear: a list"'
  title: "設計メモ: 2026"   ->  '"設計メモ: 2026"'
```

**YAML requires quoting for a value containing a colon.** A note called
`gear: a list` cannot be written any other way, so this is not an exotic
input — and the quote marks went into the manifest, and would have gone onto
the screen `sora` is building.

The field exists so that a consumer does not have to open a document to name
it ([ADR-0040], R7). It was handing back a name no document claimed.

## Decision

**`title_of` returns what the document wrote.**

- A stated-but-empty title is `""`; a document that says nothing is `null`.
  The two are different answers, which is what the contract has always said.
- One matching pair of surrounding quotes is taken off.
- An **unterminated** quote is repeated as written. This is not a YAML parser
  and does not become one ([ADR-0001] keeps the runtime at zero dependencies);
  guessing at what an author meant by `title: "unclosed` is worse than
  repeating it, and repeating is the standing every other front-matter value
  has here.

## What it costs

**Manifests now contain `""` where they contained `null`.** The schema already
permitted it — `["string", "null"]`, no minimum length — so no contract moves,
and a consumer that collapsed the two was told not to. One that reads `title`
as truthy sees no change: both are falsy.

**Titles change for documents whose authors quoted them.** A re-sync rewrites
those manifests, and `content_hash` does not move because the title is derived
from the artefact's text and is not in `run_id` ([ADR-0040]). The corpus is the
same; the name musubi reports for it is now the one the document gave.

**A quote-stripping rule that a real YAML parser would do better.** Single and
double, one pair, no escape handling. The alternative is a dependency in the
domain, which ADR-0001 refuses, and the limit is stated rather than implied.

## The shape of it

This is the fourth consumer-facing claim this month that was true of the
documents and not of the code, and the second found by **checking something the
consumer wrote down** rather than by reading musubi. The other was
`artefacts[].title` being `null` about half the time, which `sora` was told
about and had not hit yet.

A contract that promises a distinction the producer cannot make is worse than
one that promises nothing: the consumer writes the branch, the branch is
correct, and it never runs. Neither side has anything to notice.

The guard is the one the last five findings arrived at, in the smallest form it
takes here: a test whose assertions are checked against its own docstring by a
person, which is not a guard at all. What made this one visible was a consumer
writing their reading of the contract down where musubi could read it back.

[ADR-0001]: 0001-the-domain-depends-on-nothing.md
[ADR-0040]: 0040-a-corpus-says-what-it-holds-and-what-it-is-called.md
