"""Every way musubi refuses.

This module imports nothing -- not even from the rest of musubi. An error type
that depends on a layer cannot be raised from below it, and refusing is the one
thing every layer has to be able to do.

musubi fails closed, and it fails closed *loudly*. An ingestion tool runs
unattended over a folder nobody is watching, so the alternative to raising is
almost never a visible error -- it is a corpus that is quietly wrong, and a
citation six months later that points at the wrong paragraph of the wrong file.
"""

from __future__ import annotations

__all__ = [
    "ContractError",
    "ConversionError",
    "CredentialFoundError",
    "EmptySourceError",
    "MusubiError",
    "SourceError",
    "TraceError",
]


class MusubiError(Exception):
    """Base class for everything musubi raises deliberately."""


class SourceError(MusubiError):
    """An export could not be read as the kind of export it claims to be.

    A Slack export missing ``channels.json``, a Notion zip whose pages do not
    resolve, a maildir with no ``cur/``. Reading it hopefully produces records
    that look right and are attributed to the wrong conversation, so it is
    refused instead.
    """


class ConversionError(MusubiError):
    """A unit could not be converted into text that points back at it.

    Not "could not be converted" -- that is a skip, and it is reported in the
    manifest with its reason. This is the narrower and worse case: text came
    out, and the map from that text back to the source did not (ADR-0004).
    """


class TraceError(MusubiError):
    """A trace map does not hold against the artefact it describes.

    Segments that overlap, run backwards, or name offsets outside the file.
    Every downstream citation is resolved through this map, so a map that does
    not hold is not a degraded map -- it is a source of confident wrong
    answers, and it stops the run.
    """


class EmptySourceError(MusubiError):
    """A source produced nothing, and a corpus built from it already exists.

    musubi cannot tell "the owner deleted everything" from "the source has
    become unreadable": a path that resolves and holds nothing looks the same
    either way. An unmounted drive, a cloud folder that has not populated, a
    drive letter reassigned under a configured path -- each yields zero units
    from a directory that exists.

    Withdrawal deletes what the manifest recorded writing, so on zero units it
    deletes all of it. That is right in one reading and destroys the corpus in
    the other, so the run stops and the operator looks.

    Zero is not a threshold chosen for caution. It is the only count at which
    the two readings cannot be separated: **one surviving unit proves the
    source is readable**, and every withdrawal beside it is a deletion somebody
    asked for.
    """


class CredentialFoundError(MusubiError):
    """Something that looks like a secret was found in the data being synced.

    Stops the whole run rather than skipping the unit (ADR-0008). A skipped
    unit is a hole in a corpus nobody reads the log of; a stopped run is a
    person looking at the thing they were about to publish.

    Carries what the screener matched on and *where*, never the value.
    """


class ContractError(MusubiError):
    """A document did not conform to a contract musubi recognises.

    Raised for an unknown ``contract`` value, a missing required field, or a
    manifest whose ``run_id`` does not re-derive. Guessing at an unrecognised
    version is how a consumer reads the wrong field and reports the wrong
    thing, so it is refused instead (ADR-0002).
    """
