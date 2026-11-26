"""Tests for part_b/sensitive_flags.py (SENSITIVE-CONTENT DETECTION: flags only, never rewrites). SYNTHETIC text only."""
import pytest

from part_b.sensitive_flags import CATEGORIES, detect_sensitive, is_sensitive_failclosed
from part_b.sanitizer import sanitize

POSITIVE = {
    "health_medical": ["I was in the hospital for surgery and could not pay.", "Because of my cancer diagnosis I missed the payment.", "My medication costs were charged to the card."],
    "minors": ["My son's account was opened without me.", "The custodial account for my daughter was frozen.", "My 15-year-old used the card.", "She is a minor."],
    "government_id": ["They asked for my social security number.", "I sent a copy of my driver's license.", "My passport was needed for the account."],
    "financial_account_details": ["I gave them my routing number and account number.", "The CVV was requested.", "They wanted my debit card number.", "I read out 021000021 and 123456789012 to the agent."],
    "credentials_authentication": ["I told the caller my password.", "They asked for the one-time code sent to my phone.", "My security answers were changed.", "I shared my PIN number.", "The verification code was texted."],
    "immigration_legal_case": ["My immigration case was affected.", "The court order froze the account.", "Case number 2026-CV-12345 is pending.", "A subpoena was issued."],
    "self_harm_safety": ["I felt like I wanted to end my life after losing the money.", "Domestic violence is why I closed the account.", "My stalker had access to the account."],
}
NEGATIVE = ["I was charged twice for the same purchase and want a refund.", "The transfer of $500 never arrived and support does not answer.", "My account was closed without notice.",
            "Zelle said the payment was sent but the recipient never received it.", "They charged a monthly fee of $15 that I never agreed to.", "I paid with my Visa card and the merchant did not deliver.",
            "I received a text and the money was taken by a scammer.", "The app froze when I tried to transfer money."]


@pytest.mark.parametrize("category,texts", POSITIVE.items())
def test_each_category_fires(category, texts):
    for t in texts:
        assert category in detect_sensitive(t).categories, (category, t)


@pytest.mark.parametrize("text", NEGATIVE)
def test_ordinary_complaints_not_flagged(text):
    assert not detect_sensitive(text).is_sensitive, text


def test_flagger_never_rewrites_and_returns_no_text():
    r = detect_sensitive("My password is hunter2 and my routing number is 021000021.")
    assert set(r.hits) <= set(CATEGORIES) and all(isinstance(v, int) for v in r.hits.values())
    assert "hunter2" not in repr(r) and "021000021" not in repr(r)


def test_flags_on_raw_text_see_evidence_that_redaction_conceals():
    raw = "They asked for my routing number 021000021 on the call."
    redacted = sanitize(raw).text
    assert "021000021" not in redacted               # the sanitizer concealed the digits ...
    assert "financial_account_details" in detect_sensitive(raw).categories   # ... the flagger on RAW text still flags it
    assert "financial_account_details" in detect_sensitive(redacted).categories  # and the cue words survive redaction here


def test_fail_closed():
    assert is_sensitive_failclosed(None) is True and is_sensitive_failclosed(12345) is True
    assert is_sensitive_failclosed("The app froze.") is False


def test_card_brand_visa_is_not_immigration():
    assert "immigration_legal_case" not in detect_sensitive("My Visa card was declined.").categories
