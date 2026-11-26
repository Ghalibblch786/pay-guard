"""Tests for part_b/sanitizer.py (PII REDACTION). SYNTHETIC text only: every string below is invented; no real complaint text is used."""
import re

import pytest

from part_b.sanitizer import PLACEHOLDERS, SanitizerError, load_nlp, sanitize, try_sanitize


@pytest.fixture(scope="module")
def nlp():
    return load_nlp()


def clean(text, nlp=None):
    return sanitize(text, nlp=nlp).text


# ---------- positives: each identifier type and several formats; the canary must not survive ----------
EMAILS = ["jane.doe@example.com", "j_doe+bank@mail.example.org", "JANE@EXAMPLE.CO.UK", "jane dot doe at example dot com".replace("jane dot doe", "janedoe")]
PHONES = ["(555) 123-4567", "555-123-4567", "555.123.4567", "555 123 4567", "+1 555 123 4567", "1-555-123-4567", "+44 20 7946 0958"]
URLS = ["https://pay.example.com/login?id=1", "http://example.org/a/b", "www.example-bank.com/help", "example-bank.com", "https://bit.example.io/xYz"]
SSNS = ["123-45-6789", "987-65-4321"]
CARDS = ["4111 1111 1111 1111", "4111-1111-1111-1111", "4111111111111111", "5500 0000 0000 0004", "3782 822463 10005"]
ACCTS = ["0123456789", "000123456789012", "021000021", "12345678"]
ZIPS = ["90210-1234"]
DATES = ["03/14/2026", "3/4/26", "2026-03-14", "XX/XX/2026", "03/XX/XXXX", "March 3, 2026", "Mar 3rd", "3rd of March 2026", "14 March 2026", "XX/XX/XXXX"]
ADDRESSES = ["123 Main Street", "4567 Oak Ave Apt 12", "89 N. Elm Boulevard, Suite 200", "P.O. Box 4455", "1200 Sunset Blvd #4B"]


@pytest.mark.parametrize("canary", EMAILS)
def test_email_removed(canary):
    out = clean(f"Please write to {canary} about this.")
    assert canary not in out and "[EMAIL]" in out


@pytest.mark.parametrize("canary", PHONES)
def test_phone_removed(canary):
    out = clean(f"Call me on {canary} please.")
    assert canary not in out and "[PHONE]" in out and not re.search(r"\d{3}", out)


@pytest.mark.parametrize("canary", URLS)
def test_url_removed(canary):
    out = clean(f"I followed the link {canary} and entered details.")
    assert canary not in out and "[URL]" in out


@pytest.mark.parametrize("canary", SSNS + CARDS + ACCTS)
def test_number_ids_removed(canary):
    out = clean(f"The number {canary} was on the statement.")
    assert canary not in out and "[NUMBER_ID]" in out


@pytest.mark.parametrize("canary", ZIPS)
def test_zip4_removed(canary):
    assert canary not in clean(f"Mailed to the area {canary} yesterday.")


@pytest.mark.parametrize("text", ["my zip code is 78701 and", "I live in Austin TX 78701 near", "ZIP: 78701"])
def test_zip_with_context_removed(text):
    assert "78701" not in clean(text)


@pytest.mark.parametrize("canary", DATES)
def test_dates_removed(canary):
    out = clean(f"The charge posted on {canary} without my approval.")
    assert "[DATE]" in out and not re.search(r"\b2026\b|\b03/", out.replace("[DATE]", ""))


@pytest.mark.parametrize("canary", ADDRESSES)
def test_address_removed(canary):
    out = clean(f"The card was mailed to {canary} last week.")
    assert canary not in out and "[ADDRESS]" in out


@pytest.mark.parametrize("text,last4", [("card ending in 4821 was used", "4821"), ("account ending with x1234", "1234"), ("last 4 digits 9876 on the card", "9876"),
                                         ("card XXXX1234 was lost", "1234"), ("card ****5678 was lost", "5678"), ("acct XXXX XXXX XXXX 4321", "4321"), ("last four of the account is 1357", "1357")])
def test_last4_removed(text, last4):
    out = clean(text)
    assert last4 not in out and "[LAST4]" in out


def test_name_cues():
    assert "Maria" not in clean("Hello, my name is Maria Lopez. Please help.") and "Please help" in clean("Hello, my name is Maria Lopez. Please help.")
    assert "Smith" not in clean("I spoke to Mr. Smith at the branch.")
    assert "Johnson" not in clean("Thank you.\nSincerely,\nAlex Johnson")
    assert "Acme Payroll" not in clean("I work for Acme Payroll and my pay was held.") and "[EMPLOYER]" in clean("I work for Acme Payroll and my pay was held.")


def test_cfpb_tokens():
    out = clean("On XXXX I paid XXXX XXXX and XXXX never arrived.")
    assert "XXXX" not in out and out.count("[REDACTED]") >= 2 and "[REDACTED] [REDACTED]" not in out


# ---------- negatives: signal that must survive ----------
@pytest.mark.parametrize("keep", ["$1,200.00", "{$150.00}", "$20", "50%", "3 weeks", "10:30 am", "2026", "May 2026", "1,234,567", "150000 dollars", "$500000", "Zelle", "PayPal", "Chase", "Visa", "Wells Fargo"])
def test_signal_preserved(keep):
    out = clean(f"They took {keep} from the Zelle transfer and Chase did nothing.") if keep not in ("Zelle", "PayPal", "Chase", "Visa", "Wells Fargo") else clean(f"I had a problem with {keep} yesterday.")
    assert keep in out, out


def test_critical_words_survive():
    text = "This is fraud: an unauthorized charge, a scam, and I want a refund or I will contact my attorney about a lawsuit."
    out = clean(text)
    for w in ["fraud", "unauthorized", "scam", "refund", "attorney", "lawsuit"]:
        assert w in out


# ---------- NER layer (local spaCy) ----------
NER_CASES = [("Yesterday Maria Lopez told me the account was frozen.", "Maria"), ("My wife Priya Natarajan opened the account.", "Natarajan"),
             ("The branch manager, Robert Chen, refused to help.", "Chen"), ("Then Sofia Martinez called me back.", "Martinez"),
             ("I met Daniel Okafor at the bank.", "Okafor"), ("Linda Nguyen sent the wire.", "Nguyen"), ("Agent Thomas Becker closed my case.", "Becker"),
             ("My brother Carlos Mendes used my card.", "Mendes"), ("Ahmed Hassan emailed the receipt.", "Hassan"), ("A rep named Julia Kowalski answered.", "Kowalski")]


def test_ner_redacts_most_synthetic_names(nlp):
    hit = sum(1 for text, surname in NER_CASES if surname not in clean(text, nlp))
    assert hit >= 7, f"NER removed only {hit}/{len(NER_CASES)} synthetic names (this is a smoke check, not a guarantee)"


def test_ner_locations_and_protected_brands(nlp):
    out = clean("I live in Austin, Texas and sent money to Lagos but Zelle and Chase and Wells Fargo ignored me.", nlp)
    assert "Austin" not in out and "Texas" not in out and "[LOCATION]" in out
    for brand in ["Zelle", "Chase", "Wells Fargo"]:
        assert brand in out


# ---------- invariants ----------
ALL_SAMPLES = ([f"Reach me at {e} today." for e in EMAILS] + [f"Call {p} now" for p in PHONES] + [f"See {u}" for u in URLS] + [f"Card {c} used" for c in CARDS]
               + [f"Paid on {d}." for d in DATES] + [f"Send to {a}." for a in ADDRESSES] + ["card ending in 4821", "Hello, my name is Maria Lopez. Please help."]
               + ["Plain text with nothing to redact $12.50 and 3 days."])


@pytest.mark.parametrize("text", ALL_SAMPLES)
def test_idempotent_and_deterministic(text, nlp):
    a = sanitize(text, nlp=nlp).text
    assert sanitize(text, nlp=nlp).text == a
    assert sanitize(a, nlp=nlp).text == a


def test_only_known_placeholders_introduced():
    for text in ALL_SAMPLES:
        for ph in set(re.findall(r"\[[A-Z0-9_]+\]", clean(text))):
            assert ph in PLACEHOLDERS


def test_edge_cases(nlp):
    assert clean("") == "" and clean("   \n  ") == ""
    assert clean("plain text") == "plain text"
    long_ok = "word " * 20_000
    assert sanitize(long_ok).text
    with pytest.raises(SanitizerError):
        sanitize("x" * 200_000)
    with pytest.raises(SanitizerError):
        sanitize(None)


def test_fail_closed_wrapper():
    assert try_sanitize(None) is None and try_sanitize("x" * 200_000) is None and try_sanitize("ok text") is not None


def test_counts_contain_no_text():
    r = sanitize("Mail jane@example.com or call 555-123-4567.")
    assert r.counts == {"[EMAIL]": 1, "[PHONE]": 1}


def test_canary_injection_across_templates(nlp):
    """Inject synthetic canaries into synthetic narrative templates; none may survive."""
    templates = ["I was charged twice and {c} was on the receipt.", "Support asked for {c} and then closed my account.", "{c} -- this is what I gave them before the money vanished."]
    canaries = ["jane.doe@example.com", "(555) 123-4567", "4111 1111 1111 1111", "123-45-6789", "https://phish.example.net/a", "021000021", "123 Main Street"]
    for t in templates:
        for c in canaries:
            assert c not in clean(t.format(c=c), nlp), (t, c)


# ---------- regression tests for gaps found by adversarial synthetic probing ----------
@pytest.mark.parametrize("text,gone", [
    ("reference #A123456789 was given", "A123456789"), ("IBAN GB82WEST12345698765432 was used", "GB82WEST12345698765432"),
    ("wallet 0x742d35Cc6634C0532925a3b844Bc454e4438f44e got it", "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"),
    ("Account 12345 was charged", "12345"), ("tracking number 1Z999AA10123456784 shows delivered", "1Z999AA10123456784"),
    ("email me: JOHN.SMITH(at)GMAIL.COM please", "GMAIL"), ("write to jane at example.com now", "jane at example.com"),
    ("Thanks.\nSincerely,\nmaria", "maria"),
])
def test_probe_gaps_fixed(text, gone):
    assert gone not in clean(text), clean(text)


@pytest.mark.parametrize("text", ["Payment of 250000 pesos was sent", "I lost 120000 euros in the scam", "They took €250000 from me", "refund of 90000 dollars is owed"])
def test_amounts_in_other_currencies_not_treated_as_ids(text):
    assert "[NUMBER_ID]" not in clean(text)


@pytest.mark.parametrize("text", ["Thank you very much", "Thanks so much", "thank you so much for nothing"])
def test_thanks_phrases_not_mistaken_for_names(text):
    assert "[PERSON]" not in clean(text)


def test_known_limitations_are_actual_limitations():
    """Documents what is NOT caught, so nobody mistakes this sanitizer for anonymization."""
    assert "dev patel" in clean("my cousin dev patel did the transfer")      # lowercase name without cue, no NER
    assert "3/14" in clean("it happened on 3/14 around noon")                # date without year
    assert "Elm Street" in clean("the branch on Elm Street refused")         # street name without a number
    assert "1234" in clean("card XXXX 1234 was used")                        # indistinguishable from a year


def test_edge_cases_unicode_does_not_crash(nlp):
    out = sanitize("Paid €50 😀 مرحبا مرحبا", nlp=nlp).text
    assert isinstance(out, str) and "€50" in out


@pytest.mark.parametrize("text,gone,kept", [
    ("my name is john smith and I need help", "smith", "and I need help"), ("My name is Maria J. Lopez, please call", "Lopez", "please call"),
    ("my name is priya and I was scammed", "priya", "and I was scammed"), ("MY NAME IS OMAR FAROUK. Thanks", "FAROUK", "Thanks"),
])
def test_my_name_is_cue_handles_case_and_function_words(text, gone, kept):
    out = clean(text)
    assert gone not in out and kept in out and "[PERSON]" in out, out
