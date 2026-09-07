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

from dataclasses import dataclass

__all__ = [
    "CATALOGUE",
    "DONE",
    "ERRORS_CONTRACT",
    "FAILED",
    "NOT_PRINTED",
    "OPEN_NAMESPACES",
    "REFUSED",
    "USAGE",
    "ContractError",
    "ConversionError",
    "CredentialFoundError",
    "DifferentSourceError",
    "EmptySourceError",
    "EverythingSkippedError",
    "InterruptedRunError",
    "Kind",
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


class EverythingSkippedError(MusubiError):
    """Units were read and not one of them became a document.

    The question `sora` asked musubi to answer: **is a run that skipped
    everything a success?** ([ADR-0046])

    It is not, and this project had already decided so somewhere else.
    `Manifest.summary` records the shape it refuses to print --

        0 emitted, 1 skipped, 0 removals, **100.0% traceable**

    -- a number maximised by total failure. A run that read two hundred files
    and wrote none of them is the same sentence with a wider blast radius: the
    owner pointed musubi at a folder and got an empty corpus, and the only
    thing that said so was a count of skips.

    **Distinct from `EmptySourceError`, which was answering this and saying
    the wrong thing.** That one is for a source that produced *no units*, and
    it fired here too -- so a folder of unreadable PDFs was refused with the
    words "produced no units", sending the owner to look at whether the folder
    could be read at all. It could. Nothing in it could be converted, which is
    a different problem with a different fix.

    Not a threshold. This is the one count where "musubi read your folder" and
    "musubi read nothing of your folder" cannot be told apart from the outside:
    **one emitted document proves the run did something**, and a corpus with
    some documents missing is a skip list, which is reported and is not this.
    """


class DifferentSourceError(MusubiError):
    """This corpus was written by a different source than the one syncing it.

    A destination belongs to the source that wrote it, because the manifest is
    an account of **one run** ([ADR-0002]) and withdrawal deletes whatever the
    previous manifest recorded that this one does not. So a second source
    pointed at the same folder does not add to the corpus; it **replaces** it,
    and the documents the first source wrote are deleted.

    Measured: a vault synced into a corpus, then a second folder synced into
    the same corpus, and the vault's documents were gone. Exit 0, nothing said,
    `musubi verify` passing afterwards because the corpus really was consistent
    with the manifest that had just replaced it.

    Not a threshold and not a guess. The two readings -- *I am replacing this
    corpus* and *I meant a different folder* -- are indistinguishable from
    here, and one of them destroys work. `--withdraw-all` is the operator
    saying they have looked, which is the same gesture the other two refusals
    take ([ADR-0049]).
    """


# -- what a program driving musubi can be told, and where it is written down --


#: The exit codes, here rather than in the CLI, because they are musubi's
#: contract with whatever runs it and not a detail of one interface. The
#: catalogue below quotes them, so a code and its meaning cannot come apart.
#:
#: ``REFUSED`` is the one an orchestrator has to tell apart: musubi declined
#: on purpose and nothing was written, so retrying changes nothing and a
#: person has to look. ``USAGE`` is argparse's own value, and is why refusal
#: is 3.
DONE = 0
FAILED = 1
USAGE = 2
REFUSED = 3

#: Not frozen. A second program has to have produced and consumed one first,
#: which is [ADR-0024]'s rule and not a date.
ERRORS_CONTRACT = "musubi.errors/1-draft"


@dataclass(frozen=True, slots=True)
class Kind:
    """One way musubi can fail, as a program reading `stderr` sees it.

    `kind` is exactly what is printed before the first colon. That is the
    whole of the interface: `sora` folds incidents by it and keeps nothing
    else from the line, because a message can quote a path somebody's file
    system chose.
    """

    kind: str
    exit_code: int
    #: One of `refused`, `unavailable`, `failed`, `timed_out` -- `sora`'s
    #: vocabulary. musubi never produces the last two-thirds of it, and
    #: says so rather than leaving a reader to infer it from absence.
    outcome: str
    #: Would asking again, unchanged, do anything? Almost never here, and the
    #: reason is [ADR-0007]: musubi reads a folder that is already on the disk.
    #: There is no network, no lock, no service and no timeout, so there is no
    #: transient failure to wait out. The one exception is the file system
    #: itself.
    retryable: bool
    detail: str
    #: Written here rather than translated downstream. `sora` asked for this
    #: and the reason is good: two sentences written by one hand cannot
    #: disagree, and a translation maintained by the reader drifts from the
    #: thing it describes the first time either changes.
    detail_ja: str


#: Every kind musubi can print before a colon on `stderr`, with what a caller
#: may conclude from it.
#:
#: **The list is checked against the code, not maintained beside it.**
#: `tests/test_error_catalogue.py` asserts that every `MusubiError` subclass
#: appears here and that every entry names something that exists, because a
#: catalogue listing six of seven kinds is worse than none: `sora` folds by
#: kind, and a kind it has never been told about is an incident it cannot
#: name.
CATALOGUE: tuple[Kind, ...] = (
    # -- refusals: musubi declined, and nothing was written -----------------
    Kind(
        "CredentialFoundError",
        REFUSED,
        "refused",
        False,
        "Something matching a credential signature was found in the data being "
        "synced, so the whole run stopped and nothing was written. A person has "
        "to look; the exemption is `--allow rule:unit_key`.",
        "同期しようとしたデータの中に認証情報の形をしたものが見つかったため、"
        "run 全体を停止し、何も書いていない。人が見る必要がある。"
        "見た上で許すなら `--allow rule:unit_key`。",
    ),
    Kind(
        "DifferentSourceError",
        REFUSED,
        "refused",
        False,
        "This corpus was written by a different source than the one syncing it. "
        "A destination belongs to one source, so this run would take out every "
        "document the other one wrote. Sync into a different folder, or pass "
        "`--withdraw-all` to replace the corpus.",
        "このコーパスを書いたのは、今 sync している source とは別の source。"
        "1 つの宛先は 1 つの source のものなので、このまま進めると"
        "もう一方が書いた文書が全部消える。別のフォルダに sync するか、"
        "置き換えてよいなら `--withdraw-all`。",
    ),
    Kind(
        "EmptySourceError",
        REFUSED,
        "refused",
        False,
        "The source produced no units at all and a corpus already exists, so "
        "withdrawal would take every document in it. An empty source and an "
        "unreadable one look identical from here. `--withdraw-all` is the "
        "operator saying they have looked.",
        "source が unit を 1 件も返さず、既存のコーパスがあるため、"
        "取り下げれば全文書が消える。空の source と読めない source は"
        "ここからは見分けがつかない。確認した上でなら `--withdraw-all`。",
    ),
    Kind(
        "EverythingSkippedError",
        REFUSED,
        "refused",
        False,
        "Units were read and not one became a document. The folder can be read; "
        "nothing in it could be converted. Check the skip reasons in the report: "
        "an optional extra may be what is missing.",
        "unit は読めたが、1 件も文書にならなかった。フォルダは読める。"
        "中身が 1 つも変換できなかった。レポートの skip 理由を見ること。"
        "optional な extra が入っていないだけのこともある。",
    ),
    # -- failures: something was wrong, and fixing it and retrying is right --
    Kind(
        "SourceError",
        FAILED,
        "failed",
        False,
        "An export could not be read as the kind of export it claims to be, or "
        "a path does not exist. Reading it hopefully produces records attributed "
        "to the wrong conversation, so it is refused instead.",
        "export が名乗っている形式として読めなかったか、パスが存在しない。"
        "推測して読むと、間違った会話に紐づいたレコードができるので拒否する。",
    ),
    Kind(
        "ConversionError",
        FAILED,
        "failed",
        False,
        "Text came out of a unit and the map back to its source did not. Not a "
        "skip -- a skip is reported in the manifest with its reason. This is the "
        "narrower and worse case.",
        "unit からテキストは出たが、source へ戻る map が出なかった。"
        "skip ではない（skip は理由つきで manifest に載る）。より狭く、より悪い方。",
    ),
    Kind(
        "TraceError",
        FAILED,
        "failed",
        False,
        "A trace map does not hold against the artefact it describes: segments "
        "that overlap, run backwards, or name offsets outside the file. Every "
        "citation is resolved through this map, so it stops the run.",
        "trace map が、対象の artefact に対して成り立たない。"
        "segment の重複・逆走・ファイル外のオフセットなど。"
        "引用はすべてこの map を通して解決されるので、run を止める。",
    ),
    Kind(
        "ContractError",
        FAILED,
        "failed",
        False,
        "A document did not conform to a contract musubi recognises: an unknown "
        "`contract` value, a missing required field, or a manifest whose "
        "`run_id` does not re-derive.",
        "musubi が知っている契約に文書が適合しない。未知の `contract` 値、"
        "必須フィールドの欠落、`run_id` が再導出できない manifest など。",
    ),
    Kind(
        "Unverified",
        FAILED,
        "failed",
        False,
        "`musubi verify` found faults in a corpus. The corpus is on disk and it "
        "does not hold: the report on standard output names each fault. Nothing "
        "was changed.",
        "`musubi verify` がコーパスに不整合を見つけた。"
        "コーパスはディスク上にあり、成り立っていない。"
        "標準出力のレポートが各不整合を挙げる。何も変更していない。",
    ),
    Kind(
        "InterruptedRunError",
        FAILED,
        "failed",
        True,
        "Another musubi run into the same destination removed this one's "
        "staging area while it was promoting. Some documents were moved and "
        "the manifest was not: `musubi verify` will say which, and **running "
        "the sync again repairs it**. One run at a time per destination.",
        "同じ宛先へのもう 1 つの musubi の run が、promote 中にこの run の "
        "staging を消した。一部の文書だけが移り、manifest は移っていない。"
        "`musubi verify` がどれかを言う。**もう一度 sync すれば直る。**"
        "1 つの宛先につき run は 1 つ。",
    ),
    Kind(
        "Unreadable",
        FAILED,
        "failed",
        True,
        "The file system refused: a disk that is full, a file another process "
        "holds, a path that stopped resolving mid-run. **The one retryable kind "
        "musubi has**, because it is the one failure that is about the machine "
        "rather than about the data.",
        "ファイルシステムに断られた。ディスクが一杯、他プロセスがファイルを掴んでいる、"
        "run の途中でパスが解決しなくなった、など。"
        "**musubi で唯一 retry する価値のある kind**。"
        "データではなく機械についての失敗だから。",
    ),
    Kind(
        "Usage",
        USAGE,
        "failed",
        False,
        "The arguments did not parse. `musubi <command> --help` states them. "
        "Retrying the same command line does the same thing.",
        "引数が解釈できなかった。`musubi <command> --help` に書いてある。"
        "同じコマンドラインを再実行しても結果は同じ。",
    ),
    Kind(
        "Unexpected",
        FAILED,
        "failed",
        False,
        "A bug in musubi. The traceback follows on the same stream, for the "
        "person who has to fix it. Named rather than left as a bare traceback "
        "so that a reader folding by kind gets one bucket instead of a bucket "
        "per line of Python.",
        "musubi のバグ。同じストリームに traceback が続く（直す人のため）。"
        "裸の traceback にせず名前をつけてあるのは、kind で畳む読み手が"
        "Python の行ごとにバケツを作らずに済むようにするため。",
    ),
)

#: Prefixes for kinds musubi assembles at run time from somebody else's
#: vocabulary. It assembles none: every kind above is a name musubi chose and
#: the list is closed. Present because an empty list is an answer and a
#: missing field is a shrug.
OPEN_NAMESPACES: tuple[str, ...] = ()


#: Kinds that exist and never reach `stderr`, each with the reason.
#:
#: Listed rather than omitted, for the reason `NOT_FLOORED` is listed in the
#: converter register: an exclusion nobody wrote down is indistinguishable
#: from an oversight, and `tests/test_error_catalogue.py` requires every
#: `MusubiError` subclass to be in the catalogue **or** in here.
NOT_PRINTED: dict[str, str] = {
    "OutsideRootError": (
        "raised inside the MCP server's tool loop and returned as a tool "
        "result with `isError`, never as a line on stderr -- a refusal is an "
        "answer to the model, not a transport failure. The MCP surface has its "
        "own error channel, and this catalogue is about the command line."
    ),
}


class InterruptedRunError(MusubiError):
    """The staging area went away while this run was promoting it.

    One thing does that: **another musubi run into the same destination**.
    `begin()` removes the staging area and makes it again, so a second run
    starting while a first is mid-flight takes the first one's files with it.

    Measured, with the second run's `begin()` landing after four of six
    documents had been promoted: the corpus held four new documents and an old
    manifest, `musubi verify` reported eight faults, and **the next ordinary
    sync repaired all of it**. So this is a detectable, self-healing
    inconsistency rather than a corrupt corpus -- which is what [ADR-0008]'s
    promotion order is for.

    It is named because of how it used to arrive. `promote()` let the
    `FileNotFoundError` out, so the command line reported `Unreadable: the file
    system refused`, and a person read that and went to look at their disk. The
    file system was fine. Another copy of musubi was running ([ADR-0053]).
    """
