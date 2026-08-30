"""The two converters that are nearly the identity, and the map they still owe.

Plain text and Markdown come first on purpose. Neither has a hard conversion in
it -- Markdown *is* the output format, and a `.txt` is already text -- so the
correct answer is obvious at every offset, which makes them the right place to
get the tiling machinery right before it is used somewhere the answer is not
obvious ([ADR-0004]).

"Nearly" is doing real work in that sentence. Two things happen to a file on its
way to being text, and both are transformations that move offsets:

**Decoding.** A byte-order mark is three bytes on disk and no characters in the
string, so every source offset after it is three further along than the
character index suggests. Windows producers write one without being asked.

**Line endings.** CRLF and a lone CR become LF, because a corpus whose line
endings depend on which machine wrote it has offsets that depend on the same
thing, and musubi reads folders written on other people's machines.

The map's source side is measured in **characters of the decoded text**, and the
decoding travels beside it ([ADR-0018]). Turning that into a byte offset takes
the encoding, the length of the byte-order mark and the file -- and the command
that opens the file is the only thing that has all three.
"""

from __future__ import annotations

from ...domain.text import decode, normalize_line_endings
from ...domain.trace import TraceMap
from ...ports.converter import Converted, Unconvertible

__all__ = ["MarkdownConverter", "PlainTextConverter", "TextConverter"]


class TextConverter:
    """Decode, normalize line endings, and account for both.

    Satisfies :class:`~musubi.ports.converter.Converter`.
    """

    name = "text@1"
    media_types: tuple[str, ...] = ("text/plain",)

    def convert(self, content: bytes, media_type: str) -> Converted | Unconvertible:
        try:
            decoded = decode(content)
        except ValueError as error:
            # Not an error: a file in an encoding musubi will not guess at is a
            # unit the manifest reports with a reason, and the owner converts
            # it. Guessing would write mojibake into a corpus bound for a model
            # and would look exactly like a successful read.
            return Unconvertible("undecodable", str(error), self.name)

        rewritten = normalize_line_endings(decoded.text)
        return Converted(
            text=rewritten.text,
            trace=TraceMap.of_rewrite(rewritten).merged(),
            converter=self.name,
            # Everything needed to turn a character offset into a byte offset,
            # for the command that opens the file ([ADR-0018]). A fixed, tiny
            # amount of information rather than a per-character index.
            source_encoding=decoded.encoding,
            source_bom_bytes=decoded.bom_length,
        )


class PlainTextConverter(TextConverter):
    """`.txt`, and nothing else to say about it."""

    name = "plaintext@1"
    media_types: tuple[str, ...] = ("text/plain",)


class MarkdownConverter(TextConverter):
    """Markdown, which is already the output format.

    It is the same conversion as plain text, and saying so is better than
    inventing a difference. What a Markdown converter *could* do -- resolve
    wikilinks, drop `%%comments%%`, rewrite reference links -- are all
    transformations of somebody's writing, and each one needs its own argument
    about whether musubi is entitled to make it. None has been made, so none
    happens, and this class exists to claim the media type rather than to
    behave differently.
    """

    name = "markdown@1"
    media_types: tuple[str, ...] = ("text/markdown",)
