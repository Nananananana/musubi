"""Every converter against every floor, printed whether it passes or not.

`tests/test_converter_floors.py` is the gate. This is the report, and it exists
because a gate that only speaks when it fails hides the other half: a number
that went **up** is a change worth seeing, and a floor with less headroom than
somebody thinks is a floor about to become a target.

Both read `tests/converter_floors.py`, so the gate and the report cannot
disagree about what a number is.

    uv run python tools/floors.py

Exits non-zero if a floor is breached, so it can be a CI step in its own right
and print the table on the way past.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from converter_floors import BOUNDS, FLOORS, HTML, PDF, claiming, measured
from musubi.infrastructure.converters.external import unavailable


def main() -> int:
    now = measured()
    print("== converter floors: what each reader must not get worse than ==\n")
    print(f"  {'converter':16s} {'measure':26s} {'now':>7s} {'floor':>7s} {'room':>7s}")

    breached = []
    for floor in sorted(FLOORS, key=lambda f: (f.converter, f.measure)):
        reading = now.get((floor.converter, floor.measure))
        if reading is None:
            print(f"  {floor.converter:16s} {floor.measure:26s} {'--':>7s}  not measured here")
            continue
        room = reading - floor.floor
        mark = "  " if room >= 0 else "<<"
        print(
            f"  {floor.converter:16s} {floor.measure:26s} "
            f"{reading:7.3f} {floor.floor:7.3f} {room:+7.3f} {mark}"
        )
        if room < 0:
            breached.append((floor, reading))

    print("\n  bounds, which have no headroom on purpose")
    readers = [*claiming(HTML), *claiming(PDF)]
    for converter in sorted({str(getattr(c, "name", "")) for c in readers}):
        for measure in sorted(BOUNDS):
            reading = now.get((converter, measure))
            if reading is not None:
                held = "held" if reading == 1.0 else "BROKEN"
                print(f"  {converter:16s} {measure:26s} {held}")

    missing = [extractor.name for extractor in unavailable()]
    if missing:
        print(f"\n  not installed, so not measured: {', '.join(sorted(missing))}")
        print("  That is a smaller measurement rather than none; `uv sync --all-extras`.")

    if breached:
        print("\n  A floor is breached. Either this is a regression, or the floor is")
        print("  wrong -- and moving one is a commit with a reason in it.")
        for floor, reading in breached:
            print(f"\n  {floor.converter} {floor.measure}: {reading:.3f} < {floor.floor:.3f}")
            print(f"    set {floor.when} at {floor.measured:.3f}. {floor.why}")
        return 1

    print("\n  Floors, not targets. Every one sits below what it measured, so an")
    print("  honest experiment has room to cost a little without failing a build.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
