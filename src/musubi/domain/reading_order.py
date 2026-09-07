"""The order the words go in, which is not the order the file holds them in.

A PDF producer writes text in whatever order suited its layout engine. A
typesetter laying out two columns emits the left cell of a line and then the
right cell of the *same* line, because that is the order the baselines happen
in. A reader that takes the strings as it meets them interleaves the columns and
produces prose that is **not in the document** ([#97]).

The failure is the comfortable kind. Every word of the page is present, every
offset still resolves to the page it came from, `traceable_coverage` is
unchanged and so is `answer_width`. Nothing anywhere says the sentences are not
the document's. That is the shape this repository keeps finding, and this module
is the geometry that answers it.

## Why this is in the domain

It is arithmetic over coordinates and it depends on nothing. A PDF is one source
of positioned runs; a page of OCR boxes would be another. What belongs here is
*given runs and where they sit, what order do they go in* -- a question that can
be tested without a PDF anywhere in sight, and `tests/test_reading_order.py`
tests it that way before any converter is involved.

## Why there is more than one answer, and why musubi does not guess

Two columns of prose must be read **down** each column. A table must be read
**across** each row. Those are opposite orders, and the two cases can be
geometrically identical: `tests/pdf_fixtures.py` holds a two-column page and a
table that are both two clusters of x on shared baselines. What separates them
is what the words mean, and that is not in the file.

So musubi does not decide. The strategy is a setting (`pdf-reading-order`), the
default is the file's own order -- exactly what every existing corpus already
has -- and the owner of a shelf of two-column papers says `columns` once. This
is [ADR-0028]'s bargain again: offered, never claimed. A guess that silently
reorders somebody's corpus is worse than the disorder it was fixing, because the
disorder at least came from the file.

## A line, not a run

A strategy returns **lines**: runs that share a baseline are parts of one line
of text, whatever order the stream showed them in. That is why the return type
is a list of lists and not a sorted list. Getting `Item` and `Mass` into the
right order is only half of a table; the other half is knowing they are one row.

[#97]: https://github.com/Nananananana/musubi/issues/97
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

#: How far apart two runs' left edges must be, in page points, before they are
#: read as being in different columns. A threshold, registered in
#: `tests/test_thresholds.py` with the sweep behind it.
#:
#: 24 points is two 12pt line heights. Much below a line height and the
#: indented first line of a paragraph becomes its own column; far above one and
#: a narrow gutter stops being a gutter.
COLUMN_GAP = 24.0

#: How far apart two baselines may be, in page points, and still be one line.
#: A superscript or a mid-line font change moves a baseline by a point or two;
#: the next line of 12pt text is 14 to 16 away, so this separates them with
#: room on both sides.
BASELINE_TOLERANCE = 4.0


@dataclass(frozen=True, slots=True)
class Run:
    """A stretch of text and where it sits on the page.

    `y` is the baseline in the source's own coordinates. PDF puts the origin at
    the bottom left and counts upwards, so **larger `y` is higher up the page**
    and reading order runs from large `y` to small. A source that counts the
    other way converts before it gets here: this module has one convention and
    says which.
    """

    text: str
    x: float
    y: float


#: A strategy takes positioned runs and returns lines, in reading order.
Strategy = Callable[[Sequence[Run]], list[list["Run"]]]


def _floors(values: Iterable[float], apart: float) -> list[float]:
    """Where the gaps are: one floor per cluster, over sorted values.

    One pass rather than any general clustering. The question is only *where
    are the gaps wider than `apart`*, and a k-means over one dimension would
    invent a k nothing here has evidence for.
    """
    ordered = sorted(set(values))
    if not ordered:
        return []
    found = [ordered[0]]
    for value in ordered[1:]:
        if value - found[-1] > apart:
            found.append(value)
    return found


def _floor_of(value: float, floors: Sequence[float]) -> float:
    """The largest floor at or below `value`."""
    found = floors[0]
    for floor in floors:
        if floor <= value:
            found = floor
    return found


def _lined(runs: Sequence[Run], key: Callable[[Run], object]) -> list[list[Run]]:
    """Runs already in order, grouped into lines by `key`."""
    lines: list[list[Run]] = []
    last: object = object()
    for run in runs:
        here = key(run)
        if here != last:
            lines.append([])
            last = here
        lines[-1].append(run)
    return lines


def columns(runs: Sequence[Run], *, gap: float = COLUMN_GAP) -> list[list[Run]]:
    """Down each column, columns left to right.

    What a two-column paper needs. A page whose runs all start at the same left
    edge is one column, and one column read down is the same answer `rows`
    gives -- so this is safe on ordinary prose and only differs where there
    really are columns.

    **Left to right, and not otherwise.** Columns that run right to left, as
    vertical Japanese does, are a different reading order, and nothing in a
    run's geometry distinguishes the two: three runs side by side are three runs
    side by side whichever way the script goes. [ADR-0042] records that instead
    of this function guessing at a script it cannot see.
    """
    if not runs:
        return []
    sides = _floors((run.x for run in runs), gap)
    baselines = _floors((run.y for run in runs), BASELINE_TOLERANCE)
    placed = sorted(
        runs,
        key=lambda run: (_floor_of(run.x, sides), -_floor_of(run.y, baselines), run.x),
    )
    return _lined(placed, lambda run: (_floor_of(run.x, sides), _floor_of(run.y, baselines)))


def rows(runs: Sequence[Run], *, tolerance: float = BASELINE_TOLERANCE) -> list[list[Run]]:
    """Across each line, lines down the page.

    What a table needs, and what a producer emitting a table column by column
    defeats. Baselines are clustered rather than compared exactly, because a
    superscript or a mid-line font change moves one by a point.
    """
    if not runs:
        return []
    baselines = _floors((run.y for run in runs), tolerance)
    placed = sorted(runs, key=lambda run: (-_floor_of(run.y, baselines), run.x))
    return _lined(placed, lambda run: _floor_of(run.y, baselines))


#: Every geometric strategy, by name. The registry is the population: a
#: strategy added without a name here is one nobody can ask for, and
#: `musubi config` prints these.
#:
#: The file's own order is **not** in here, and that is deliberate. "Use the
#: order the file gave" is the absence of a geometric decision rather than one
#: of them, and the converter answers it without coordinates at all -- which is
#: what keeps the default path byte-for-byte what it has always been.
STRATEGIES: dict[str, Strategy] = {
    "columns": columns,
    "rows": rows,
}


def strategy_named(name: str) -> Strategy:
    """The strategy called `name`.

    A `KeyError` rather than a quiet fall back to the file's order: a misspelled
    setting that reads in stream order anyway is a corpus built the way its
    owner explicitly asked it not to be, with nothing saying so.
    """
    try:
        return STRATEGIES[name]
    except KeyError:
        raise KeyError(
            f"no reading order called {name!r}; known: {', '.join(sorted(STRATEGIES))}"
        ) from None


def text_of(lines: Sequence[Sequence[Run]]) -> str:
    """Lines of runs as text: runs joined by a space, lines by a newline.

    A space and not nothing. Two runs on one baseline are two stretches the
    producer placed separately, and in every layout that matters -- a table
    cell beside another, a label beside a value -- what separates them on the
    page is space.
    """
    return "\n".join(" ".join(run.text for run in line) for line in lines)
