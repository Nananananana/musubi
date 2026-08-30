# 20. The console is not the contract, and the exit code reports the run

**Status:** accepted

## Context

`musubi sync` on a Japanese Windows console, where the default codec is
`cp932`:

```console
$ musubi sync vault --into corpus
UnicodeEncodeError: 'cp932' codec can't encode character '—'
$ echo $?
1
$ find corpus -type f | wc -l
3
```

The corpus is complete. The staging promoted, the manifest is written, the trace
maps are there. Only the report crashed, on an em dash in a heading.

A caller reading the exit code concludes nothing was written, and the
destination is full. It is the shape of a violation of
[ADR-0008](0008-a-credential-stops-the-run.md)'s central promise — a sync is
all-or-nothing — while being exactly the opposite: the run succeeded and the
*rendering* failed. Nothing about this is exotic; `cp932` is the console default
on every un-reconfigured Japanese Windows.

Looking for the same fault elsewhere found a worse one. `--json` does not crash:

```console
$ musubi plan jvault --json > out.json ; echo $?
0
$ python -c "import pathlib; pathlib.Path('out.json').read_bytes().decode('utf-8')"
UnicodeDecodeError: 'utf-8' codec can't decode byte 0x90 in position 877
```

`render()` writes with `ensure_ascii=False`, so a Japanese `unit_key` reaches
`print()` and is encoded in whatever the console happens to be. JSON is UTF-8 by
definition. A consumer piping that gets a document which is not valid UTF-8,
**with exit 0 and no error anywhere** — no error, no warning, a file full of
plausible nonsense, which is the failure shape this project exists to make
impossible.

One root cause: the console's encoding reaching output whose encoding is not the
console's business.

## Decision

**A document is UTF-8, whatever the console is.** `--json` and every future
machine-facing output are encoded once, to UTF-8, and written to
`sys.stdout.buffer`. They never pass through the terminal's codec, because they
are not written for the terminal.

**A human report may be lossy and must never fail a run.** The report stream is
configured to substitute what it cannot encode, so a character the console
cannot show becomes a replacement character and the rest of the report arrives.
A person who cannot see an em dash still wants to know what was written.

**The exit code reports the run, not the rendering.** Once `sync()` has
returned, the corpus is built and the exit code says so. Nothing that happens
while printing can change it.

Configuring the stream rather than sanitising each string is deliberate. musubi's
subject is other people's documents; a skip line naming `写真.png`, an excerpt in
`musubi trace`, a rule id somebody added — every one of them is a character
musubi does not choose. Avoiding non-ASCII in musubi's *own* strings would fix
today's em dash and none of those.

## Consequences

A test drives the real CLI with a stream that cannot hold the output, and
asserts the run still reports success and the document is still valid UTF-8.
This class of bug is invisible on a UTF-8 developer machine and would otherwise
be found only by somebody running the tool in the language it was written for.

## What it costs

**A document printed to a `cp932` console looks like mojibake.** It is UTF-8 and
the bytes are right, which is what matters when it is redirected or piped — the
only thing `--json` is for. Displaying it was never the use.

**A report can lose a character.** `写真.png` on a console that cannot render it
shows replacement characters, and a reader may not be able to tell two skipped
files apart. Losing a glyph is a smaller failure than losing the report, and the
manifest carries the exact name for anybody who needs it.
