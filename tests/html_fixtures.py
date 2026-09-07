"""One generated page, and what a main-content extractor is meant to do with it.

Beside `pdf_fixtures.py` and for the same reason: `tools/html_coverage.py` and
`tests/converter_floors.py` both measure against this page, and two fixtures
that are supposed to be the same page and are not is a worse problem than an
unusual import.

Generated rather than collected, which is a real limitation and is stated where
the numbers are printed: synthetic HTML has the right *shape* -- a nav, an
article, a footer, entities, inline markup -- and none of the mess of a real
page. What it can answer is the relative question, which is the one being asked.
"""

from __future__ import annotations

__all__ = ["BOILERPLATE", "CONTENT", "page"]

#: Strings that must not survive. Each is in the fixture inside a structure a
#: main-content extractor is supposed to reject.
BOILERPLATE = (
    "Skip to main content",
    "Accept all cookies",
    "Subscribe to our newsletter",
    "Copyright 2026 Example Corporation",
    "Related articles you may enjoy",
    "Follow us on social media",
)

#: Strings that must survive. Losing one of these is worse than keeping a
#: banner: a corpus that quietly dropped a paragraph answers questions without
#: it and nothing anywhere says so.
CONTENT = (
    "A tent that weighs 2.4kg is a tent you carry all day",
    "The stove is the part people get wrong",
    "Boots matter more than the pack",
)


def page() -> bytes:
    return f"""<!doctype html>
<html lang="en"><head><title>The gear list</title>
<meta name="description" content="notes on what to carry"></head>
<body>
<a href="#main">{BOILERPLATE[0]}</a>
<div id="cookie-banner"><p>We use cookies. <button>{BOILERPLATE[1]}</button></p></div>
<nav><ul><li><a href="/">Home</a></li><li><a href="/about">About</a></li>
<li><a href="/blog">Blog</a></li><li><a href="/contact">Contact</a></li></ul></nav>
<main id="main"><article>
<h1>The gear list</h1>
<p>{CONTENT[0]} &mdash; and the difference is measured in kilometres.</p>
<p>{CONTENT[1]}. A remote canister freezes; a liquid-fuel stove does not.</p>
<p>{CONTENT[2]}, because a blister ends a walk and a heavy pack only slows it.</p>
<table><tr><th>Item</th><th>Mass</th></tr><tr><td>Tent</td><td>2.4&nbsp;kg</td></tr></table>
</article></main>
<aside><h2>{BOILERPLATE[4]}</h2><ul><li><a href="/x">Another post</a></li></ul></aside>
<div class="newsletter"><p>{BOILERPLATE[2]}</p></div>
<footer><p>{BOILERPLATE[3]}. All rights reserved.</p>
<p>{BOILERPLATE[5]}.</p></footer>
</body></html>
""".encode()
