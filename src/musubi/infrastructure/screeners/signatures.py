"""The signature pack: credential formats their own issuers made recognisable.

Data, not code, exactly as a cleansing rule pack is ([ADR-0009]). Adding a
vendor is an entry here and a fixture.

## Why this is the default tier and entropy is not

[ADR-0017]. Entropy-only detection scores 21.1% precision on the CredData
benchmark, and under a stop-the-run policy four false stops in five would make
`--allow` reflexive inside a week. A prefix plus an alphabet plus a length has
precision near one *by construction*, because the issuer designed the prefix to
be recognisable -- GitHub's secret-scanning partner programme has spent five
years pushing the industry into exactly this shape, and twenty-eight new
detectors from fifteen providers landed in March 2026 alone.

## Reviewed 2026-08

Formats current as of the date on each entry. This list goes stale faster than
the tracking-parameter pack, because vendors rotate token formats and new
vendors appear monthly; `since` makes the lag measurable rather than invisible.

## What is deliberately not here

A bare JWT below a hundred characters. `eyJ` is only `{"` in base64, so a short
one is indistinguishable from any base64-encoded JSON, and a false stop costs
more than a missed short token under ADR-0008.

Anything whose shape is "a long random string". That is the entropy tier's job,
it is opt-in, and it says what it is worth where it is switched on.
"""

from __future__ import annotations

from ...domain.screening import BASE32, BASE62, BASE64URL, Signature

__all__ = ["SIGNATURES", "VERSION"]

VERSION = "2026.08"

_REVIEWED = "2026-08-30"


def _sig(
    rule_id: str,
    label: str,
    prefix: str,
    alphabet: frozenset[str],
    minimum: int,
    evidence: str,
) -> Signature:
    return Signature(
        id=rule_id,
        label=label,
        prefix=prefix,
        alphabet=alphabet,
        minimum=minimum,
        evidence=evidence,
        since=_REVIEWED,
    )


_PEM = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ -")

SIGNATURES: tuple[Signature, ...] = (
    # -- GitHub, whose prefixes started the whole convention -----------------
    _sig(
        "github.pat-classic",
        "a GitHub personal access token",
        "ghp_",
        BASE62,
        36,
        "GitHub classic PAT: ghp_ plus 36 base62. Identifiable by design, for the "
        "secret-scanning partner programme.",
    ),
    _sig("github.oauth", "a GitHub OAuth token", "gho_", BASE62, 36, "GitHub OAuth access token."),
    _sig(
        "github.user-to-server",
        "a GitHub user-to-server token",
        "ghu_",
        BASE62,
        36,
        "GitHub App user-to-server token.",
    ),
    _sig(
        "github.server-to-server",
        "a GitHub server-to-server token",
        "ghs_",
        BASE62,
        36,
        "GitHub App installation token.",
    ),
    _sig(
        "github.refresh",
        "a GitHub refresh token",
        "ghr_",
        BASE62,
        36,
        "GitHub App refresh token.",
    ),
    _sig(
        "github.pat-fine-grained",
        "a GitHub fine-grained personal access token",
        "github_pat_",
        BASE62 | frozenset("_"),
        70,
        "GitHub fine-grained PAT: github_pat_ plus a long base62 body containing an underscore.",
    ),
    # -- cloud ---------------------------------------------------------------
    _sig(
        "aws.access-key",
        "an AWS access key id",
        "AKIA",
        BASE32,
        16,
        "AWS long-term access key id: AKIA plus 16 uppercase alphanumerics.",
    ),
    _sig(
        "aws.session-key",
        "an AWS session access key id",
        "ASIA",
        BASE32,
        16,
        "AWS temporary session credentials, same shape as AKIA.",
    ),
    _sig(
        "google.api-key",
        "a Google API key",
        "AIza",
        BASE64URL,
        35,
        "Google API key: AIza plus 35 characters of base64url.",
    ),
    # -- model providers, which is what musubi's output is aimed at ----------
    _sig(
        "anthropic.api-key",
        "an Anthropic API key",
        "sk-ant-",
        BASE64URL,
        80,
        "Anthropic API key: sk-ant-api03- plus a long base64url body.",
    ),
    _sig(
        "openai.project-key",
        "an OpenAI project API key",
        "sk-proj-",
        BASE64URL,
        40,
        "OpenAI project-scoped key.",
    ),
    # -- messaging and mail --------------------------------------------------
    _sig(
        "slack.bot-token",
        "a Slack bot token",
        "xoxb-",
        BASE62 | frozenset("-"),
        20,
        "Slack bot token. Relevant here beyond the usual: a Slack export is one of "
        "the formats musubi reads, and the token that produced it often sits in the "
        "same folder.",
    ),
    _sig("slack.user-token", "a Slack user token", "xoxp-", BASE62 | frozenset("-"), 20, "Slack."),
    _sig("slack.app-token", "a Slack app token", "xapp-", BASE62 | frozenset("-"), 20, "Slack."),
    _sig(
        "slack.webhook",
        "a Slack incoming webhook",
        "https://hooks.slack.com/services/",
        BASE62 | frozenset("/"),
        20,
        "A Slack webhook URL is a credential: anybody holding it can post as the app.",
    ),
    _sig(
        "sendgrid.key",
        "a SendGrid API key",
        "SG.",
        BASE64URL | frozenset("."),
        60,
        "SendGrid: SG. plus two dot-separated base64url segments.",
    ),
    # -- payments and packages ----------------------------------------------
    _sig(
        "stripe.live-secret",
        "a live Stripe secret key",
        "sk_live_",
        BASE62,
        24,
        "Stripe live secret key. The live prefix is the point: sk_test_ is not here.",
    ),
    _sig(
        "stripe.live-restricted",
        "a live Stripe restricted key",
        "rk_live_",
        BASE62,
        24,
        "Stripe live restricted key.",
    ),
    _sig("npm.token", "an npm access token", "npm_", BASE62, 36, "npm automation/publish token."),
    _sig(
        "pypi.token",
        "a PyPI API token",
        "pypi-AgEIcHlwaS5vcmc",
        BASE64URL,
        40,
        "PyPI token: the prefix is a base64 macaroon header identifying pypi.org.",
    ),
    # -- private keys, which name themselves ---------------------------------
    _sig(
        "key.pem-private",
        "a private key block",
        "-----BEGIN ",
        _PEM,
        0,
        "A PEM header. The prefix is the finding: RSA, EC, OPENSSH, PGP and plain "
        "PRIVATE KEY all announce themselves this way, and a document that contains "
        "one is worth stopping for even when it turns out to be an explanation.",
    ),
)
