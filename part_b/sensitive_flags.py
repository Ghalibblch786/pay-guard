"""SENSITIVE-CONTENT DETECTION (this module NEVER rewrites text). Not to be confused with part_b/sanitizer.py, which REDACTS PII.

Decides whether a narrative may leave this machine: any flagged narrative is NEVER sent to an external service and is routed directly to
human review (SPECS D-23), but it stays in the sample and the evaluation. It is applied to the RAW text locally (redaction can hide the
evidence, e.g. "routing number 021000021" becomes "routing number [NUMBER_ID]") and the result contains only category names and match counts,
never matched text. Keyword rules are blunt: they over-flag (false positives only cost human workload) and can miss paraphrases (false
negatives are the privacy risk, measured against the human `contains_sensitive` label, which itself is made on sanitized text and so can miss
evidence the redaction concealed).
"""
import re
from dataclasses import dataclass, field

R = re.compile
CATEGORIES = {
    "health_medical": R(r"(?i)\b(?:diagnos\w*|cancer|chemo\w*|hospital\w*|surgery|surgical|medication\w*|prescription\w*|disabilit\w*|disabled|mental\s+health|therapy|therapist|"
                         r"pregnan\w*|medical|doctor|illness|dementia|alzheimer\w*|disease|depress(?:ion|ed)|psychiatr\w*|diabet\w*|dialysis|hospice|cardiac|stroke|terminally)\b"),
    "minors": R(r"(?i)\b(?:(?:my|our|his|her|their)\s+(?:minor\s+)?(?:son|daughter|child|children|kid|kids|baby|infant|toddler|grandchild|grandchildren|grandson|granddaughter|"
                r"teen(?:ager)?|stepson|stepdaughter|niece|nephew)|minors?|underage|under\s+(?:the\s+age\s+of\s+)?18|custodial|utma|ugma|(?:[0-9]|1[0-7])[- ]year[- ]old)\b"),
    "government_id": R(r"(?i)\b(?:ssn|social\s+security|driver'?s?\s+licen[cs]e|passport|itin|tax\s+id|taxpayer\s+id\w*|national\s+id|state\s+id|government[- ]issued\s+id|id\s+card)\b"),
    "financial_account_details": R(r"(?i)\b(?:(?:bank\s+|checking\s+|savings\s+|debit\s+card\s+|credit\s+card\s+)?account\s+(?:number|no\.?|#)|routing\s+(?:number|no\.?|#)|aba\s+(?:number|routing)|"
                                   r"iban|swift\s+(?:code|number)|(?:debit\s+|credit\s+)?card\s+number|cvv|cvc|security\s+code|card\s+expir\w+|expiration\s+date|wire\s+instructions|account\s+and\s+routing)\b"),
    "credentials_authentication": R(r"(?i)\b(?:passwords?|passcodes?|passphrase|pin\s+(?:number|code)|(?:my|your|the)\s+pin|security\s+(?:question|answer)s?|maiden\s+name|"
                                    r"one[- ]time\s+(?:code|passcode|password|pin)|otp|verification\s+code|authentication\s+code|(?:log[- ]?in|sign[- ]?in)\s+credentials?|username\s+and\s+password)\b|\bPIN\b"),
    "immigration_legal_case": R(r"(?i)\b(?:immigration|green\s+card|asylum|deport\w*|work\s+permit|daca|visa\s+(?:application|status|holder)|court\s+order|restraining\s+order|subpoena|"
                                r"docket|(?:case|docket|file|claim)\s*(?:no\.?|number|#)\s*[:#]?\s*[\w-]*\d[\w-]*)\b"),
    "self_harm_safety": R(r"(?i)\b(?:suicid\w*|kill\s+(?:my\s*self|myself)|end\s+my\s+life|self[- ]harm|hurt\s+myself|want\s+to\s+die|domestic\s+(?:violence|abuse)|abusive\s+(?:husband|wife|partner|spouse|boyfriend|girlfriend)|"
                          r"stalk(?:er|ing|ed)|death\s+threats?|threatened\s+to\s+kill)\b"),
}
_LONG_DIGITS = R(r"(?<![\w$.,])\d(?:[ -]?\d){8,}(?![\w%])")  # 9+ digits: possible routing / account / card number in the raw text


@dataclass
class SensitiveResult:
    categories: frozenset = frozenset()
    hits: dict = field(default_factory=dict)  # category -> number of matches (no matched text)

    @property
    def is_sensitive(self) -> bool:
        return bool(self.categories)


def detect_sensitive(raw_text: str) -> SensitiveResult:
    """Return which sensitive categories fire on the RAW text. Raises TypeError on non-strings (fail closed: caller treats as sensitive)."""
    if not isinstance(raw_text, str):
        raise TypeError("raw_text must be a string")
    hits = {}
    for name, rx in CATEGORIES.items():
        n = len(rx.findall(raw_text))
        if n:
            hits[name] = n
    n_digits = len(_LONG_DIGITS.findall(raw_text))
    if n_digits:
        hits["financial_account_details"] = hits.get("financial_account_details", 0) + n_digits
    return SensitiveResult(categories=frozenset(hits), hits=hits)


def is_sensitive_failclosed(raw_text) -> bool:
    """True if sensitive OR if detection itself fails (unknown => keep local)."""
    try:
        return detect_sensitive(raw_text).is_sensitive
    except Exception:
        return True
