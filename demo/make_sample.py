"""Build a small folder that has every problem musubi exists for.

Nothing here is contrived to flatter the library. Each file is a thing a real
vault contains and a thing that goes wrong:

```text
design/ギア設計.md      UTF-8 Japanese, a tracked URL in it
design/古いメモ.md      **Shift-JIS** -- a note from before everything was UTF-8
posts/index.html        a blog index: forty tracked links, nav, cookie banner
reports/report.pdf      **PDF 1.5** -- the page lives in a compressed object stream
setup/deploy.md         holds something shaped exactly like an AWS key
photo.png               a format musubi does not read
```

Run it, then follow `demo/README.md`.

    uv run python demo/make_sample.py
"""

from __future__ import annotations

import io
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE = HERE / "sample-vault"

GEAR = """# ギア設計

テントは 2.4kg。ブーツのほうが効く。山では軽さがすべて。

参考にしたページ: https://example.test/gear?utm_source=newsletter&utm_medium=email
"""

OLD = """# 古いメモ

2013年の記録。当時のテントは 3.8kg あった。
いまのものと比べると、ほとんど別の道具といっていい。
"""

DEPLOY = """# deploy

Set the credentials before running the job:

    aws_access_key_id = AKIAIOSFODNN7EXAMPLE
"""

POST = (
    "<li>Post {i}: <a href='https://example.test/post/{i}"
    "?utm_source=feed&utm_medium=rss&utm_campaign=weekly'>read it</a></li>\n"
)

INDEX = (
    "<!doctype html><html><head><title>Posts</title></head><body>\n"
    "<a href='#main'>Skip to main content</a>\n"
    "<div id='cookies'><p>We use cookies. <button>Accept all cookies</button></p></div>\n"
    "<nav><a href='/'>Home</a><a href='/about'>About</a></nav>\n"
    "<main id='main'><article>\n"
    "<h1>Everything written this year</h1>\n"
    "<p>A tent that weighs 2.4kg is a tent you carry all day, and the difference "
    "shows up in the last hour rather than the first.</p>\n"
    "<ul>\n" + "".join(POST.format(i=i) for i in range(40)) + "</ul>\n"
    "</article></main>\n"
    "<div class='newsletter'><p>Subscribe to our newsletter</p></div>\n"
    "<footer><p>Copyright 2026 Example Corporation.</p></footer>\n"
    "</body></html>\n"
)


def modern_pdf() -> bytes:
    """PDF 1.5, with the page inside a compressed object stream.

    This is what almost every current producer writes, and what a scan for
    `N 0 obj` cannot see -- the whole reason `musubi[pdf]` exists.
    """
    inside = {
        2: b"<< /Type /Catalog /Pages 3 0 R >>",
        3: b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        4: (
            b"<< /Type /Page /Parent 3 0 R /MediaBox [0 0 612 792] /Contents 5 0 R "
            b"/Resources << /Font << /F1 7 0 R >> >> >>"
        ),
    }
    pairs, bodies, at = [], [], 0
    for number, body in inside.items():
        pairs.append(b"%d %d" % (number, at))
        bodies.append(body)
        at += len(body) + 1
    header = b" ".join(pairs) + b"\n"
    packed = zlib.compress(header + b"\n".join(bodies) + b"\n")

    content = (
        b"BT /F1 12 Tf 72 720 Td (Trip report: the Kita-Alps, October) Tj "
        b"0 -16 Td (The tent weighed 2.4kg and it mattered on day three.) Tj ET"
    )
    stream = b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream"

    out = io.BytesIO()
    out.write(b"%PDF-1.5\n")
    offsets: dict[int, int] = {}
    offsets[1] = out.tell()
    out.write(
        b"1 0 obj\n<< /Type /ObjStm /N %d /First %d /Length %d /Filter /FlateDecode >>\nstream\n"
        % (len(inside), len(header), len(packed))
        + packed
        + b"\nendstream\nendobj\n"
    )
    offsets[5] = out.tell()
    out.write(b"5 0 obj\n" + stream + b"\nendobj\n")
    offsets[7] = out.tell()
    out.write(b"7 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    table = out.tell()
    rows = {
        0: (0, 0, 65535),
        1: (1, offsets[1], 0),
        2: (2, 1, 0),
        3: (2, 1, 1),
        4: (2, 1, 2),
        5: (1, offsets[5], 0),
        6: (1, table, 0),
        7: (1, offsets[7], 0),
    }
    data = b"".join(struct.pack(">BIH", *rows[n]) for n in sorted(rows))
    index = b" ".join(b"%d 1" % n for n in sorted(rows))
    packed_rows = zlib.compress(data)
    out.write(
        b"6 0 obj\n<< /Type /XRef /Size %d /Index [%s] /W [1 4 2] /Root 2 0 R "
        b"/Filter /FlateDecode /Length %d >>\nstream\n"
        % (len(rows), index, len(packed_rows))
        + packed_rows
        + b"\nendstream\nendobj\n"
    )
    out.write(b"startxref\n%d\n%%%%EOF\n" % table)
    return out.getvalue()


def main() -> int:
    if SAMPLE.exists():
        print(f"{SAMPLE} already exists; delete it to build a fresh one.", file=sys.stderr)
        return 1

    for folder in ("design", "posts", "reports", "setup"):
        (SAMPLE / folder).mkdir(parents=True)

    (SAMPLE / "design" / "ギア設計.md").write_bytes(GEAR.encode("utf-8"))
    # The one that used to be unreadable. Written as Shift-JIS on purpose.
    (SAMPLE / "design" / "古いメモ.md").write_bytes(OLD.encode("cp932"))
    (SAMPLE / "posts" / "index.html").write_bytes(INDEX.encode("utf-8"))
    (SAMPLE / "reports" / "report.pdf").write_bytes(modern_pdf())
    (SAMPLE / "setup" / "deploy.md").write_bytes(DEPLOY.encode("utf-8"))
    (SAMPLE / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"not really a png")

    total = sum(p.stat().st_size for p in SAMPLE.rglob("*") if p.is_file())
    print(f"built {SAMPLE}")
    print(f"  6 files, {total:,} bytes")
    print()
    print("Now follow demo/README.md, or just run:")
    print("  musubi plan demo/sample-vault --as filesystem")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
