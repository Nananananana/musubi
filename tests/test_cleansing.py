"""Taking the tracking out of a URL without losing an offset.

ADR-0005: every firing is recorded with the rule that made it, by hash and never
by value. ADR-0016: a rule matches a parsed parameter name, and nothing here
runs a regular expression over anybody's corpus.
"""

from __future__ import annotations

from dataclasses import fields

import pytest
from hypothesis import given
from hypothesis import strategies as st

from musubi.domain.cleansing import cleanse, find_urls
from musubi.domain.hashing import content_hash
from musubi.domain.removal import Match, RemovalRecord, Rule, Ruleset
from musubi.domain.span import Span
from musubi.domain.trace import Kind, TraceMap
from musubi.infrastructure.rules.core import CORE

UTM = Rule(
    id="tracking.utm-family",
    kind="tracking_parameter",
    match=Match.PREFIX,
    value="utm_",
    evidence="test",
    since="2026-08-30",
)
FBCLID = Rule(
    id="tracking.fbclid",
    kind="tracking_parameter",
    match=Match.EXACT,
    value="fbclid",
    evidence="test",
    since="2026-08-30",
)
PACK = Ruleset(id="test", version="1", rules=(UTM, FBCLID))


# -- finding URLs -----------------------------------------------------------


def test_a_bare_url() -> None:
    text = "see https://example.com/a for more"
    assert [s.slice(text) for s in find_urls(text)] == ["https://example.com/a"]


def test_a_trailing_full_stop_belongs_to_the_sentence() -> None:
    text = "see https://example.com/a."
    assert [s.slice(text) for s in find_urls(text)] == ["https://example.com/a"]


def test_a_markdown_link_ends_at_its_bracket() -> None:
    text = "[docs](https://example.com/a?utm_source=x)"
    assert [s.slice(text) for s in find_urls(text)] == ["https://example.com/a?utm_source=x"]


def test_a_url_may_keep_brackets_it_opened_itself() -> None:
    """A Wikipedia article title. Only a closer that never opened is given back."""
    text = "https://en.wikipedia.org/wiki/Knot_(mathematics)"
    assert [s.slice(text) for s in find_urls(text)] == [text]


def test_an_autolink_ends_at_its_angle_bracket() -> None:
    text = "<https://example.com/a>"
    assert [s.slice(text) for s in find_urls(text)] == ["https://example.com/a"]


def test_several_urls_are_found_left_to_right() -> None:
    text = "http://a.example and https://b.example"
    assert [s.slice(text) for s in find_urls(text)] == ["http://a.example", "https://b.example"]


def test_text_with_no_url_finds_nothing() -> None:
    assert find_urls("the tent weighs 2.4kg") == []


def test_a_scheme_with_nothing_after_it_is_still_a_span() -> None:
    assert [s.slice("https://") for s in find_urls("https://")] == ["https://"]


# -- cleansing --------------------------------------------------------------


def test_a_tracking_parameter_is_removed_and_the_url_stays_valid() -> None:
    text = "see https://example.com/a?utm_source=news&id=7 today"
    result = cleanse(text, PACK)
    assert result.text == "see https://example.com/a?id=7 today"


def test_the_only_parameter_takes_the_question_mark_with_it() -> None:
    result = cleanse("https://example.com/a?fbclid=abc", PACK)
    assert result.text == "https://example.com/a"


def test_a_parameter_in_the_middle_leaves_the_others_joined() -> None:
    result = cleanse("https://example.com/?a=1&utm_medium=x&b=2", PACK)
    assert result.text == "https://example.com/?a=1&b=2"


def test_the_last_parameter_leaves_no_dangling_ampersand() -> None:
    result = cleanse("https://example.com/?a=1&fbclid=x", PACK)
    assert result.text == "https://example.com/?a=1"


def test_every_parameter_matching_still_leaves_a_usable_url() -> None:
    result = cleanse("https://example.com/p?utm_source=a&utm_medium=b&fbclid=c", PACK)
    assert result.text == "https://example.com/p"
    assert len(result.removals) == 3


def test_a_fragment_survives_the_query_being_cut() -> None:
    result = cleanse("https://example.com/a?fbclid=x#section", PACK)
    assert result.text == "https://example.com/a#section"


def test_a_url_with_no_query_is_left_alone() -> None:
    result = cleanse("https://example.com/a", PACK)
    assert result.text == "https://example.com/a"
    assert result.removals == ()


def test_a_query_with_nothing_to_remove_is_left_byte_for_byte() -> None:
    text = "https://example.com/a?id=7&page=2"
    result = cleanse(text, PACK)
    assert result.text == text
    assert result.removals == ()
    assert [s.kind for s in TraceMap.of_rewrite(result.rewritten).segments] == [Kind.VERBATIM]


def test_a_parameter_with_no_value_is_matched_by_name() -> None:
    result = cleanse("https://example.com/?fbclid&keep", PACK)
    assert result.text == "https://example.com/?keep"


def test_two_urls_in_one_document_are_both_cleansed() -> None:
    text = "a https://x.example/?fbclid=1 b https://y.example/?fbclid=2 c"
    result = cleanse(text, PACK)
    assert result.text == "a https://x.example/ b https://y.example/ c"
    assert len(result.removals) == 2


# -- what the record says ---------------------------------------------------


def test_a_removal_names_its_rule_and_where_it_struck() -> None:
    text = "https://example.com/?utm_source=news"
    result = cleanse(text, PACK)
    (removal,) = result.removals
    assert removal.rule == "tracking.utm-family"
    assert removal.kind == "tracking_parameter"
    assert removal.span.slice(text) == "utm_source=news"
    assert removal.removed_characters == len("utm_source=news")


def test_a_removal_carries_a_hash_and_never_the_value() -> None:
    """ADR-0005. The removed thing is usually the sensitive thing, and a
    manifest that quoted it would re-publish exactly what the run was for."""
    result = cleanse("https://example.com/?utm_source=who-i-am", PACK)
    (removal,) = result.removals
    assert removal.removed_hash == content_hash("utm_source=who-i-am")
    written = [getattr(removal, field.name) for field in fields(removal)]
    assert not any("who-i-am" in str(value) for value in written)


def test_the_same_value_removed_twice_hashes_the_same() -> None:
    """What the hash is for: showing two runs took the same thing, without
    carrying it."""
    text = "https://a.example/?fbclid=Z https://b.example/?fbclid=Z"
    left, right = cleanse(text, PACK).removals
    assert left.removed_hash == right.removed_hash
    assert left.span != right.span


# -- the map ----------------------------------------------------------------


def test_a_cut_query_is_a_transformation_in_the_map() -> None:
    result = cleanse("see https://example.com/?a=1&fbclid=x today", PACK)
    trace = TraceMap.of_rewrite(result.rewritten)
    assert [s.kind for s in trace.segments] == [Kind.VERBATIM, Kind.TRANSFORMED, Kind.VERBATIM]
    assert trace.segments[1].rule == "url_query"


def test_a_query_removed_entirely_is_a_removal_in_the_map() -> None:
    result = cleanse("https://example.com/a?fbclid=x", PACK)
    trace = TraceMap.of_rewrite(result.rewritten)
    assert [s.kind for s in trace.segments] == [Kind.VERBATIM, Kind.REMOVAL]


def test_everything_after_a_cut_still_resolves_to_the_right_place() -> None:
    """The reason a removal is a discontinuity in the map rather than a silent
    shift: the sentence after the link has to keep pointing at itself."""
    text = "see https://example.com/?fbclid=x and the tent weighs 2.4kg"
    result = cleanse(text, PACK)
    trace = TraceMap.of_rewrite(result.rewritten)

    at = result.text.index("2.4kg")
    found = trace.source_span_of(Span(at, at + len("2.4kg")))
    assert found.slice(text) == "2.4kg"


def test_the_text_is_shorter_by_exactly_what_was_recorded() -> None:
    text = "https://example.com/?utm_source=a&keep=1&fbclid=b"
    result = cleanse(text, PACK)
    # Two parameters plus the two delimiters that went with them.
    assert len(text) - len(result.text) == sum(r.removed_characters for r in result.removals) + 2


# -- the vendored pack ------------------------------------------------------


def test_the_core_pack_removes_what_the_catalogue_says_it_should() -> None:
    text = (
        "https://example.com/article"
        "?utm_source=newsletter&utm_campaign=aug&fbclid=IwAR0&mc_eid=abc123&id=7"
    )
    result = cleanse(text, CORE)
    assert result.text == "https://example.com/article?id=7"
    assert sorted(r.rule for r in result.removals) == [
        "tracking.fbclid",
        "tracking.mc-eid",
        "tracking.utm-family",
        "tracking.utm-family",
    ]


def test_the_core_pack_leaves_a_parameter_that_carries_meaning() -> None:
    text = "https://example.com/search?q=%E7%B4%A1%E3%81%8E&page=2&lang=ja"
    assert cleanse(text, CORE).text == text


def test_the_over_broad_catalogue_rule_was_not_adopted() -> None:
    """ClearURLs strips `[a-z]?mc`, which eats `amc`, `bmc` and twenty-four
    others. Tolerable in a browser; in a corpus it silently changes somebody's
    link. ADR-0016 records the decision, and this is what checks it."""
    text = "https://example.com/?amc=1&bmc=2&mc=3"
    assert cleanse(text, CORE).text == text


def test_every_core_rule_states_its_evidence_and_when_it_was_reviewed() -> None:
    assert CORE.rules, "the pack is empty; this test would pass without reading a rule"
    for rule in CORE.rules:
        assert rule.evidence, f"{rule.id} has no evidence"
        assert rule.since, f"{rule.id} has no review date"


def test_referral_marketing_is_its_own_kind_so_it_can_be_spared_later() -> None:
    assert "referral_marketing" in CORE.kinds()
    rule = CORE.matching("ref")
    assert rule is not None
    assert rule.kind == "referral_marketing"


# -- rules --------------------------------------------------------------


def test_exact_beats_prefix_when_both_claim_a_name() -> None:
    exact = Rule(
        id="b.exact", kind="k", match=Match.EXACT, value="utm_x", evidence="e", since="2026-08-30"
    )
    pack = Ruleset(id="t", version="1", rules=(UTM, exact))
    assert pack.matching("utm_x") is exact


def test_the_longer_prefix_wins() -> None:
    longer = Rule(
        id="a.longer",
        kind="k",
        match=Match.PREFIX,
        value="utm_source",
        evidence="e",
        since="2026-08-30",
    )
    pack = Ruleset(id="t", version="1", rules=(UTM, longer))
    assert pack.matching("utm_source_x") is longer


def test_a_rule_must_state_its_evidence() -> None:
    with pytest.raises(ValueError, match="evidence"):
        Rule(id="x", kind="k", match=Match.EXACT, value="v", evidence="", since="2026-08-30")


def test_a_rule_must_say_when_it_was_reviewed() -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        Rule(id="x", kind="k", match=Match.EXACT, value="v", evidence="e", since="last year")


def test_a_rule_must_match_something() -> None:
    with pytest.raises(ValueError, match="matches nothing"):
        Rule(id="x", kind="k", match=Match.EXACT, value="", evidence="e", since="2026-08-30")


def test_a_rule_must_have_an_id_and_a_kind() -> None:
    with pytest.raises(ValueError, match="no id"):
        Rule(id="", kind="k", match=Match.EXACT, value="v", evidence="e", since="2026-08-30")
    with pytest.raises(ValueError, match="no kind"):
        Rule(id="x", kind="", match=Match.EXACT, value="v", evidence="e", since="2026-08-30")


def test_a_ruleset_refuses_two_rules_with_the_same_id() -> None:
    with pytest.raises(ValueError, match="twice"):
        Ruleset(id="t", version="1", rules=(UTM, UTM))


def test_a_removal_record_is_built_from_the_rule_that_made_it() -> None:
    record = RemovalRecord.of(FBCLID, Span(4, 10), "fbclid=x")
    assert record.rule == "tracking.fbclid"
    assert record.kind == "tracking_parameter"


# -- the invariants ---------------------------------------------------------


@given(st.text(max_size=120))
def test_cleansing_any_text_keeps_a_tiling(text: str) -> None:
    result = cleanse(text, CORE)
    trace = TraceMap.of_rewrite(result.rewritten)
    at = 0
    for segment in trace.segments:
        assert segment.out.start == at
        at = segment.out.end
    assert at == len(result.text)


@given(st.text(max_size=120))
def test_cleansing_never_makes_text_longer(text: str) -> None:
    assert len(cleanse(text, CORE).text) <= len(text)


@given(st.text(max_size=120))
def test_cleansing_is_idempotent(text: str) -> None:
    once = cleanse(text, CORE).text
    assert cleanse(once, CORE).text == once


@given(st.sampled_from(["utm_source", "fbclid", "mc_eid", "_ga", "gclid"]), st.text(max_size=10))
def test_a_known_parameter_never_survives(name: str, value: str) -> None:
    safe = "".join(c for c in value if c not in "&#?= \t\n<>\"'")
    text = f"https://example.com/?{name}={safe}"
    assert name not in cleanse(text, CORE).text
