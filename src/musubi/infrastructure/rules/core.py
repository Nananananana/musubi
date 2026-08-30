"""The core ruleset: what musubi takes out of a URL, and why it is allowed to.

Data, not code ([ADR-0009]). Adding a source's quirks is an entry here and a
fixture, never a branch in the cleanser.

## Where this came from

Derived on 2026-08-30 from the **ClearURLs** rule catalogue's global rules
(<https://github.com/ClearURLs/Rules>, `data.min.json`, `globalRules`), which is
the publicly maintained answer to *what is a tracking parameter*. Borrowing a
catalogue somebody else maintains is right; pretending it was ours is not.

The catalogue is written as regular expressions. musubi's rules are exact
matches and prefixes ([ADR-0016]), so each entry below names the catalogue
pattern it came from in its evidence. Almost every one was already a literal or
a prefix wearing regex notation; the small alternations became several rules,
which is longer to read and individually attributable when one of them turns out
to be wrong.

## What was deliberately left out

`[a-z]?mc` -- strips `mc` and every single letter followed by `mc`, so `amc`,
`bmc` and twenty-four others. Tolerable in a browser; in a corpus it silently
changes a link in somebody's notes. ADR-0016 records the decision.

`(?:%3F)?` prefixes -- they exist to catch doubly-encoded URLs in an address
bar. musubi parses the query structurally and has no equivalent problem.

## Staleness

The tail of tracking parameters is long and growing, and a vendored catalogue
lags its upstream permanently. Every rule carries `since`, so the lag is
measurable instead of invisible.
"""

from __future__ import annotations

from ...domain.removal import Match, Rule, Ruleset

__all__ = ["CORE", "VERSION"]

VERSION = "2026.08"

_REVIEWED = "2026-08-30"


def _exact(rule_id: str, value: str, evidence: str, kind: str = "tracking_parameter") -> Rule:
    return Rule(
        id=rule_id,
        kind=kind,
        match=Match.EXACT,
        value=value,
        evidence=evidence,
        since=_REVIEWED,
    )


def _prefix(rule_id: str, value: str, evidence: str, kind: str = "tracking_parameter") -> Rule:
    return Rule(
        id=rule_id,
        kind=kind,
        match=Match.PREFIX,
        value=value,
        evidence=evidence,
        since=_REVIEWED,
    )


_CLEARURLS = "ClearURLs globalRules"

CORE = Ruleset(
    id="core",
    version=VERSION,
    rules=(
        # -- campaign tagging ------------------------------------------------
        _exact("tracking.utm", "utm", f"Urchin campaign tag, bare; {_CLEARURLS} `utm(?:_…)?`"),
        _prefix(
            "tracking.utm-family",
            "utm_",
            f"Google Analytics campaign parameters; {_CLEARURLS} `utm(?:_[a-z_]*)?`",
        ),
        _exact("tracking.mtm", "mtm", f"Matomo campaign tag, bare; {_CLEARURLS} `mtm(?:_…)?`"),
        _prefix(
            "tracking.mtm-family",
            "mtm_",
            f"Matomo campaign parameters; {_CLEARURLS} `mtm(?:_[a-z_]*)?`",
        ),
        _prefix("tracking.ga", "ga_", f"Google Analytics; {_CLEARURLS} `ga_[a-z_]+`"),
        _prefix("tracking.otm", "otm_", f"Omniture campaign; {_CLEARURLS} `otm_[a-z_]*`"),
        _prefix("tracking.vn", "vn_", f"Vero campaign; {_CLEARURLS} `vn(?:_[a-z]*)+`"),
        _exact("tracking.itm-campaign", "itm_campaign", f"{_CLEARURLS} `itm_(?:campaign|…)`"),
        _exact("tracking.itm-medium", "itm_medium", f"{_CLEARURLS} `itm_(?:…|medium|…)`"),
        _exact("tracking.itm-source", "itm_source", f"{_CLEARURLS} `itm_(?:…|source)`"),
        _exact("tracking.hmb-campaign", "hmb_campaign", f"{_CLEARURLS} `hmb_(?:campaign|…)`"),
        _exact("tracking.hmb-medium", "hmb_medium", f"{_CLEARURLS} `hmb_(?:…|medium|…)`"),
        _exact("tracking.hmb-source", "hmb_source", f"{_CLEARURLS} `hmb_(?:…|source)`"),
        _exact("tracking.cmpid", "cmpid", f"Generic campaign id; {_CLEARURLS} `cmpid`"),
        _exact("tracking.s-cid", "s_cid", f"Adobe/Omniture campaign id; {_CLEARURLS} `s_cid`"),
        _exact("tracking.spm", "spm", f"Alibaba super position model; {_CLEARURLS} `spm`"),
        # -- click identifiers -----------------------------------------------
        _exact("tracking.gclid", "gclid", f"Google Ads click id; {_CLEARURLS} `gclid`"),
        _exact("tracking.dclid", "dclid", f"DoubleClick click id; {_CLEARURLS} `dclid`"),
        _exact("tracking.srsltid", "srsltid", f"Google Shopping click id; {_CLEARURLS} `srsltid`"),
        _exact("tracking.fbclid", "fbclid", f"Facebook click id; {_CLEARURLS} `fbclid`"),
        _exact("tracking.msclkid", "msclkid", f"Microsoft Ads click id; {_CLEARURLS} `msclkid`"),
        _exact("tracking.twclid", "twclid", f"X/Twitter click id; {_CLEARURLS} `twclid`"),
        _exact("tracking.yclid", "yclid", f"Yandex click id; {_CLEARURLS} `yclid`"),
        _exact("tracking.wickedid", "wickedid", f"Wicked Reports id; {_CLEARURLS} `wickedid`"),
        _exact("tracking.rb-clickid", "rb_clickid", f"{_CLEARURLS} `rb_clickid`"),
        # -- per-recipient identifiers, which are the worst of them -----------
        _exact(
            "tracking.mc-eid",
            "mc_eid",
            f"Mailchimp *per-subscriber* id -- identifies the reader, not the campaign; "
            f"{_CLEARURLS} `mc_(?:eid|cid|tc)`",
        ),
        _exact("tracking.mc-cid", "mc_cid", f"Mailchimp campaign id; {_CLEARURLS} `mc_(?:…)`"),
        _exact("tracking.mc-tc", "mc_tc", f"Mailchimp tracking; {_CLEARURLS} `mc_(?:…)`"),
        _exact(
            "tracking.ml-subscriber",
            "ml_subscriber",
            f"MailerLite subscriber id; {_CLEARURLS} `ml_subscriber`",
        ),
        _exact(
            "tracking.ml-subscriber-hash",
            "ml_subscriber_hash",
            f"MailerLite subscriber hash; {_CLEARURLS} `ml_subscriber_hash`",
        ),
        _exact("tracking.vero-id", "vero_id", f"Vero recipient id; {_CLEARURLS} `vero_id`"),
        _exact("tracking.vero-conv", "vero_conv", f"Vero conversion; {_CLEARURLS} `vero_conv`"),
        _exact("tracking.oly-anon-id", "oly_anon_id", f"Omeda; {_CLEARURLS} `oly_anon_id`"),
        _exact("tracking.oly-enc-id", "oly_enc_id", f"Omeda; {_CLEARURLS} `oly_enc_id`"),
        _exact("tracking.os-ehash", "os_ehash", f"Hashed email address; {_CLEARURLS} `os_ehash`"),
        _exact("tracking.mkt-tok", "mkt_tok", f"Marketo recipient token; {_CLEARURLS} `mkt_tok`"),
        # -- analytics session state -----------------------------------------
        _exact("tracking.ga-cookie", "_ga", f"Google Analytics client id; {_CLEARURLS} `_ga`"),
        _exact("tracking.gl", "_gl", f"Google cross-domain linker; {_CLEARURLS} `_gl`"),
        _exact("tracking.hsenc", "_hsenc", f"HubSpot; {_CLEARURLS} `_hsenc`"),
        _exact("tracking.hsfp", "__hsfp", f"HubSpot fingerprint; {_CLEARURLS} `__hsfp`"),
        _exact("tracking.hssc", "__hssc", f"HubSpot session; {_CLEARURLS} `__hssc`"),
        _exact("tracking.hstc", "__hstc", f"HubSpot visitor; {_CLEARURLS} `__hstc`"),
        _exact("tracking.hs-cta", "hsCtaTracking", f"HubSpot CTA; {_CLEARURLS} `hsCtaTracking`"),
        _exact("tracking.drip", "__s", f"Drip per-subscriber id; {_CLEARURLS} `__s`"),
        _exact("tracking.openstat", "_openstat", f"Openstat; {_CLEARURLS} `_openstat`"),
        _exact("tracking.echobox", "Echobox", f"Echobox; {_CLEARURLS} `Echobox`"),
        _exact("tracking.gs-l", "gs_l", f"Google search state; {_CLEARURLS} `gs_l`"),
        _exact("tracking.wtrid", "wtrid", f"Webtrekk; {_CLEARURLS} `wtrid`"),
        _exact("tracking.wt-mc", "wt_mc", f"Webtrekk media code; {_CLEARURLS} `wt_?z?mc`"),
        _exact("tracking.wtmc", "wtmc", f"Webtrekk media code; {_CLEARURLS} `wt_?z?mc`"),
        _exact("tracking.wt-zmc", "wt_zmc", f"Webtrekk media code; {_CLEARURLS} `wt_?z?mc`"),
        _exact("tracking.wtzmc", "wtzmc", f"Webtrekk media code; {_CLEARURLS} `wt_?z?mc`"),
        _exact("tracking.ceneo-spo", "ceneo_spo", f"Ceneo; {_CLEARURLS} `ceneo_spo`"),
        _exact("tracking.tracking-source", "tracking_source", f"{_CLEARURLS} `tracking_source`"),
        # -- social scaffolding ----------------------------------------------
        _exact("tracking.fb-source", "fb_source", f"{_CLEARURLS} `fb_(?:source|ref)`"),
        _exact("tracking.fb-ref", "fb_ref", f"{_CLEARURLS} `fb_(?:source|ref)`"),
        _exact("tracking.fb-action-types", "fb_action_types", f"{_CLEARURLS} `fb_action_(?:…)`"),
        _exact("tracking.fb-action-ids", "fb_action_ids", f"{_CLEARURLS} `fb_action_(?:…)`"),
        _exact("tracking.action-object-map", "action_object_map", f"{_CLEARURLS} `action_…_map`"),
        _exact("tracking.action-type-map", "action_type_map", f"{_CLEARURLS} `action_…_map`"),
        _exact("tracking.action-ref-map", "action_ref_map", f"{_CLEARURLS} `action_…_map`"),
        _exact(
            "tracking.twitter-impression",
            "__twitter_impression",
            f"{_CLEARURLS} `__twitter_impression`",
        ),
        # -- referral marketing ----------------------------------------------
        # A separate kind, because these are the arguable ones: an affiliate tag
        # is a tracking identifier and is also sometimes what somebody meant to
        # save. Kept in the default pack, kept nameable on its own so that a
        # future flag can spare them and `musubi rules --list` shows them apart.
        _exact(
            "referral.ref",
            "ref",
            f"Referral attribution; {_CLEARURLS} referralMarketing `ref_?`",
            kind="referral_marketing",
        ),
        _exact(
            "referral.ref-underscore",
            "ref_",
            f"Referral attribution; {_CLEARURLS} referralMarketing `ref_?`",
            kind="referral_marketing",
        ),
        _exact(
            "referral.referrer",
            "referrer",
            f"Referral attribution; {_CLEARURLS} referralMarketing `referrer`",
            kind="referral_marketing",
        ),
    ),
)
