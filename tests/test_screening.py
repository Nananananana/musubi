"""Finding a credential, and saying so without repeating it.

ADR-0008: a hit stops the run and musubi does not redact. ADR-0017: the default
tier is signatures, because entropy-only detection scores 21.1% precision on
CredData and four false stops in five is not a gate.
"""

from __future__ import annotations

from dataclasses import fields

import pytest
from hypothesis import given
from hypothesis import strategies as st

from musubi.domain.hashing import content_hash
from musubi.domain.screening import BASE62, Finding, Signature, shannon_entropy
from musubi.domain.span import Span
from musubi.infrastructure.screeners import (
    CompositeScreener,
    EntropyScreener,
    SignatureScreener,
    default_screener,
)
from musubi.infrastructure.screeners.signatures import SIGNATURES
from musubi.ports.screener import Screener

AWS = "AKIA" + "IOSFODNN7EXAMPLE"
GITHUB = "ghp_" + "a" * 36
ANTHROPIC = "sk-ant-api03-" + "x" * 80


# -- signatures -------------------------------------------------------------


def test_an_aws_access_key_is_found() -> None:
    (finding,) = SignatureScreener().screen(f"export AWS_ACCESS_KEY_ID={AWS}")
    assert finding.rule == "aws.access-key"
    assert finding.label == "an AWS access key id"


def test_a_github_token_is_found_wherever_it_sits() -> None:
    text = f"the token is {GITHUB} and it should not be here"
    (finding,) = SignatureScreener().screen(text)
    assert finding.span.slice(text) == GITHUB


def test_a_prefix_that_is_too_short_to_be_the_thing_is_not_a_finding() -> None:
    """`ghp_` in prose is not a token, and stopping a run for it would be the
    behaviour ADR-0017 exists to avoid."""
    assert SignatureScreener().screen("the ghp_ prefix marks a classic token") == []


# Assembled rather than written out. `detect-private-key` in
# .pre-commit-config.yaml fires on the literal, which is ADR-0017's stated
# collision -- "a PEM header in a document about PEM headers stops the run" --
# arriving in musubi's own test suite on the day the screener was written.
# Excluding this file from the hook would disarm it for every future test here;
# assembling the string leaves it armed, and the screener sees exactly the same
# characters either way.
PEM_HEADER = "-----BEGIN " + "OPENSSH PRIVATE" + " KEY-----"


def test_a_pem_header_names_itself() -> None:
    (finding,) = SignatureScreener().screen(f"{PEM_HEADER}\nabc")
    assert finding.rule == "key.pem-private"


def test_a_test_key_is_not_a_live_key() -> None:
    """Stripe's live prefix is the point. `sk_test_` is not in the pack."""
    assert SignatureScreener().screen("sk_test_" + "a" * 24) == []
    assert len(SignatureScreener().screen("sk_live_" + "a" * 24)) == 1


def test_several_credentials_are_reported_in_the_order_they_appear() -> None:
    text = f"{GITHUB} then {AWS}"
    found = SignatureScreener().screen(text)
    assert [f.rule for f in found] == ["github.pat-classic", "aws.access-key"]


def test_a_clean_document_is_clean() -> None:
    assert SignatureScreener().screen("the tent weighs 2.4kg and cost 45,000 yen") == []


def test_an_empty_document_is_clean() -> None:
    assert SignatureScreener().screen("") == []


def test_a_slack_webhook_is_a_credential() -> None:
    url = "https://hooks.slack.com/services/T00000000/B00000000/abcdefghijklmnopqrst"
    (finding,) = SignatureScreener().screen(url)
    assert finding.rule == "slack.webhook"


def test_the_same_token_twice_is_two_findings() -> None:
    found = SignatureScreener().screen(f"{GITHUB} and again {GITHUB}")
    assert len(found) == 2
    assert found[0].matched_hash == found[1].matched_hash


# -- what a finding says ----------------------------------------------------


def test_a_finding_carries_a_hash_and_never_the_value() -> None:
    """The run stops so the secret does not travel. An error message quoting it
    would send it to a log file instead of a corpus, which is not an
    improvement."""
    (finding,) = SignatureScreener().screen(f"key: {ANTHROPIC}")
    assert finding.matched_hash == content_hash(ANTHROPIC)
    written = [getattr(finding, field.name) for field in fields(finding)]
    assert not any(ANTHROPIC in str(value) for value in written)


def test_a_finding_describes_itself_without_naming_the_secret() -> None:
    (finding,) = SignatureScreener().screen(f"key: {ANTHROPIC}")
    line = finding.describe("notes/setup.md")
    assert "an Anthropic API key" in line
    assert "notes/setup.md" in line
    assert ANTHROPIC not in line


# -- the pack ---------------------------------------------------------------


def test_every_signature_states_its_evidence_and_when_it_was_reviewed() -> None:
    assert SIGNATURES, "no signatures; this test would pass without reading one"
    for signature in SIGNATURES:
        assert signature.evidence, f"{signature.id} has no evidence"
        assert signature.since, f"{signature.id} has no review date"
        assert signature.label, f"{signature.id} has no label"


def test_a_screener_can_be_given_a_narrower_pack() -> None:
    """Which is how a source with its own vendor gets one added without a
    musubi release, and how a test names exactly what it is testing."""
    only_aws = SignatureScreener([s for s in SIGNATURES if s.id == "aws.access-key"])
    assert [s.id for s in only_aws.signatures] == ["aws.access-key"]
    assert only_aws.screen(GITHUB) == []
    assert len(only_aws.screen(AWS)) == 1


def test_signature_ids_are_unique() -> None:
    ids = [s.id for s in SIGNATURES]
    assert len(ids) == len(set(ids))


def test_a_signature_needs_a_prefix() -> None:
    """Without one it is an entropy filter wearing a signature's clothes, and
    ADR-0017 is the whole argument for keeping those apart."""
    with pytest.raises(ValueError, match="no prefix"):
        Signature(
            id="x",
            label="l",
            prefix="",
            alphabet=BASE62,
            minimum=8,
            evidence="e",
            since="2026-08-30",
        )


def test_a_signature_needs_a_label_somebody_can_act_on() -> None:
    with pytest.raises(ValueError, match="no label"):
        Signature(
            id="x",
            label="",
            prefix="p",
            alphabet=BASE62,
            minimum=8,
            evidence="e",
            since="2026-08-30",
        )


def test_a_signature_that_expects_a_body_must_allow_some_characters() -> None:
    with pytest.raises(ValueError, match="allows no characters"):
        Signature(
            id="x",
            label="l",
            prefix="p",
            alphabet=frozenset(),
            minimum=8,
            evidence="e",
            since="2026-08-30",
        )


def test_a_signature_must_state_its_evidence_and_review_date() -> None:
    with pytest.raises(ValueError, match="evidence"):
        Signature(
            id="x",
            label="l",
            prefix="p",
            alphabet=BASE62,
            minimum=1,
            evidence="",
            since="2026-08-30",
        )
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        Signature(
            id="x", label="l", prefix="p", alphabet=BASE62, minimum=1, evidence="e", since="soon"
        )


def test_a_signature_with_a_negative_minimum_is_refused() -> None:
    with pytest.raises(ValueError, match="negative"):
        Signature(
            id="x",
            label="l",
            prefix="p",
            alphabet=BASE62,
            minimum=-1,
            evidence="e",
            since="2026-08-30",
        )


def test_a_signature_with_no_id_is_refused() -> None:
    with pytest.raises(ValueError, match="no id"):
        Signature(
            id="",
            label="l",
            prefix="p",
            alphabet=BASE62,
            minimum=1,
            evidence="e",
            since="2026-08-30",
        )


# -- entropy, which is not the default --------------------------------------


def test_entropy_is_off_unless_it_is_asked_for() -> None:
    assert isinstance(default_screener(), SignatureScreener)
    assert isinstance(default_screener(entropy=True), CompositeScreener)


def test_the_entropy_tier_publishes_what_it_is_worth() -> None:
    """A measurement that stays in the documentation is one nobody reads at the
    moment it matters."""
    described = EntropyScreener().describe()
    assert "21.1%" in described
    assert "70.4%" in described


def test_the_entropy_tier_finds_what_a_signature_cannot() -> None:
    found = EntropyScreener().screen("password = 'Xk92mQ7vLp3RtY8wZn4Bc6Hd1Jf5Gs0A'")
    assert [f.rule for f in found] == ["entropy.base64"]


def test_the_entropy_tier_leaves_ordinary_prose_alone() -> None:
    assert EntropyScreener().screen("the tent weighs 2.4kg and we walked to the station") == []


def test_a_short_random_run_is_below_the_length_floor() -> None:
    assert EntropyScreener().screen("id=Xk92mQ7v") == []


def test_a_long_hex_run_is_found_as_hex() -> None:
    found = EntropyScreener().screen("digest 3f8a9c2e7b1d4056af83c92e6b1d40573f8a9c2e")
    assert [f.rule for f in found] == ["entropy.hex"]


def test_shannon_entropy_of_nothing_is_zero() -> None:
    assert shannon_entropy("") == 0.0


def test_shannon_entropy_of_one_repeated_character_is_zero() -> None:
    assert shannon_entropy("aaaaaaaa") == 0.0


def test_shannon_entropy_counts_bits_per_character() -> None:
    assert shannon_entropy("abcd" * 4) == pytest.approx(2.0)


# -- composing --------------------------------------------------------------


def test_a_composite_reports_every_tier_in_one_ordered_list() -> None:
    text = f"{GITHUB} and password = 'Xk92mQ7vLp3RtY8wZn4Bc6Hd1Jf5Gs0A'"
    found = default_screener(entropy=True).screen(text)
    assert [f.rule for f in found] == ["github.pat-classic", "entropy.base64"]


def test_a_composite_with_no_tiers_is_refused() -> None:
    """Fail closed. A screener that screens nothing would let a run proceed
    unscreened while looking like it had been checked (ADR-0008)."""
    with pytest.raises(ValueError, match="screen nothing"):
        CompositeScreener()


def test_the_screener_names_itself_for_the_manifest() -> None:
    assert default_screener().name.startswith("signatures@")
    assert "entropy@1" in default_screener(entropy=True).name


def test_the_default_screener_satisfies_the_port() -> None:
    screener: Screener = default_screener()
    assert screener.screen("") == []


# -- the invariants ---------------------------------------------------------


@given(st.text(max_size=200))
def test_screening_never_reports_a_span_outside_the_text(text: str) -> None:
    for finding in default_screener(entropy=True).screen(text):
        assert finding.span.end <= len(text)
        assert finding.matched_characters == finding.span.length


@given(st.text(max_size=200))
def test_screening_is_deterministic(text: str) -> None:
    screener = default_screener(entropy=True)
    assert screener.screen(text) == screener.screen(text)


@given(st.text(alphabet="abc ", max_size=60), st.text(alphabet="abc ", max_size=60))
def test_a_token_is_found_wherever_it_is_put(before: str, after: str) -> None:
    text = f"{before} {AWS} {after}"
    found = SignatureScreener().screen(text)
    assert any(f.rule == "aws.access-key" for f in found)


def test_a_finding_can_be_built_directly() -> None:
    finding = Finding.of("r", "a thing", Span(0, 3), "abc")
    assert finding.matched_characters == 3
    assert finding.matched_hash == content_hash("abc")
