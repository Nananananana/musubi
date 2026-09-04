"""Reading N units out of an archive opens O(1) archives, not O(N).

`Source` is two stages on purpose: `discover()` opens nothing and `read()` opens
one thing. For a folder that is exactly right. For an **archive** it is the shape
of a quadratic, because there is no way to open one entry without the container,
so the container gets opened once per entry — measured at 400 pages,
`tools/scaling.py --only archive`, doubling the pages more than tripled the time.

**Counted rather than timed.** A timing assertion on this would be flaky on a
loaded machine and would still pass on a quadratic run that happened to be
small. What decides the order of growth is how many times an archive is
*opened*, and that is an integer.

It took two attempts to get right, and both intermediate states passed every
functional test in the suite:

```text
inflate the part once, cache the bytes    still quadratic -- `ZipFile(BytesIO)`
                                          per read re-reads a central directory
cache the opened archive                  linear
```

That is the whole reason this file counts a thing instead of asserting a
behaviour: the behaviour was correct at every step.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import pytest

from musubi.infrastructure.sources.notion import NotionSource

PAGE = "# note {i}\n\n" + ("Some ordinary prose in a paragraph a person wrote.\n\n" * 8)


def export(root: Path, pages: int, parts: int = 1) -> Path:
    """A Notion-shaped export: an outer archive of `Part-N.zip` of pages."""
    outer = root / "8a1_ExportBlock-9f2.zip"
    with zipfile.ZipFile(outer, "w") as archive:
        for part in range(parts):
            inner = io.BytesIO()
            with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as held:
                for i in range(part, pages, parts):
                    held.writestr(f"Note {i} {i:032x}.md", PAGE.format(i=i))
            archive.writestr(f"ExportBlock-9f2-Part-{part + 1}.zip", inner.getvalue())
    return outer


class Counter:
    """How many archives were opened, and how many entries were inflated."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.opened = 0
        self.inflated = 0
        opening = zipfile.ZipFile.__init__
        reading = zipfile.ZipFile.open

        def counted_init(inner: Any, *args: Any, **kwargs: Any) -> Any:
            self.opened += 1
            return opening(inner, *args, **kwargs)

        def counted_open(inner: Any, *args: Any, **kwargs: Any) -> Any:
            self.inflated += 1
            return reading(inner, *args, **kwargs)

        monkeypatch.setattr(zipfile.ZipFile, "__init__", counted_init)
        monkeypatch.setattr(zipfile.ZipFile, "open", counted_open)


def read_everything(root: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[int, int, int]:
    """Discover, then read every unit, counting archive opens along the way."""
    source = NotionSource(root)
    found = source.discover().found
    counter = Counter(monkeypatch)
    for item in found:
        source.read(item)
    return len(found), counter.opened, counter.inflated


@pytest.mark.parametrize("pages", [20, 40, 80])
def test_reading_every_unit_opens_a_constant_number_of_archives(
    pages: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The count must not grow with the number of pages.

    Two archives get opened at most: the outer, on its path, to reach a part
    that is not cached; and the part itself, once. A run that opens one per page
    is the quadratic this file exists to stop coming back.
    """
    export(tmp_path, pages)
    units, opened, _ = read_everything(tmp_path, monkeypatch)

    assert units == pages, "the fixture did not produce the pages it claims"
    assert opened <= 2, (
        f"reading {pages} units opened {opened} archives. An archive opened per unit is "
        f"a quadratic: `ZipFile(...)` reads a central directory, so the cost is the "
        f"entry count, and the run pays it once per entry."
    )


def test_the_inflations_are_one_per_unit_and_not_one_per_unit_plus_a_part(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Entries opened, rather than archives.

    One per unit is unavoidable and correct -- that *is* the work. What must not
    happen is a part being inflated again for each unit inside it, which is the
    other half of the same quadratic.
    """
    export(tmp_path, pages=40)
    units, _, inflated = read_everything(tmp_path, monkeypatch)

    assert inflated <= units + 2, (
        f"{units} units cost {inflated} entry reads. Anything much above one per unit "
        f"means a nested part is being inflated again per unit inside it."
    )


def test_several_parts_are_all_held_and_the_reads_still_do_not_grow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The case a cache of one would fail.

    The pipeline sorts units by key and a Notion key is a page id, so reads
    arrive in an order unrelated to which part a page is in. A single-slot cache
    thrashes on exactly this shape, which is why the bound is a byte budget.
    """
    export(tmp_path, pages=60, parts=4)
    units, opened, inflated = read_everything(tmp_path, monkeypatch)

    assert units == 60
    # One outer plus one per part. Linear in the **parts**, which is a handful,
    # and flat in the pages, which is the number that grows. The first version
    # of this assertion said `<= 2` and was measuring a one-part fixture.
    assert opened <= 4 + 1
    assert inflated <= units + 8, f"{units} units cost {inflated} entry reads across 4 parts"


def test_the_archives_opened_do_not_grow_with_the_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The invariant, stated as the comparison it actually is.

    A bound like `<= 5` is a bound on this fixture. What matters is that the
    count is **the same** for twice as many pages in the same number of parts,
    because that is the difference between linear and quadratic and it holds
    whatever the constant turns out to be.
    """
    small = tmp_path / "small"
    large = tmp_path / "large"
    small.mkdir()
    large.mkdir()
    export(small, pages=30, parts=3)
    export(large, pages=120, parts=3)

    fewer, opened_fewer, _ = read_everything(small, monkeypatch)
    more, opened_more, _ = read_everything(large, monkeypatch)

    assert (fewer, more) == (30, 120)
    assert opened_fewer == opened_more, (
        f"{fewer} pages opened {opened_fewer} archives and {more} pages opened "
        f"{opened_more}. The count is meant to depend on the parts, not the pages."
    )


def test_a_budget_too_small_to_hold_a_part_still_reads_correctly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The degradation is slow, not wrong.

    An export whose parts exceed the budget goes back to inflating per read. The
    bound is on memory, and the honest claim for that case is *correct and slow*
    rather than *fast*, so this asserts correctness and deliberately does not
    assert a count.
    """
    export(tmp_path, pages=10)
    source = NotionSource(tmp_path, nested_budget=1)
    found = source.discover().found

    assert len(found) == 10
    for item in found:
        assert source.read(item).startswith(b"# note ")
