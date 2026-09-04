"""What changed between one run and the one before it.

## Why musubi is the project this belongs in

Reviewed as *「証拠の履歴」を扱うのは musubi だけ* — of the six libraries, this is
the only one whose subject is what a corpus **was**. And most of the machinery
was already here without being used as history:

```text
content_hash    a document is identified by its bytes          content-addressed
run_id          a hash over exactly the inputs that decide     a *tree* id
determinism     the same inputs give the same id (ADR-0003)    reproducible
```

What was missing is the one thing that turns a series of snapshots into a
history: **a parent.** Each `sync` overwrote `manifest.json` and the previous
one was gone, so a corpus could say what it *is* and never what it *had been*.

And a `run_id` turned out not to be a commit id, which is a distinction this
module learned the hard way -- see `Entry.entry_id`. A corpus that comes back
to a state it held before comes back to the same id, so three entries answered
to the same short id and `--since` could not say which was meant. An entry
carries its own id, over the run *plus its parent and its time*, which is what
a commit has always been.

## What a journal entry holds, and what it deliberately does not

**Changes, not snapshots.** An entry records what was added, what changed and
what was removed, and says how many artefacts were untouched. It does not
repeat the corpus.

That is not a space optimisation, it is the difference between a feature that
works on a real corpus and one that does not. A manifest for ten thousand
artefacts is megabytes; a hundred runs of those is a history larger than the
thing it describes. **A no-change re-sync writes an almost empty entry**, which
is the common case and should cost nothing.

## What this is not, and the sentence that matters most

**This is history, not storage. musubi cannot restore a document it did not
keep.**

`musubi log` says a file changed on Tuesday and `musubi diff` says which files
those were. Neither can give you Monday's text, because the corpus holds one
version and the journal holds only what the change *was*. Rolling back needs
content storage, which is a different and much larger decision — and the
honest thing is to say so here rather than let *git-like* imply it.

What it does buy is the audit question, which is the one this family exists
for: **when did this document enter the corpus, what did it look like when it
did, and which run put it there.**
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from .hashing import hash_of

__all__ = [
    "CONTRACT",
    "Change",
    "Entry",
    "abbreviated",
    "changes",
    "entry_from",
    "folded",
    "run_named",
]

#: Not frozen. The freeze condition is a second program having needed it, not a
#: date ([ADR-0002]), and nothing outside musubi reads this yet.
CONTRACT = "musubi.run-journal/1-draft"


@dataclass(frozen=True, slots=True)
class Change:
    """What one run did to the corpus, against the run before it."""

    added: tuple[str, ...]
    changed: tuple[str, ...]
    removed: tuple[str, ...]
    #: Counted rather than listed. Naming every untouched artefact is what makes
    #: a journal grow with the corpus instead of with the work.
    unchanged: int

    @property
    def is_empty(self) -> bool:
        """Nothing moved. A re-sync of a folder nobody edited."""
        return not (self.added or self.changed or self.removed)

    @property
    def touched(self) -> int:
        return len(self.added) + len(self.changed) + len(self.removed)

    @property
    def total(self) -> int:
        """How many artefacts the corpus held **after** this change.

        Derivable rather than stored, and stated here once so that three
        callers do not each rederive it: what a run left untouched, plus what
        it added, plus what it changed. Removals are not in the total because
        they are not in the corpus.
        """
        return self.unchanged + len(self.added) + len(self.changed)

    def summary(self) -> str:
        if self.is_empty:
            return f"no change, {self.unchanged} artefacts"
        parts = []
        for label, names in (
            ("added", self.added),
            ("changed", self.changed),
            ("removed", self.removed),
        ):
            if names:
                parts.append(f"{len(names)} {label}")
        return f"{', '.join(parts)}, {self.unchanged} unchanged"


@dataclass(frozen=True, slots=True)
class Entry:
    """One run, and its place in the sequence."""

    run_id: str
    #: The `run_id` of the run this corpus was in before, or ``None`` for the
    #: first. The field that makes a sequence a history.
    parent: str | None
    created_at: str
    musubi_version: str
    kind: str
    change: Change

    @property
    def entry_id(self) -> str:
        """This entry's own id, which is **not** the corpus's.

        The distinction the first draft of this module did not have, and the
        one that git has: a ``run_id`` identifies the corpus a run produced,
        the way a tree id identifies a tree. It is a hash over the artefacts'
        content hashes ([ADR-0003]), so a corpus that returns to a state it was
        in before gets the same id back -- and it does, routinely:

        ```text
        add a.md      run 3f34b1
        edit a.md     run 0ecc39
        delete a.md   run 1bc3be   <- the same id as the run three back
        ```

        Three entries then answered to ``--since 1bc3be`` and the command could
        not say which history was meant. Adding the parent and the time is what
        makes an entry distinguishable, and it is exactly what a commit is: a
        tree, plus where it came from, plus when.

        Two entries sharing a ``run_id`` and differing here is not a fault. It
        is the corpus saying it came back to somewhere it had been.
        """
        return hash_of(
            {"run_id": self.run_id, "parent": self.parent or "", "created_at": self.created_at}
        )

    @property
    def short(self) -> str:
        """Enough of the id to name this entry to a person.

        The algorithm prefix is dropped for **display only**, because
        ``sha256:d6f95`` spends most of a short id saying what every id in the
        corpus says, and leaves five characters doing the distinguishing.
        `run_named()` matches on either form, so what is printed can be typed back.
        """
        return abbreviated(self.entry_id)

    @property
    def short_run(self) -> str:
        """The corpus this run produced, shortened. Ties a line to a manifest."""
        return abbreviated(self.run_id)

    @property
    def names_nothing(self) -> bool:
        """A run that left the corpus exactly as it found it.

        ``run_id`` is over the artefacts' content hashes ([ADR-0003]), so a run
        whose id equals its parent's produced the identical corpus -- and this
        is checkable without reading the change list, which is what makes it
        worth stating. The converse does not hold: a musubi upgrade changes the
        id while changing no document.
        """
        return self.run_id == self.parent

    def document(self) -> dict[str, object]:
        """The entry as the line it is written as."""
        return {
            "contract": CONTRACT,
            #: Derived, and written anyway so that a reader with `jq` does not
            #: have to reimplement the canonical form to key on a line. Read
            #: back it is *checked* rather than trusted (`entry_from`): a file
            #: that can name a different run than its own fields describe is a
            #: history that can lie about which corpus it is the history of.
            "entry_id": self.entry_id,
            "run_id": self.run_id,
            "parent": self.parent,
            "created_at": self.created_at,
            "musubi_version": self.musubi_version,
            "kind": self.kind,
            "added": list(self.change.added),
            "changed": list(self.change.changed),
            "removed": list(self.change.removed),
            "unchanged": self.change.unchanged,
        }


def changes(before: Mapping[str, str], after: Mapping[str, str]) -> Change:
    """What happened between two corpora, by artefact path and content hash.

    **Changed is decided by the hash, not by a timestamp.** A file rewritten
    with identical bytes did not change, and a corpus is derived data whose
    modification times say when musubi last ran rather than when anything moved
    ([ADR-0022] makes the same distinction for a document's own mtime).

    Sorted, because [ADR-0003] wants two runs over the same inputs to produce
    the same bytes, and a journal line is bytes.
    """
    gone = sorted(set(before) - set(after))
    fresh = sorted(set(after) - set(before))

    altered = []
    same = 0
    for path in sorted(set(before) & set(after)):
        if before[path] != after[path]:
            altered.append(path)
        else:
            same += 1

    return Change(
        added=tuple(fresh),
        changed=tuple(altered),
        removed=tuple(gone),
        unchanged=same,
    )


def entry_from(document: Mapping[str, object]) -> Entry:
    """One journal line, read back.

    Refuses a contract it does not recognise rather than reading hopefully,
    for the reason the manifest reader gives: a document parsed by guesswork is
    a history that says something the corpus never did.
    """
    contract = document.get("contract")
    if not isinstance(contract, str) or not contract.startswith("musubi.run-journal/1"):
        raise ValueError(
            f"a journal line declares contract {contract!r}, which this does not recognise"
        )

    run_id = document.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("a journal line has no run_id")

    parent = document.get("parent")
    unchanged = document.get("unchanged")
    entry = Entry(
        run_id=run_id,
        parent=parent if isinstance(parent, str) and parent else None,
        created_at=_text(document.get("created_at")),
        musubi_version=_text(document.get("musubi_version")),
        kind=_text(document.get("kind")),
        change=Change(
            added=_names(document.get("added")),
            changed=_names(document.get("changed")),
            removed=_names(document.get("removed")),
            unchanged=unchanged if isinstance(unchanged, int) else 0,
        ),
    )

    written = document.get("entry_id")
    if isinstance(written, str) and written and written != entry.entry_id:
        raise ValueError(
            f"the line names entry {abbreviated(written)} and its fields hash to "
            f"{entry.short}. One of the two was edited."
        )
    return entry


def folded(entries: Sequence[Entry]) -> Change:
    """The net effect of a run of entries, oldest first.

    What ``musubi diff`` answers: not what one run did, but what the corpus did
    across several. Added-then-removed cancels; added-then-changed is still
    added, because the corpus had neither before.

    **A path that left and came back is reported as changed, and that is the
    storage boundary showing through.** The journal knows it was removed and
    knows it was added; it does not keep the bytes, so it cannot tell you the
    two versions were identical. Reporting *changed* is the claim that is never
    false about the corpus's history, where *unchanged* could be.
    """
    state: dict[str, str] = {}
    for entry in entries:
        for path in entry.change.added:
            state[path] = "changed" if state.get(path) == "removed" else "added"
        for path in entry.change.changed:
            state[path] = "added" if state.get(path) == "added" else "changed"
        for path in entry.change.removed:
            if state.pop(path, None) != "added":
                state[path] = "removed"

    added = tuple(sorted(path for path, verb in state.items() if verb == "added"))
    changed = tuple(sorted(path for path, verb in state.items() if verb == "changed"))
    removed = tuple(sorted(path for path, verb in state.items() if verb == "removed"))

    # Derived from the last entry rather than carried: an entry says how many
    # artefacts it left untouched, so the corpus it left had
    # ``unchanged + added + changed`` artefacts in it. Anything in that total
    # this fold did not name is a file no run in the range touched.
    total = entries[-1].change.total if entries else 0
    return Change(
        added=added,
        changed=changed,
        removed=removed,
        unchanged=max(total - len(added) - len(changed), 0),
    )


def abbreviated(run_id: str, length: int = 12) -> str:
    """A run id shortened the way every tool that shows a hash shortens one."""
    _, _, digest = run_id.rpartition(":")
    return (digest or run_id)[:length]


def run_named(entries: Sequence[Entry], prefix: str) -> int:
    """The index of the one run a prefix names.

    Matched against the full id **and** the digest alone, so that what
    `Entry.short` printed can be typed back -- a short id nobody can paste is a
    short id that only looks like git's.

    Ambiguity is an error rather than the first match. Two runs sharing a
    prefix is a thing to be told about, not a coin flip about which history is
    being read.
    """
    wanted = prefix.strip()
    found = [
        index
        for index, entry in enumerate(entries)
        if entry.entry_id.startswith(wanted)
        or abbreviated(entry.entry_id, len(entry.entry_id)).startswith(wanted)
    ]
    if not found:
        raise LookupError(f"no run in this corpus has an id starting {wanted!r}")
    if len(found) > 1:
        raise LookupError(f"{wanted!r} names {len(found)} runs in this corpus; use more of the id")
    return found[0]


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _names(value: object) -> tuple[str, ...]:
    if not isinstance(value, Iterable) or isinstance(value, str | bytes):
        return ()
    return tuple(name for name in value if isinstance(name, str))
