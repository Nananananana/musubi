"""musubi in three lines, for one file.

## Why this exists

```python
from markitdown import MarkItDown
print(MarkItDown().convert("report.pdf").text_content)
```

That is the first thing anybody tries, and until this module musubi could not
do it. `musubi.__all__` was six exception classes and a version string; using
the library meant importing from `application`, `infrastructure` and `ports`,
building a `Settings`, a source and an emitter, and knowing that
`run(write=True)` stages while `sync()` promotes.

Worse than the friction: **the map was the hardest thing to reach.** musubi's
whole claim is that a conversion carries one, and the only way to hold it was to
run a sync into a folder and read a sidecar back off disk — so the thing that
makes musubi different from every `bytes -> str` converter was the thing nobody
could get at.

```python
import musubi

converted = musubi.convert("report.pdf")
converted.text                      # what a model would read
converted.coverage                  # 0.997
converted.where(57, 62)             # Where(...): page 3, or characters [13:18]
```

## What this is not

**Not a second pipeline.** Everything here calls the same converters, the same
cleansing rules and the same screener that `musubi sync` calls, chosen by the
same configuration. A difference between `musubi.convert(p)` and
`musubi sync`'s treatment of the same file would be two implementations of one
promise, so there is one and this is a doorway to it.

**Not a corpus.** One file has no `(source_id, unit_key)` identity — [ADR-0006]
makes identity a property of a *source*, and a path handed to a function is not
one. So this returns a value and writes nothing; `sync()` is next door for when
a folder and a manifest are what is wanted.

**Not exempt from the screener.** [ADR-0008] stops a *run* on a credential, and
the equivalent here is refusing to return the text: `CredentialFoundError`,
naming the rule and never the value. A convenience function that quietly handed
back a file with an AWS key in it would be the one place in musubi where the
policy did not apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .application.pipeline import Settings
from .config import Configuration, destination, load, settings_from, source_from
from .domain.cleansing import cleanse
from .domain.hashing import content_hash
from .domain.journal import Entry
from .domain.removal import RemovalRecord
from .domain.span import Span
from .domain.trace import CHARACTERS, Kind, TraceMap
from .errors import ConversionError, CredentialFoundError
from .infrastructure.sources.filesystem import MEDIA_TYPES
from .ports.converter import Converted

__all__ = ["Converted", "Where", "convert", "history", "media_type_of", "settings"]


@dataclass(frozen=True, slots=True)
class Where:
    """Where a range of the converted text came from.

    `unit` is what the offsets count — `characters` for a format whose source is
    text, `opaque` for one whose source is not ([ADR-0025]). **A caller must
    read it before doing arithmetic**, because `[2:3]` is one character or one
    page and the numbers look identical.
    """

    span: Span
    unit: str
    kinds: tuple[Kind, ...]
    rules: tuple[str, ...]

    @property
    def is_exact(self) -> bool:
        """Every run in the range is verbatim, so the correspondence holds at
        every interior offset rather than only at the ends."""
        return bool(self.kinds) and all(kind is Kind.VERBATIM for kind in self.kinds)

    def __str__(self) -> str:
        """ASCII only, and that is not fussiness.

        [ADR-0020] makes the *command line* incapable of failing a run on a
        narrow console: `main()` reconfigures the streams with
        `errors="replace"`. **A library value has no such protection.** This
        used an en dash between page numbers, and `print(doc.where(0, 34))` on
        an un-reconfigured Japanese Windows console raised
        `UnicodeEncodeError` — a crash in the three-line example, from a
        typographic choice.

        The rule that follows: musubi may print what it likes through its own
        commands, and anything a caller might `print` themselves stays in ASCII.
        """
        if self.unit == CHARACTERS:
            return f"characters [{self.span.start}:{self.span.end}]"
        if self.span.length == 1:
            return f"page {self.span.start + 1} (opaque locator)"
        return f"pages {self.span.start + 1}-{self.span.end} (opaque locator)"


@dataclass(frozen=True, slots=True)
class Document:
    """One file, converted, with the map still attached."""

    #: What a model would read. Cleansed, and **without** front matter: nothing
    #: was emitted, so there is nothing for front matter to describe.
    text: str
    trace: TraceMap
    #: `markdown@1`, `trafilatura@1` — what the manifest would have recorded.
    converter: str
    media_type: str
    #: The encoding the source was read in, and the bytes its mark took. With
    #: these and the file, a character offset becomes a byte offset ([ADR-0018]).
    encoding: str
    bom_bytes: int
    content_hash: str
    removals: tuple[RemovalRecord, ...]
    path: Path | None = None

    @property
    def coverage(self) -> float:
        """The share of the text that resolves to a place in the source."""
        return self.trace.traceable_coverage

    def where(self, start: int, end: int) -> Where:
        """Where this range of `text` came from."""
        if not 0 <= start <= end <= len(self.text):
            raise ValueError(f"[{start}:{end}] is outside the text [0:{len(self.text)}]")
        out = Span(start, end)
        # `Span.overlaps` is false for an empty span, and it has to be -- an
        # insertion would otherwise collide with the run it sits in. But a
        # **removal occupies no output** (ADR-0005), so a filter built on
        # `overlaps` alone reports where a range came from and silently omits
        # what was taken out of it, which is the one thing ADR-0005 exists to
        # keep visible. The second clause is what catches those.
        touching = [
            segment
            for segment in self.trace.segments
            if segment.out.overlaps(out) or out.start <= segment.out.start <= out.end
        ]
        return Where(
            span=self.trace.source_span_of(out),
            unit=self.trace.source_unit,
            kinds=tuple(dict.fromkeys(segment.kind for segment in touching)),
            rules=tuple(dict.fromkeys(s.rule for s in touching if s.rule)),
        )

    def __str__(self) -> str:
        return self.text


def settings(start: Path | None = None) -> Settings:
    """The settings a run here would use: the same ones `musubi sync` uses.

    Read from `musubi.toml` and the environment exactly as the command line
    reads them ([ADR-0027]), so a folder configured for `sync` is configured
    for this too and `musubi config` explains both.
    """
    return settings_from(load(start), musubi_version=_version(), created_at="")


def media_type_of(path: Path | str) -> str | None:
    """What musubi thinks this file is, by suffix, or ``None``.

    The same table `FilesystemSource` walks a folder with, so a file this
    returns ``None`` for is a file a sync would skip as `unknown_format`.
    """
    return MEDIA_TYPES.get(Path(path).suffix.lower())


def convert(
    path: Path | str,
    *,
    content: bytes | None = None,
    media_type: str | None = None,
    configuration: Configuration | None = None,
) -> Document:
    """Convert one file and hand back the text **and** the map.

    ```python
    converted = musubi.convert("notes/gear.md")
    print(converted.text)
    print(converted.where(*range_of_interest))
    ```

    `content` lets a caller supply the bytes — for a file that is not on a disk,
    or one already in memory. `path` is then only used to decide the format and
    to say where the answer came from.

    Raises `CredentialFoundError` rather than returning text that holds a
    credential ([ADR-0008]), `SourceError` when the file cannot be read, and
    `ConversionError` when musubi has no converter for it or the converter
    refused. Each names what happened; none of them quotes a secret.
    """
    location = Path(path)
    body = location.read_bytes() if content is None else content
    kind = media_type or media_type_of(location)
    if kind is None:
        known = ", ".join(sorted(MEDIA_TYPES))
        raise ConversionError(
            f"{location.name} has no suffix musubi recognises; it reads {known}. "
            f"Pass media_type= to say what it is."
        )

    chosen = (
        settings(None)
        if configuration is None
        else settings_from(configuration, musubi_version=_version(), created_at="")
    )

    hits = list(chosen.screener.screen(body.decode("utf-8", errors="replace")))
    refused = [hit for hit in hits if f"{hit.rule}:{location.name}" not in chosen.allowed]
    if refused:
        raise CredentialFoundError(
            f"{refused[0].label} in {location.name} ({refused[0].rule}). Nothing is "
            f"returned: musubi refuses rather than redacting, because refusing needs "
            f"only that a secret exists (ADR-0008)."
        )

    converter = chosen.converter_for(kind)
    if converter is None:
        raise ConversionError(f"no converter claims {kind!r}")

    converted = converter.convert(body, kind)
    if not isinstance(converted, Converted):
        raise ConversionError(f"{location.name} was not converted: {converted.reason}")

    cleansed = cleanse(converted.text, chosen.ruleset)
    trace = converted.trace.followed_by(TraceMap.of_rewrite(cleansed.rewritten)).merged()
    return Document(
        text=cleansed.rewritten.text,
        trace=trace,
        converter=converted.converter,
        media_type=kind,
        encoding=converted.source_encoding,
        bom_bytes=converted.source_bom_bytes,
        content_hash=content_hash(body),
        removals=cleansed.removals,
        path=location if content is None else None,
    )


def sync(root: Path | str, into: Path | str | None = None) -> object:
    """Build a corpus, exactly as `musubi sync` does.

    Here so that the doorway is not only one file wide, and deliberately thin:
    it composes the same objects the command line composes, so that there is one
    implementation of a sync and this is a way in rather than a second one.
    """
    from .application.sync import sync as run_sync
    from .infrastructure.emitters import DocumentEmitter

    configuration = load(Path(root))
    where = Path(into) if into is not None else destination(configuration)
    source = source_from(configuration, Path(root))
    return run_sync(source, settings(Path(root)), DocumentEmitter(where))


def history(corpus: Path | str) -> tuple[Entry, ...]:
    """A corpus's history, oldest first, exactly as `musubi log` reads it.

    Returns the entries themselves rather than a rendering of them, because the
    thing a caller wants is usually a question the report does not answer --
    *which run first held this path*, *what was the corpus on the day of the
    incident* -- and a caller that has to parse a report back is a caller
    musubi has sent the long way round.

    Empty for a corpus that keeps no history ([ADR-0034]). That is not an
    error: a corpus written before the journal existed is otherwise sound.

    **History, not storage.** An entry says a document changed; nothing here
    can give back what it was.
    """
    from .infrastructure.corpus import Corpus

    return Corpus(Path(corpus)).journal()


def _version() -> str:
    from . import __version__

    return __version__
