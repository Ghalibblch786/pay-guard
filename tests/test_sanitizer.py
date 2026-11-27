"""Tests for part_b/sanitizer.py (PII REDACTION). SYNTHETIC text only: every string below is invented; no real complaint text is used."""
import re

import pytest

from part_b.sanitizer import PLACEHOLDERS, SanitizerError, load_nlp, sanitize, try_sanitize


@pytest.fixture(scope="module")
def nlp():
    return load_nlp()


def clean(text, nlp=None, protected=None):
    return sanitize(text, nlp=nlp, protected=protected if protected is not None else set()).text


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
    # protected company names are supplied by the caller (Step 2 derives them from the export's public Company column)
    out = clean("I live in Austin, Texas and sent money to Lagos but Zelle and Chase and Wells Fargo ignored me.", nlp, protected={"chase", "wells fargo"})
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
    assert "1234" in clean("I sent XXXX 1234 to them")                       # masked digits without card/account wording
    assert "2031" in clean("my card 2031 was replaced")                      # year-like, no 'number' / 'ending' / '#'
    assert "4821" in clean("the card I used, 4821, was lost")                 # wording not adjacent to the digits


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


# ---------- D-27 fixes, tested with a deterministic stand-in for spaCy so the tests do not depend on what the model happens to tag ----------
import re as _re
import types


class FakeEnt:
    def __init__(self, text, label, start):
        self.text, self.label_, self.start_char, self.end_char = text, label, start, start + len(text)


class FakeNLP:
    """Entities come from a fixed {surface: label} table. `staged`: only the k-th surface is 'visible' once k [PERSON] placeholders exist
    (simulates a name that NER only sees after an earlier name was removed). `calls` counts NER passes."""
    def __init__(self, table, staged=None):
        self.table, self.staged, self.calls = table, staged, 0

    def __call__(self, text):
        self.calls += 1
        items = list(self.table.items())
        if self.staged:
            k = text.count("[PERSON]")
            items = [(self.staged[k], "PERSON")] if k < len(self.staged) else []
        ents = [FakeEnt(surface, label, m.start()) for surface, label in items for m in _re.finditer(_re.escape(surface), text)]
        return types.SimpleNamespace(ents=sorted(ents, key=lambda e: e.start_char))


def test_loose_email_rule_removed():
    out = clean("I looked at chase.com and then at paypal.com for help.")
    assert "[EMAIL]" not in out                                   # these are websites, not addresses (the old rule produced [EMAIL])
    assert "[EMAIL]" in clean("write to me at jane.doe@example.com")  # real addresses are still caught


@pytest.mark.parametrize("brand", ["Zelle", "Venmo", "Cash App", "Citi", "Visa", "Mastercard"])
def test_brand_allowlist_keeps_exact_brand_even_if_ner_tags_it(brand):
    nlp = FakeNLP({brand: "PERSON"})
    r = sanitize(f"My {brand} payment failed.", nlp=nlp)
    assert brand in r.text and "[PERSON]" not in r.text and r.ner_skips.get("brand_allowlist") == 1


def test_brand_allowlist_is_exact_not_broad():
    for surface in ["Visa Patel", "Citi Nguyen", "Venmo Johnson", "Zelles"]:
        out = sanitize(f"I spoke with {surface} yesterday.", nlp=FakeNLP({surface: "PERSON"})).text
        assert surface not in out and "[PERSON]" in out, surface
    assert "Zelle" in sanitize("Zelle's app froze.", nlp=FakeNLP({"Zelle's": "PERSON"})).text   # possessive of an exact brand is still the brand


def test_critical_terms_never_redacted_by_ner():
    nlp = FakeNLP({"Fraud Department": "PERSON", "Dana": "PERSON", "chargeback": "GPE", "Unauthorized Charges Team": "PERSON"})
    r = sanitize("Dana from the Fraud Department said the chargeback and the Unauthorized Charges Team could not help.", nlp=nlp)
    assert "Dana" not in r.text and "[PERSON]" in r.text
    for kept in ["Fraud Department", "chargeback", "Unauthorized Charges Team"]:
        assert kept in r.text
    assert r.ner_skips["critical_term"] == 3


def test_company_list_still_protects_names():
    r = sanitize("Acme Savings closed my account.", nlp=FakeNLP({"Acme Savings": "GPE"}), protected={"acme savings"})
    assert "Acme Savings" in r.text and r.ner_skips == {"company_list": 1}


def test_ner_second_pass_catches_entity_exposed_by_first_pass_and_stops_when_stable():
    nlp = FakeNLP({}, staged=["Dana", "Lee"])
    r = sanitize("Dana Lee called me back.", nlp=nlp)
    assert "Lee" not in r.text and "Dana" not in r.text and r.ner_passes == 2
    quiet = FakeNLP({"Nobody": "PERSON"})
    r2 = sanitize("Plain text with no entities.", nlp=quiet)
    assert r2.ner_passes == 1 and quiet.calls == 1          # stable after one pass: no second pass


def test_ner_passes_are_capped_at_two():
    nlp = FakeNLP({}, staged=["Ann", "Bob", "Cy"])
    r = sanitize("Ann Bob Cy", nlp=nlp)
    assert r.ner_passes == 2 and nlp.calls == 2 and "Cy" in r.text and "Ann" not in r.text and "Bob" not in r.text


def test_default_protected_list_is_empty():
    from part_b.sanitizer import DEFAULT_PROTECTED
    assert DEFAULT_PROTECTED == set()


# --- 4 digits after card / account wording (known-gap fix before leak review batch 1) ---
@pytest.mark.parametrize("text,digits", [
    ("my card 4821 was lost", "4821"), ("Debit Card 0042 got charged", "0042"), ("account 7731 was closed", "7731"), ("acct #5512 is frozen", "5512"),
    ("a/c no. 8812 shows nothing", "8812"), ("card number 4821 was used", "4821"), ("my account number is 3377.", "3377"), ("card: 6604, then nothing", "6604"),
    ("card XXXX 1234 was used", "1234"), ("account xxxx-9090 was drained", "9090"), ("card **** 4455 was used", "4455"),
    ("card ending 2024 was lost", "2024"), ("account number 1999 is mine", "1999"), ("card # 2050 expired", "2050"),
    ("I used my card 4821 3 days ago", "4821"), ("account 7731 2 weeks later", "7731"), ("card 4821 500 dollars were taken", "4821"),
    ("card number ending 4821 was used", "4821"), ("account no. ending 4821", "4821"), ("my card (4821) was lost", "4821"), ("card: #4821", "4821"),
    ("account, 4821", "4821"), ("my Visa ending 4821 was charged", "4821"), ("Mastercard ending 4821", "4821"),
])
def test_card_and_account_fragments_removed(text, digits):
    out = clean(text)
    assert digits not in out and "[LAST4]" in out


@pytest.mark.parametrize("text,kept", [
    ("I opened the account 2019 and it was fine", "2019"), ("my card XXXX 2023 statement", "2023"), ("since XXXX 2024 nothing changed", "2024"),
    ("they took from my account $4821 today", "4821"), ("charged to my card 1500 dollars", "1500"), ("debited from account 2500.00 yesterday", "2500.00"),
    ("my card $1,200 limit", "1,200"), ("a gift card 5000 points bonus", "5000"), ("the account 1500 limit was cut", "1500"), ("in 2024 my card was stolen", "2024"),
    ("I paid 4821 for it", "4821"), ("the card was charged 3000 twice", "3000"),
    ("the account 1234.5 units", "1234.5"), ("the card, 2023 edition", "2023"), ("for the year ending 2024", "2024"),
])
def test_amounts_and_years_are_kept(text, kept):
    out = clean(text)
    assert kept in out and "[LAST4]" not in out


@pytest.mark.parametrize("text", ["my card 4111 1111 1111 1111 was used", "account number 123456789012", "card 4111-1111-1111-1111 gone"])
def test_long_card_numbers_are_not_split_by_the_four_digit_rule(text):
    out = clean(text)
    assert not any(ch.isdigit() for ch in out) and "[LAST4]" not in out


def test_card_fragment_rule_is_idempotent():
    once = clean("card XXXX 1234 and account 7731")
    assert clean(once) == once
