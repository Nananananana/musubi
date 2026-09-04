"""Reading a file that is not UTF-8, without pretending to be sure.

## The rule this relaxes, and what it keeps

`domain.text.decode` reads UTF-8 and UTF-16-with-a-mark and refuses everything
else, on a good argument:

> A guessed legacy encoding writes mojibake into a corpus that will be sent to a
> model, and it looks exactly like successful ingestion -- no error, no warning,
> a file full of plausible nonsense.

The argument is about a guess that is **invisible**. It was implemented as a
refusal, and the refusal turned out to be the wrong shape for the person musubi
is for: a vault with any note written before about 2015, on a Japanese Windows
machine, is Shift-JIS, and musubi reports every one of those files as
`undecodable`. That is a correct answer and a library nobody can use.

So the guess becomes **visible** instead of forbidden:

```text
encoding = "strict"   the default. Refuses, and the refusal now says what the
                      file looks like and what to set
encoding = "detect"   decodes it, and **records what was detected and how
                      confident** in the trace map and the manifest
```

Nothing is silent in either mode. The domain is unchanged and still refuses;
what changed is that infrastructure can offer an answer with its uncertainty
attached, which is what the original objection actually asked for.

## What it gets right, measured

`tools/encoding_detection.py`, six languages against seven encodings, comparing
the **recovered text** rather than the label -- `euc-jp` read as `euc_jis_2004`
is a pass, because it is a superset that decodes the same bytes the same way.

```text
a paragraph of prose   **17 of 19** recovered exactly
one line of prose      **16 of 19**
```

Both constant failures are the same case: **French in Latin-1 or cp1252, read
as cp1250.** Every multi-byte encoding was right at paragraph length --
Shift-JIS, EUC-JP, ISO-2022-JP, GB18030, KOI8-R.

**The short-sample row is the one worth reading twice.** Detection degrades as
the file gets smaller, and the extra failure there is Russian in KOI8-R read as
`shift_jis_2004` -- not a near miss, a different alphabet. A folder of one-line
notes is exactly the input that produces it.

That asymmetry is the reason `strict` is the default. A Japanese vault is the
case detection handles well and the case a refusal makes unusable; short
single-byte Western text is the case where a wrong guess is plausible, quiet,
and confident -- every one of these misses reported **100% coherence**.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import replace as _replace

from ..domain.text import Decoded, decode
from ..ports.converter import Converted, Converter, Unconvertible

__all__ = ["DECODES", "EXTRA", "Decoding", "Detection", "detector", "read"]

#: The media types whose source **is** text, and which a decoding therefore
#: applies to.
#:
#: A PDF is bytes all the way down: transcoding one would corrupt it, and
#: detecting an encoding for it would be detecting the encoding of a container.
#: So the wrapper is applied by media type rather than by asking a converter
#: what it does, and `tests/test_decoding.py` asserts every registered converter
#: falls on one side or the other rather than being quietly missed.
DECODES = frozenset({"text/markdown", "text/plain", "text/html", "text/csv"}) | frozenset(
    {"application/xhtml+xml"}
)

#: What to install to have this at all.
EXTRA = "musubi[encoding]"

#: Below this, a detection is reported but not acted on even in `detect` mode.
#:
#: `charset-normalizer` scores a candidate by how coherent the decoded text
#: looks, and a low score means it found nothing it recognised -- which for this
#: purpose is the same as not knowing. Refusing there keeps the failure the one
#: the original rule was written about: a file that cannot be read is reported
#: as unreadable rather than turned into plausible nonsense.
CONFIDENT = 0.3


@dataclass(frozen=True, slots=True)
class Detection:
    """What a file looks like, and how much of a guess that is."""

    encoding: str
    #: 0 to 1. Higher is more coherent, not more certain -- there is no
    #: probability here and calling it one would be the invisible guess again.
    confidence: float
    text: str

    @property
    def worth_acting_on(self) -> bool:
        return self.confidence >= CONFIDENT

    def describe(self) -> str:
        return f"looks like {self.encoding} ({self.confidence:.0%} coherent)"


def detector() -> Callable[[bytes], Detection | None] | None:
    """The detection function, or ``None`` when the extra is not installed.

    Imported inside the function, like every other optional dependency
    ([ADR-0028]): a missing extra is a feature that is not offered, never an
    `ImportError` from `import musubi`.
    """
    try:
        import charset_normalizer
    except ImportError:
        return None

    def detect(content: bytes) -> Detection | None:
        best = charset_normalizer.from_bytes(content).best()
        if best is None:
            return None
        # Decoded here rather than taken from `str(best)`. The library's own
        # rendering is not always the decoding its label implies: for
        # ISO-2022-JP it hands back the escape sequences, so `str(best)` was the
        # raw `$B@_7W...` while `best.encoding` said `iso2022_jp` and was right.
        #
        # `tools/encoding_detection.py` never saw it, because the tool decodes
        # with the reported encoding -- which is to say **the measurement and
        # the code did two different things**, and the measurement was the
        # correct one. Doing what the tool does is what makes its numbers true
        # of this function.
        encoding = str(best.encoding)
        try:
            text = content.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            return None

        # `chaos` is the share of the decoding that looked incoherent, so the
        # complement is the readable one. Reported rather than thresholded away,
        # because a caller deciding what to do with a 40% reading should be able
        # to see that it was 40%.
        return Detection(
            encoding=encoding,
            confidence=max(0.0, 1.0 - float(best.chaos)),
            text=text,
        )

    return detect


def read(content: bytes, *, detect: bool) -> tuple[Decoded, Detection | None]:
    """Decode as [ADR-0018] requires, falling back to detection if allowed.

    Returns the decoding **and** what was detected, so that a caller can record
    the guess beside the text rather than only the text. A `Detection` in the
    result is the difference between this and the thing the original rule
    forbade.

    Raises `ValueError` when nothing can read the bytes, with a message that
    names the detection when there was one -- so a refusal in `strict` mode
    tells the owner what their file is and which setting reads it, instead of
    only that it is not UTF-8.
    """
    try:
        return decode(content), None
    except ValueError as refusal:
        found = detector()
        detected = found(content) if found is not None else None

        if detected is None:
            raise
        if not detect:
            raise ValueError(
                f'{refusal}. It {detected.describe()}; set `encoding = "detect"` in '
                f"musubi.toml to read it, and the detected encoding will be recorded "
                f"with every offset"
            ) from refusal
        if not detected.worth_acting_on:
            raise ValueError(
                f"{refusal}. The best reading of it {detected.describe()}, which is not "
                f"coherent enough to act on; musubi would be writing plausible nonsense"
            ) from refusal

        return (
            Decoded(
                text=detected.text,
                encoding=detected.encoding,
                bom_length=0,
                codec=detected.encoding,
            ),
            detected,
        )


class Decoding:
    """A converter that can also read a file which is not UTF-8.

    Wraps rather than changes: `Converter` is `bytes -> text and a map`, and
    every converter that decodes does it the same way, so the policy belongs in
    one place outside all of them.

    **Why transcoding is safe here, which is the only subtle part.** When
    detection is used, the bytes handed to the inner converter are the *same
    text* re-encoded as UTF-8. Character offsets are counted over the text, so
    they are identical either way -- and `source_encoding` records the
    **original**, so `text[:n].encode(source_encoding)` still gives a byte
    offset in the file the owner has ([ADR-0018]). Nothing about the map's
    meaning changes; only what musubi had to do to read the bytes.
    """

    def __init__(self, inner: Converter, *, detect: bool) -> None:
        self._inner = inner
        self._detect = detect
        self.name = inner.name
        self.media_types = inner.media_types

    def convert(self, content: bytes, media_type: str) -> Converted | Unconvertible:
        if media_type not in DECODES:
            return self._inner.convert(content, media_type)

        try:
            decoded, detection = read(content, detect=self._detect)
        except ValueError as refusal:
            return Unconvertible("undecodable", str(refusal), self.name)

        if detection is None:
            # The ordinary path, and deliberately the *same* bytes rather than
            # a re-encoding of them: a UTF-8 file with a byte-order mark has a
            # `bom_bytes` the inner converter knows how to record, and
            # transcoding would quietly drop it.
            return self._inner.convert(content, media_type)

        converted = self._inner.convert(decoded.text.encode("utf-8"), media_type)
        if not isinstance(converted, Converted):
            return converted
        return _replace(
            converted,
            source_encoding=detection.encoding,
            source_bom_bytes=0,
        )
