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

## Everything here is linear in what the history names

A first sync of ten thousand documents writes one entry naming ten thousand
paths, and `musubi log` prints its summary. The first version of this module
kept the hashes as a tuple of pairs and looked them up by scanning, so that
summary cost ten thousand scans of ten thousand pairs -- the quadratic this
repository keeps finding one layer at a time (`TraceMap.followed_by`, the
Notion archive). The maps are dicts, the per-entry membership is a set built
once, and `attribution` walks the history once rather than once per path.

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
from dataclasses import dataclass, field
from types import MappingProxyType

from .hashing import hash_of

__all__ = [
    "CONTRACT",
    "Attribution",
    "Change",
    "Entry",
    "abbreviated",
    "attribution",
    "changes",
    "entry_from",
    "folded",
    "run_named",
    "touching",
]

#: Not frozen. The freeze condition is a second program having needed it, not a
#: date ([ADR-0002]), and nothing outside musubi reads this yet.
CONTRACT = "musubi.run-journal/1-draft"

_NOTHING: Mapping[str, str] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class Change:
    """What one run did to the corpus, against the run before it."""

    added: tuple[str, ...]
    changed: tuple[str, ...]
    removed: tuple[str, ...]
    #: Counted rather than listed. Naming every untouched artefact is what makes
    #: a journal grow with the corpus instead of with the work.
    unchanged: int
    #: What each path holds **after** this run: every `added` and `changed`
    #: path, and nothing else. A removed path holds nothing.
    #:
    #: A mapping, looked up rather than scanned. The line it becomes is sorted
    #: when it is written, which is where [ADR-0003]'s same-bytes promise is
    #: kept; keeping the pairs sorted *here* bought nothing and cost a scan per
    #: lookup ([ADR-0035]).
    hashes: Mapping[str, str] = _NOTHING
    #: What each path held **before** this run: every `changed` and `removed`
    #: path. Two maps rather than one with two meanings -- the first draft put
    #: the after-hash for added and changed and the before-hash for removed
    #: into a single map, and a fold could then not tell what a changed path
    #: had been, so a document edited and edited back inside a range read as
    #: changed. Hypothesis found it in three runs.
    previous: Mapping[str, str] = _NOTHING
    #: Whether everything this describes was decided by comparing hashes. True
    #: for a run, which measures its own corpus. False for a `folded()` answer
    #: over a range containing a line written before [ADR-0035], where some
    #: path fell back to the conservative verb.
    exact: bool = True
    #: The pairs `moves` found, kept so that `summary()` and a report that
    #: prints the lists do not each search again. Derived in `__post_init__`
    #: from fields that are frozen, so it cannot go stale.
    _moves: tuple[tuple[str, str], ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_moves", self._pair_moves())

    def hash_for(self, path: str) -> str | None:
        """What this path holds after the run, or ``None``.

        ``None`` for a path the run removed or did not touch, and also for a
        line written before [ADR-0035] -- which is why callers branch on it
        rather than assuming. A history that spans the change has entries of
        both kinds.
        """
        return self.hashes.get(path)

    def hash_before(self, path: str) -> str | None:
        """What this path held before the run, or ``None``."""
        return self.previous.get(path)

    @property
    def moves(self) -> tuple[tuple[str, str], ...]:
        """Paths that left and paths that arrived holding the same bytes.

        What content addressing buys, and the reason it was worth carrying the
        hashes: a rename is a `removed` and an `added` in every journal that
        records only paths, and there is no way to tell it from a deletion that
        happened to coincide with an unrelated new file.

        Pairs are made only where a hash matches **exactly one** on each side.
        Two files with identical content -- an empty note, a stub copied twice
        -- are not evidence about which became which, and guessing would put a
        confident wrong answer where an honest silence belongs. Those stay in
        `added` and `removed`, which is what they are.
        """
        return self._moves

    @property
    def moved(self) -> frozenset[str]:
        """Every path that is one half of a move, for a report to skip over."""
        return frozenset(path for pair in self._moves for path in pair)

    @property
    def touches(self) -> frozenset[str]:
        """Every path this change names, for membership rather than scanning."""
        return frozenset(self.added) | frozenset(self.changed) | frozenset(self.removed)

    def _pair_moves(self) -> tuple[tuple[str, str], ...]:
        gone = _by_hash(
            (path, self.previous[path]) for path in self.removed if path in self.previous
        )
        arrived = _by_hash((path, self.hashes[path]) for path in self.added if path in self.hashes)
        return tuple(
            sorted(
                (gone[digest][0], arrived[digest][0])
                for digest in gone.keys() & arrived.keys()
                if len(gone[digest]) == 1 and len(arrived[digest]) == 1
            )
        )

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
        """The one-line account, with moves counted once rather than twice.

        A rename is a `removed` and an `added` in the lists, because that is
        what the corpus did. Reporting it in the headline as both would have a
        run that renamed one file read as *1 added, 1 removed* -- two events,
        neither of which happened.
        """
        if self.is_empty:
            return f"no change, {self.unchanged} artefacts"

        paired = self.moved
        parts = []
        for label, names in (
            ("added", self.added),
            ("changed", self.changed),
            ("removed", self.removed),
        ):
            rest = sum(1 for path in names if path not in paired)
            if rest:
                parts.append(f"{rest} {label}")
        if self._moves:
            parts.append(f"{len(self._moves)} moved")
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
        """The entry as the line it is written as.

        The maps come out sorted, which is where the same-inputs-same-bytes
        promise ([ADR-0003]) is kept for a journal line -- not in the
        in-memory shape, which is looked up and never compared byte for byte.
        """
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
            #: Both sides of every path the three lists name. What turns a
            #: removed-and-added pair into a move, and what lets a fold over a
            #: range say *unchanged* where it used to have to say *changed*
            #: ([ADR-0035]).
            "hashes": dict(sorted(self.change.hashes.items())),
            "previous": dict(sorted(self.change.previous.items())),
        }


def changes(before: Mapping[str, str], after: Mapping[str, str]) -> Change:
    """What happened between two corpora, by artefact path and content hash.

    **Changed is decided by the hash, not by a timestamp.** A file rewritten
    with identical bytes did not change, and a corpus is derived data whose
    modification times say when musubi last ran rather than when anything moved
    ([ADR-0022] makes the same distinction for a document's own mtime).

    The lists are sorted, because [ADR-0003] wants two runs over the same
    inputs to produce the same bytes, and a journal line is bytes.
    """
    gone = sorted(before.keys() - after.keys())
    fresh = sorted(after.keys() - before.keys())

    altered = []
    same = 0
    for path in sorted(before.keys() & after.keys()):
        if before[path] != after[path]:
            altered.append(path)
        else:
            same += 1

    # Both sides of every path that moved. The before-hash of a removed
    # artefact is the last thing known about it, and it is what makes a rename
    # legible ([ADR-0035]); the before-hash of a changed one is what lets a
    # fold say that a document edited and edited back is where it started.
    return Change(
        added=tuple(fresh),
        changed=tuple(altered),
        removed=tuple(gone),
        unchanged=same,
        hashes={path: after[path] for path in fresh + altered},
        previous={path: before[path] for path in altered + gone},
    )


def entry_from(document: Mapping[str, object]) -> Entry:
    """One journal line, read back.

    Refuses a contract it does not recognise rather than reading hopefully,
    for the reason the manifest reader gives: a document parsed by guesswork is
    a history that says something the corpus never did. And refuses a line
    whose lists overlap, for the same reason: a path both added and removed by
    one run is not a thing a run can do, and folding it would decide which
    half to believe.
    """
    contract = document.get("contract")
    if not isinstance(contract, str) or not contract.startswith("musubi.run-journal/1"):
        raise ValueError(
            f"a journal line declares contract {contract!r}, which this does not recognise"
        )

    run_id = document.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("a journal line has no run_id")

    added = _names(document.get("added"))
    changed = _names(document.get("changed"))
    removed = _names(document.get("removed"))
    if len(set(added) | set(changed) | set(removed)) != len(added) + len(changed) + len(removed):
        raise ValueError("a journal line names one path in two of added, changed and removed")

    parent = document.get("parent")
    unchanged = document.get("unchanged")
    entry = Entry(
        run_id=run_id,
        parent=parent if isinstance(parent, str) and parent else None,
        created_at=_text(document.get("created_at")),
        musubi_version=_text(document.get("musubi_version")),
        kind=_text(document.get("kind")),
        change=Change(
            added=added,
            changed=changed,
            removed=removed,
            # `bool` is an `int`, and `true` is not a count of anything.
            unchanged=unchanged
            if isinstance(unchanged, int) and not isinstance(unchanged, bool)
            else 0,
            hashes=_hashes(document.get("hashes")),
            previous=_hashes(document.get("previous")),
        ),
    )

    written = document.get("entry_id")
    if isinstance(written, str) and written and written != entry.entry_id:
        raise ValueError(
            f"the line names entry {abbreviated(written)} and its fields hash to "
            f"{entry.short}. One of the two was edited."
        )
    return entry


#: A path the corpus did not hold at one end of a range.
#:
#: An explicit marker rather than a key missing from the dict, and the
#: difference is a bug this had: *not in the corpus then* and *this fold has
#: not met it yet* are both "no entry", and conflating them made a path added
#: and then changed inside a range look like a path that was already there.
ABSENT = "\x00absent"

#: A path the fold knows is in the corpus at one end, and whose content that
#: range does not record -- a line written before [ADR-0035]. Not the same as
#: absent and not the same as a known hash, and conflating either with a hash
#: is how a fold starts claiming things it cannot know.
PRESENT = "\x00present"


def folded(entries: Sequence[Entry]) -> Change:
    """The net effect of a run of entries, oldest first.

    What ``musubi diff`` answers: not what one run did, but what the corpus did
    across several. Added-then-removed cancels; added-then-changed is still
    added, because the corpus had neither before.

    **Two states per path rather than a verb.** The first draft folded verbs --
    added, changed, removed -- and so could not tell a document that left and
    came back unaltered from one that came back rewritten. It reported
    *changed* for both, and [ADR-0034] had to publish the divergence as a
    limit. Carrying the hashes ([ADR-0035]) turns the whole of that into
    arithmetic: what a path held when the range began against what it holds
    now. The answer is then exactly what `changes()` gives for the two ends,
    and there is nothing left to caveat.

    **A line written before the hashes existed cannot be folded exactly**, and
    the result says so instead of guessing: those paths compare `PRESENT`
    against something, which is never equal, so they fall back to *changed* --
    the claim that is never false -- and `exact` is false for the whole
    answer. One unhashed line in a range is one place the arithmetic could not
    reach, and a reader told which half of a mixed history they are looking at
    can decide what to do about it.
    """
    #: path -> what it held when the range began, `ABSENT`, or `PRESENT`.
    origin: dict[str, str] = {}
    #: path -> what it holds now, or `ABSENT`.
    current: dict[str, str] = {}
    exact = True

    for entry in entries:
        change = entry.change
        for path in change.added:
            # Only if this range has not already decided: a path removed and
            # then added back began the range with what the removal recorded.
            origin.setdefault(path, ABSENT)
            now = change.hashes.get(path)
            current[path] = now or PRESENT
            exact = exact and now is not None
        for path in change.changed:
            # Changed without having been added here means it was there before
            # the range, holding whatever this entry says it held.
            was, now = change.previous.get(path), change.hashes.get(path)
            origin.setdefault(path, was or PRESENT)
            current[path] = now or PRESENT
            exact = exact and was is not None and now is not None
        for path in change.removed:
            was = change.previous.get(path)
            origin.setdefault(path, was or PRESENT)
            current[path] = ABSENT
            exact = exact and was is not None

    added, altered, gone = [], [], []
    hashes: dict[str, str] = {}
    earlier: dict[str, str] = {}
    for path in sorted(current):
        was, now = origin[path], current[path]
        if was == ABSENT and now == ABSENT:
            continue  # arrived and left inside the range: the corpus is as it was
        if was == ABSENT:
            added.append(path)
        elif now == ABSENT:
            gone.append(path)
        elif was != now or PRESENT in (was, now):
            altered.append(path)
        else:
            continue  # the same bytes at both ends: this range did nothing to it

        if now not in (ABSENT, PRESENT):
            hashes[path] = now
        if was not in (ABSENT, PRESENT):
            earlier[path] = was

    # Derived from the last entry rather than carried: an entry says how many
    # artefacts it left untouched, so the corpus it left had
    # ``unchanged + added + changed`` artefacts in it. Anything in that total
    # this fold did not name is a file no run in the range touched.
    total = entries[-1].change.total if entries else 0
    return Change(
        added=tuple(added),
        changed=tuple(altered),
        removed=tuple(gone),
        unchanged=max(total - len(added) - len(altered), 0),
        hashes=hashes,
        previous=earlier,
        exact=exact,
    )


@dataclass(frozen=True, slots=True)
class Attribution:
    """Which runs put one artefact where it is, if the history can say."""

    path: str
    #: The run that added it, or ``None`` where the history does not reach back
    #: far enough to have seen it arrive. Followed through moves: a document
    #: renamed on Tuesday entered the corpus on the day it was first added,
    #: under whatever name it had then.
    first_seen: Entry | None
    #: The run that last added, changed or moved it. ``None`` for the same reason.
    last_touched: Entry | None
    #: How many runs in the history changed or moved it after it arrived.
    revisions: int
    #: The names it held before this one, most recent first. Empty when it has
    #: only ever had the one -- and an *inference*, because a move is bytes
    #: matching and not a `mv` observed ([ADR-0035]).
    formerly: tuple[str, ...] = ()

    @property
    def is_answered(self) -> bool:
        """Whether the history has anything to say about this artefact at all.

        False is a real answer and the report prints it as one. An artefact
        that predates the journal, or one whose corpus was copied in from
        somewhere else, has no history here -- and *unknown* is what a
        provenance tool owes a reader in that case. Attributing it to the
        oldest run it happens to sit beside would be a confident wrong answer
        in the exact place this library exists to prevent one.
        """
        return self.first_seen is not None or self.last_touched is not None


def touching(entries: Sequence[Entry], path: str, *, follow: bool = True) -> tuple[Entry, ...]:
    """The runs that added, changed, removed or moved one artefact, oldest first.

    `git log --follow -- <path>`, and the query the audit question is actually
    made of: a document is being questioned, and what is wanted is not the
    corpus's whole history but this document's part of it.

    **Followed through moves by default**, newest to oldest: when a run's
    moves say this name arrived from another, the search continues under that
    name. A document renamed last month still has the history it had before,
    and a reader who typed the name they can see should not need to know the
    names it used to have. ``follow=False`` asks about the name alone.
    """
    names = {path}
    chosen = []
    name = path
    for entry in reversed(entries):
        change = entry.change
        if follow:
            for old, new in change.moves:
                if new == name:
                    name = old
                    names.add(old)
                    break
        if change.touches & names:
            chosen.append(entry)
    chosen.reverse()
    return tuple(chosen)


def attribution(entries: Sequence[Entry], paths: Iterable[str]) -> tuple[Attribution, ...]:
    """For each artefact, the run that put it there and the run that last moved it.

    `git blame`, at the granularity musubi keeps -- a document rather than a
    line, because a document is the unit [ADR-0006] gives an identity to and a
    line is not something the journal records.

    Every path asked about comes back, including one the history has never
    heard of. Dropping those would make the answer look complete when it is
    the corpus that is complete and the history that is short.

    One walk of the history for every path at once, rather than one per path:
    the state of every artefact is carried forward entry by entry, and a move
    carries a state from the old name to the new one -- which is how a
    renamed document keeps the run that first added it.
    """
    #: path -> (first_seen, last_touched, revisions, former names). A first
    #: of ``None`` is an artefact the history saw change or move without ever
    #: having seen it arrive: it was there before the journal was.
    state: dict[str, tuple[Entry | None, Entry, int, tuple[str, ...]]] = {}
    for entry in entries:
        change = entry.change
        moved_to = dict(change.moves)
        arrived_by_move = frozenset(moved_to.values())
        for path in change.removed:
            carried = state.pop(path, None)
            if path in moved_to:
                first, revisions, formerly = (
                    (carried[0], carried[2], carried[3]) if carried is not None else (None, 0, ())
                )
                state[moved_to[path]] = (first, entry, revisions + 1, (path, *formerly))
        for path in change.added:
            if path not in arrived_by_move:
                # Added again after a removal: the artefact in the corpus now
                # is the one this run put there, so the clock restarts. The
                # earlier life is still in `musubi log --path`.
                state[path] = (entry, entry, 0, ())
        for path in change.changed:
            carried = state.get(path)
            if carried is None:
                state[path] = (None, entry, 1, ())
            else:
                first, _, revisions, formerly = carried
                state[path] = (first, entry, revisions + 1, formerly)

    found = []
    for path in sorted(paths):
        carried = state.get(path)
        if carried is None:
            found.append(Attribution(path=path, first_seen=None, last_touched=None, revisions=0))
            continue
        first, last, revisions, formerly = carried
        found.append(
            Attribution(
                path=path,
                first_seen=first,
                last_touched=last,
                revisions=revisions,
                formerly=formerly,
            )
        )
    return tuple(found)


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
    being read. And nothing names nothing: an empty prefix matches every run
    and would otherwise resolve to the only one in a short history.
    """
    wanted = prefix.strip()
    if not wanted:
        raise LookupError("no run id was given")
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


def _hashes(value: object) -> dict[str, str]:
    """The recorded hashes, or empty for a line written before [ADR-0035].

    Empty rather than a refusal. A journal that spans the change has lines of
    both kinds, and a reader that rejected the older ones would turn a history
    with less detail in its early part into no history at all.
    """
    if not isinstance(value, Mapping):
        return {}
    return {
        path: digest
        for path, digest in value.items()
        if isinstance(path, str) and isinstance(digest, str) and digest
    }


def _by_hash(pairs: Iterable[tuple[str, str]]) -> dict[str, list[str]]:
    """Hash to every path holding it. A list because two files can be equal."""
    grouped: dict[str, list[str]] = {}
    for path, digest in pairs:
        grouped.setdefault(digest, []).append(path)
    return grouped


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _names(value: object) -> tuple[str, ...]:
    if not isinstance(value, Iterable) or isinstance(value, str | bytes):
        return ()
    return tuple(name for name in value if isinstance(name, str))
