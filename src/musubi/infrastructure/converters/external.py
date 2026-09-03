"""Converters built on somebody else's extractor, with the map recovered.

## Why these exist

musubi's own converters are written rather than borrowed because [ADR-0004]
needs a map and every library in the world returns a string. That decision was
right and it has a cost: **boilerplate removal is a research area with published
benchmarks, and a hand-written scan of tags does not win it.** A guarantee that
is true of text nobody wants is not worth much.

[ADR-0028] takes the dependency, outside the domain, optional, and pays for it
by recovering the map instead of being handed one: the extractor's text is
*aligned* against the source (`domain/alignment.py`), so what comes back is a
real tiling whose traceable coverage is a **measurement** rather than a claim.

## What an adapter must not do

**No network.** [ADR-0007] is the boundary that makes everything else
checkable, and it does not become negotiable because the code doing the
fetching belongs to somebody else. `tests/test_alignment.py` runs every
adapter with the socket module broken.

**No import at import time.** A missing extra is a converter that is not
registered, never an `ImportError` from `import musubi`. `unavailable()` says
which are missing and what to install, and `musubi config` prints it.

## What is here

| Adapter | Extra | Licence | What it is for |
|---|---|---|---|
| `trafilatura@1` | `musubi[html]` | Apache-2.0 | main-content extraction that wins its benchmarks |

Only permissively licensed extractors are adapted. `PyMuPDF` is the fastest PDF
reader in Python and is AGPL-3.0; a library whose users vendor it into their own
products cannot hand them that, and an extra is still a dependency the user
ends up shipping.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ...domain.alignment import align
from ...domain.text import decode
from ...ports.converter import Converted, Unconvertible

__all__ = ["AlignedConverter", "Extractor", "available", "unavailable"]


@dataclass(frozen=True, slots=True)
class Extractor:
    """Somebody else's `bytes -> str`, and what it takes to have it.

    `load` returns the extraction function or ``None`` when the dependency is
    absent. Called at registration and again whenever `musubi config` is asked,
    so installing an extra takes effect without anything being re-imported.
    """

    name: str
    media_types: tuple[str, ...]
    extra: str
    licence: str
    load: Callable[[], Callable[[str], str | None] | None]


class AlignedConverter:
    """Satisfies :class:`~musubi.ports.converter.Converter` by aligning.

    The source is decoded by musubi ([ADR-0018]: the map's offsets are
    characters of *this* decoding, and the encoding is recorded beside it), the
    extractor is handed the decoded text, and the result is aligned back against
    it. An extractor that returns nothing is a refusal with a reason, exactly as
    a scanned PDF is.
    """

    def __init__(self, extractor: Extractor) -> None:
        self._extractor = extractor
        self.name = extractor.name
        self.media_types = extractor.media_types

    def convert(self, content: bytes, media_type: str) -> Converted | Unconvertible:
        extract = self._extractor.load()
        if extract is None:  # pragma: no cover - unregistered when absent
            return Unconvertible(
                "extractor_missing",
                f"install {self._extractor.extra}",
                self.name,
            )
        try:
            decoded = decode(content)
        except ValueError as error:
            return Unconvertible("undecodable", str(error), self.name)

        text = extract(decoded.text)
        if not text or not text.strip():
            return Unconvertible(
                "no_main_content",
                f"{self._extractor.name} found nothing it would call content",
                self.name,
            )

        body = text if text.endswith("\n") else text + "\n"
        aligned = align(decoded.text, body)
        return Converted(
            text=body,
            trace=aligned.trace,
            converter=self.name,
            source_encoding=decoded.codec,
            source_bom_bytes=decoded.bom_length,
        )


def _trafilatura() -> Callable[[str], str | None] | None:
    try:
        import trafilatura
    except ImportError:
        return None

    def extract(html: str) -> str | None:
        # `favor_precision` because a corpus is read by a model: a paragraph of
        # navigation that got through is a paragraph the model will answer from.
        # `no_fallback=False` keeps the readability pass, which is where the
        # published benchmark numbers come from.
        #
        # No `url=`. Passing one lets the library reason about the site, and
        # musubi has no url to pass -- it read a file (ADR-0007).
        result: str | None = trafilatura.extract(
            html,
            favor_precision=True,
            include_comments=False,
            include_tables=True,
            output_format="txt",
        )
        return result

    return extract


EXTRACTORS: tuple[Extractor, ...] = (
    Extractor(
        name="trafilatura@1",
        media_types=("text/html", "application/xhtml+xml"),
        extra="musubi[html]",
        licence="Apache-2.0",
        load=_trafilatura,
    ),
)


def available() -> tuple[Extractor, ...]:
    """The adapters whose dependency is installed, in a stable order."""
    return tuple(sorted((e for e in EXTRACTORS if e.load() is not None), key=lambda e: e.name))


def unavailable() -> tuple[Extractor, ...]:
    """The adapters whose dependency is not, so a report can say what to do."""
    return tuple(sorted((e for e in EXTRACTORS if e.load() is None), key=lambda e: e.name))
