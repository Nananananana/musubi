"""Does detection recover the text, or only a plausible-looking label?

[ADR-0031] relaxes a refusal into a recorded guess, and the whole question is
how often the guess is right. The number that matters is **not** whether the
detector names the encoding a file was written in. It is whether the text comes
back **identical**, because two encodings can share a label and disagree about
one character, and one can carry a different name and decode the same bytes the
same way.

So this compares strings, not labels. `euc-jp` detected as `euc_jis_2004` is a
pass: it is a superset, and the text is the text.

    uv run python tools/encoding_detection.py

The corpus is generated, and here that limitation is smaller than usual: the
detector reads bytes, and prose in a language is prose in a language. What it
cannot show is behaviour on the mixed, truncated, half-binary files a real
folder has, where the honest expectation is worse than this.
"""

from __future__ import annotations

import sys

from musubi.infrastructure.decoding import detector

#: One paragraph per language, long enough that a detector has something to
#: work with. A short sample is the case detection is worst at, and
#: `--short` runs the same table at one line to show how much worse.
SAMPLES: dict[str, str] = {
    "japanese": "設計メモ。テントは 2.4kg。ブーツのほうが効く。山では軽さがすべて。\n",
    "chinese": "设计备忘录。帐篷重两点四公斤。靴子比背包更重要。\n",
    "korean": "설계 메모. 텐트는 2.4킬로그램. 신발이 배낭보다 중요하다.\n",
    "french": "Café résumé naïve. La tente pèse deux kilos quatre cents grammes.\n",
    "german": "Größe Straße Fußgänger über. Das Zelt wiegt zwei Komma vier Kilo.\n",
    "russian": "Привет мир, это заметка о снаряжении. Палатка весит два килограмма.\n",
}

ENCODINGS = ("cp932", "euc-jp", "iso-2022-jp", "latin-1", "cp1252", "koi8-r", "gb18030")


def main() -> int:
    detect = detector()
    if detect is None:
        print("charset-normalizer is not installed: pip install 'musubi[encoding]'")
        return 2

    short = "--short" in sys.argv
    print(f"{'sample':10s} {'written as':12s} {'detected as':16s} {'coherent':>9s} {'text':>6s}")
    print("-" * 58)

    recovered = attempted = 0
    misses: list[str] = []
    for label, paragraph in SAMPLES.items():
        text = paragraph if short else paragraph * 6
        for encoding in ENCODINGS:
            try:
                raw = text.encode(encoding)
            except UnicodeEncodeError:
                continue  # the language does not fit that encoding; not a case
            attempted += 1

            found = detect(raw)
            if found is None:
                print(f"{label:10s} {encoding:12s} {'(nothing)':16s} {'':>9s} {'no':>6s}")
                misses.append(f"{label}/{encoding}: nothing detected")
                continue

            try:
                same = raw.decode(found.encoding) == text
            except (LookupError, UnicodeDecodeError):
                same = False
            recovered += same
            if not same:
                misses.append(f"{label}/{encoding}: read as {found.encoding}")
            print(
                f"{label:10s} {encoding:12s} {found.encoding:16s} "
                f"{found.confidence:>8.0%} {('yes' if same else 'NO'):>6s}"
            )

    print()
    print(
        f"**text recovered exactly: {recovered}/{attempted}**"
        f"{' (one line per sample)' if short else ''}"
    )
    if misses:
        print("\nwhere it was wrong:")
        for miss in misses:
            print(f"  {miss}")
    print()
    print("The label is not the measurement. `euc-jp` read as `euc_jis_2004` is a pass:")
    print("a superset that decodes the same bytes the same way. What is compared is text.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
