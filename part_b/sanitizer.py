"""PII REDACTION (this module REWRITES text). Not to be confused with part_b/sensitive_flags.py, which DETECTS sensitive content,
never rewrites anything, and decides whether a narrative may leave this machine at all.

Conservative, layered, rule-based redaction with an optional local spaCy NER layer. It does NOT guarantee anonymization: it cannot
reliably catch names without cues, unusual identifier formats, employers, or indirect identifiers. Direct identifiers are replaced by
typed placeholders that keep classification-relevant context ("ending in [LAST4]", "[PHONE]"). Dollar amounts, durations and
company names are deliberately kept. Fail closed: anything unexpected raises SanitizerError / try_sanitize returns None, and the
caller must then keep the narrative local (see SPECS D-19, D-23).

KNOWN LIMITATIONS (found by synthetic probing; not fixable with simple rules): lowercase names without a cue ("my cousin dev patel"),
street names without a house number, dates without a year ("3/14"), "XXXX 1234" (the 4 digits are kept: indistinguishable from a year),
4-digit account fragments after "card"/"account", names the small NER model misses (informal / lowercase text), employers and indirect
identifiers, and over-redaction: long digit runs that are really amounts without a currency symbol or word become [NUMBER_ID].
"""
import re
import unicodedata
from dataclasses import dataclass, field

MAX_CHARS = 100_000
PLACEHOLDERS = ["[EMAIL]", "[PHONE]", "[URL]", "[ZIP]", "[NUMBER_ID]", "[LAST4]", "[DATE]", "[ADDRESS]", "[PERSON]", "[EMPLOYER]", "[LOCATION]", "[REDACTED]"]

# Public brands/banks that NER often mistakes for people or places. Step 2 extends this from the export's public 'Company' column.
DEFAULT_PROTECTED = {"zelle", "paypal", "venmo", "cash app", "cashapp", "chase", "wells fargo", "bank of america", "capital one", "citi", "citibank",
                     "discover", "american express", "amex", "visa", "mastercard", "apple", "apple pay", "google pay", "western union", "moneygram",
                     "coinbase", "robinhood", "navy federal", "truist", "pnc", "td bank", "us bank", "u.s. bank", "usaa", "ally", "chime", "sofi",
                     "walmart", "amazon", "ebay", "paysafe", "remitly", "wise", "samsung pay", "klarna", "affirm"}

STATES = ("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC PR").split()
MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
NAME = r"[A-Z][a-z'’-]+(?:\s+[A-Z]\.)?(?:\s+[A-Z][a-z'’-]+)?"  # first name, optional middle initial, optional last name (max 2 words: avoids swallowing the next sentence)


class SanitizerError(Exception):
    pass


@dataclass
class SanitizeResult:
    text: str
    counts: dict = field(default_factory=dict)   # placeholder -> number of replacements (no text content)
    ner_used: bool = False


def load_nlp():
    """Local spaCy small English model (no network, nothing leaves the machine). Parser/lemmatizer are not needed for NER."""
    import spacy
    return spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])


def _sub(rx, repl, text, counts, key):
    text, n = rx.subn(repl, text)
    if n:
        counts[key] = counts.get(key, 0) + n
    return text


def _last4(m):
    return m.group(1) + "[LAST4]"


_CURRENCY_WORDS = r"(?:dollars?|usd|bucks|euros?|eur|pounds?|gbp|pesos?|mxn|php|rupees?|inr|naira|ngn|cad|aud|yen|jpy|cents?)"


def _is_amount_context(text, start, end):
    """True if the number at text[start:end] looks like money: currency symbol before, or decimals / a currency word after."""
    before = text[max(0, start - 2):start]
    after = text[end:end + 14]
    return (before[-1:] in "$€£¥₹₦₱" and before[-1:] != "") or before.endswith("{$") or re.match(r"\.\d{2}\b", after) or re.match(r"\s*" + _CURRENCY_WORDS + r"\b", after, re.I)


R = re.compile
_EMAIL = R(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_EMAIL_OBF = R(r"\b[\w.+-]+\s*(?:\(at\)|\[at\]|\bat\b)\s*[\w-]+\s*(?:\(dot\)|\[dot\]|\bdot\b)\s*(?:com|net|org|edu|gov|io|co)\b", re.I)
_URL = R(r"\b(?:https?://|www\.)[^\s<>\"')\]]+", re.I)
_URL_BARE = R(r"\b[\w-]+(?:\.[\w-]+)*\.(?:com|net|org|edu|gov|io|co|us|info|biz)(?:/[^\s]*)?\b", re.I)
_DATE_NUM = R(r"(?<![\w/])(?:[Xx]{2}|\d{1,2})[/-](?:[Xx]{2}|\d{1,2})[/-](?:[Xx]{4}|[Xx]{2}|\d{4}|\d{2})(?![\w/])")
_DATE_ISO = R(r"\b\d{4}-\d{2}-\d{2}\b")
_DATE_TXT1 = R(r"\b" + MONTH + r"\.?\s+\d{1,2}(?:st|nd|rd|th)?\b(?!\d)(?:,?\s+(?:\d{4}|[Xx]{4})\b)?")
_DATE_TXT2 = R(r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?" + MONTH + r"\b(?:,?\s+(?:\d{4}|[Xx]{4})\b)?")
_SSN = R(r"(?<![\d-])\d{3}-\d{2}-\d{4}(?![\d-])")
_ZIP4 = R(r"(?<![\d-])\d{5}-\d{4}(?![\d-])")
_PHONE = R(r"(?<![\w$.,])(?:\+?\d{1,2}[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?![\w])")
_PHONE_INTL = R(r"(?<![\w$])\+\d{1,3}[\s.-]?\d{2,4}[\s.-]?\d{3,4}[\s.-]?\d{3,4}(?![\w])")
_LAST4_A = R(r"(?i)\b(ending\s+(?:in|with)\s+(?:#|x|\*+)?\s*)\d{4}\b")
_LAST4_B = R(r"(?i)\b(last\s+(?:4|four)(?:\s+digits)?(?:\s+of\s+(?:the\s+|my\s+)?(?:card|account|number|card\s+number|account\s+number))?\s*(?:is|are|was|:|-)?\s*)\d{4}\b")
_LAST4_MASK = R(r"(?<![\w])(?:[Xx*•]{2,}\d{4}|[Xx*•]{4}(?:[ -][Xx*•]{4}){1,3}[ -]\d{4}|[Xx]\d{4})(?!\d)")
_ZIP_CTX = R(r"(?i)\b(zip(?:\s*code)?\s*(?:is|:)?\s*)\d{5}\b")
_ZIP_STATE = R(r"\b(" + "|".join(STATES) + r")\s+\d{5}\b")
_ADDRESS = R(r"(?i)\b\d{1,6}\s+(?:[A-Za-z0-9.'’-]+\s+){1,4}(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|lane|ln|court|ct|way|place|pl|parkway|pkwy|highway|hwy|circle|cir|terrace|ter)\b\.?(?:\s*,?\s*(?:apt|apartment|unit|suite|ste|#)\s*\.?\s*[\w-]+)?")
_POBOX = R(r"(?i)\bP\.?\s?O\.?\s+Box\s+\d+\b")
_CUE_NAME = R(r"(?i)\bmy\s+name\s+is\s+([A-Za-z][A-Za-z'’-]+)((?:\s+[A-Za-z]\.)?)(?:\s+([A-Za-z][A-Za-z'’-]+))?")
_NOT_NAME_WORDS = {"and", "i", "im", "i'm", "a", "an", "the", "but", "from", "my", "is", "was", "of", "in", "at", "on", "to", "for", "with", "please", "thanks", "need",
                   "have", "had", "am", "will", "would", "can", "could", "we", "you", "so", "because", "as", "it", "this", "that", "calling", "writing", "trying", "not"}
_HONORIFIC = R(r"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr)\.?\s+" + NAME)
_CLOSING = R(r"(?i:\b(?:sincerely|regards|best\s+regards|kind\s+regards|respectfully|thanks|thank\s+you|yours\s+truly)\b)[,.!]?\s*\n?\s*(" + NAME + r")(?=[ \t]*(?:\n|$))")
_EMPLOYER = R(r"(?i:\b(?:i\s+work\s+(?:at|for)|i\s+am\s+employed\s+(?:at|by)|my\s+employer\s+is|employed\s+(?:at|by))\s+)([A-Z][\w&'.-]*(?:\s+(?:of\s+|and\s+|&\s+)?[A-Z][\w&'.-]*){0,3})")
_EMAIL_OBF2 = R(r"\b[\w.+-]+\s*(?:\(at\)|\[at\]|\{at\})\s*[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b", re.I)
_EMAIL_AT_TLD = R(r"\b[\w.+-]+\s+at\s+[\w-]+(?:\.[\w-]+)*\.(?:com|net|org|edu|gov|io|co|us|info|biz)\b", re.I)
_ALNUM_ID = R(r"(?<![\w$])(?=[A-Za-z]*\d)(?=\d*[A-Za-z])[A-Za-z0-9]{10,}(?![\w])")  # IBAN, wallet address, tracking / reference codes
_CUE_NUM = R(r"(?i)\b((?:account|acct|a/c|routing|reference|ref|confirmation|invoice|tracking|transaction|case|claim|order)\s*(?:number|no\.?|num|id|#)?\s*[:#]?\s*)(\d{5,})\b")
_CLOSING_LOWER = R(r"(?i:\b(?:sincerely|regards|best\s+regards|kind\s+regards|respectfully|yours\s+truly)\b)[,.!]?\s*\n?\s*([A-Za-z][A-Za-z'’-]+(?:\s+[A-Za-z]\.)?(?:\s+[A-Za-z][A-Za-z'’-]+)?)(?=[ \t]*(?:\n|$))")
_XTOKEN = R(r"\b[Xx]{2,}\b")
_NUMRUN = R(r"(?<![\w$.,/-])\d(?:[ -]?\d){5,}(?![\w%])")


def _protected(s, protected):
    t = s.lower().strip(" .")
    return t in protected or any(p in t for p in protected if len(p) > 3)


def sanitize(text: str, nlp=None, protected=DEFAULT_PROTECTED) -> SanitizeResult:
    if not isinstance(text, str):
        raise SanitizerError("input is not a string")
    if len(text) > MAX_CHARS:
        raise SanitizerError("input too long")
    counts: dict = {}
    t = unicodedata.normalize("NFC", text)
    t = re.sub(r"[ \t\u00a0\u2009\u202f]+", " ", t)
    t = re.sub(r"[ ]*\n[ \n]*", "\n", t).strip()
    # 1 identifiers with distinctive structure
    t = _sub(_EMAIL, "[EMAIL]", t, counts, "[EMAIL]")
    t = _sub(_EMAIL_OBF, "[EMAIL]", t, counts, "[EMAIL]")
    t = _sub(_EMAIL_OBF2, "[EMAIL]", t, counts, "[EMAIL]")
    t = _sub(_EMAIL_AT_TLD, "[EMAIL]", t, counts, "[EMAIL]")
    t = _sub(_URL, "[URL]", t, counts, "[URL]")
    t = _sub(_URL_BARE, "[URL]", t, counts, "[URL]")
    # 2 dates (numeric incl. CFPB-masked, ISO, textual day+month); month-year alone is kept
    for rx in (_DATE_NUM, _DATE_ISO, _DATE_TXT1, _DATE_TXT2):
        t = _sub(rx, "[DATE]", t, counts, "[DATE]")
    # 3 government/financial digit structures
    t = _sub(_SSN, "[NUMBER_ID]", t, counts, "[NUMBER_ID]")
    t = _sub(_ZIP4, "[ZIP]", t, counts, "[ZIP]")
    t = _sub(_PHONE_INTL, "[PHONE]", t, counts, "[PHONE]")
    t = _sub(_PHONE, "[PHONE]", t, counts, "[PHONE]")
    # 4 last-4 / masked numbers (before the generic X-token rule)
    t = _sub(_LAST4_A, _last4, t, counts, "[LAST4]")
    t = _sub(_LAST4_B, _last4, t, counts, "[LAST4]")
    t = _sub(_LAST4_MASK, "[LAST4]", t, counts, "[LAST4]")
    # 5 long digit runs (card / account / routing / reference numbers) unless they look like money
    def numrun(m):
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) < 6 or _is_amount_context(t_ref[0], m.start(), m.end()):
            return m.group(0)
        counts["[NUMBER_ID]"] = counts.get("[NUMBER_ID]", 0) + 1
        return "[NUMBER_ID]"
    t_ref = [t]
    t = _NUMRUN.sub(numrun, t)
    def cue_num(m):
        if _is_amount_context(m.string, m.start(2), m.end(2)):
            return m.group(0)
        counts["[NUMBER_ID]"] = counts.get("[NUMBER_ID]", 0) + 1
        return m.group(1) + "[NUMBER_ID]"
    t = _CUE_NUM.sub(cue_num, t)
    t = _sub(_ALNUM_ID, "[NUMBER_ID]", t, counts, "[NUMBER_ID]")
    # 6 ZIP with context, addresses
    t = _sub(_ZIP_CTX, lambda m: m.group(1) + "[ZIP]", t, counts, "[ZIP]")
    t = _sub(_ZIP_STATE, lambda m: m.group(1) + " [ZIP]", t, counts, "[ZIP]")
    t = _sub(_ADDRESS, "[ADDRESS]", t, counts, "[ADDRESS]")
    t = _sub(_POBOX, "[ADDRESS]", t, counts, "[ADDRESS]")
    # 7 name / employer cues
    def cue_name(m):
        """'my name is <first> [initial] [last]': first word is the name; the next word is the surname unless it is a function word."""
        out = m.group(0)[: m.start(1) - m.start(0)] + "[PERSON]"
        if m.group(3) and m.group(3).lower() in _NOT_NAME_WORDS:
            out += m.group(2) + " " + m.group(3)       # keep 'and', 'I', ... (initial, if any, was part of the name)
        return out
    t = _sub(_CUE_NAME, cue_name, t, counts, "[PERSON]")
    t = _sub(_HONORIFIC, "[PERSON]", t, counts, "[PERSON]")
    t = _sub(_CLOSING, lambda m: m.group(0) if _protected(m.group(1), protected) else m.group(0).replace(m.group(1), "[PERSON]"), t, counts, "[PERSON]")
    t = _sub(_CLOSING_LOWER, lambda m: m.group(0) if _protected(m.group(1), protected) else m.group(0).replace(m.group(1), "[PERSON]"), t, counts, "[PERSON]")
    t = _sub(_EMPLOYER, lambda m: m.group(0).replace(m.group(1), "[EMPLOYER]"), t, counts, "[EMPLOYER]")
    # 8 CFPB redaction tokens
    t = _sub(_XTOKEN, "[REDACTED]", t, counts, "[REDACTED]")
    # 9 local NER (people, places). Spans touching placeholders or protected brands are skipped.
    ner_used = False
    if nlp is not None:
        ner_used = True
        doc = nlp(t)
        spans = [e for e in doc.ents if e.label_ in ("PERSON", "GPE", "LOC") and "[" not in e.text and "]" not in e.text and not _protected(e.text, protected)]
        for e in sorted(spans, key=lambda e: -e.start_char):
            ph = "[PERSON]" if e.label_ == "PERSON" else "[LOCATION]"
            t = t[:e.start_char] + ph + t[e.end_char:]
            counts[ph] = counts.get(ph, 0) + 1
    # 10 tidy: merge repeated placeholders, whitespace
    t = re.sub(r"(\[(?:PERSON|LOCATION|REDACTED|ADDRESS)\])(?:[ ,]*\1)+", r"\1", t)
    t = re.sub(r"[ ]{2,}", " ", t).strip()
    return SanitizeResult(text=t, counts=counts, ner_used=ner_used)


def try_sanitize(text, nlp=None, protected=DEFAULT_PROTECTED):
    """Fail-closed wrapper: returns None on ANY problem, meaning the caller must keep the narrative local and log the exclusion."""
    try:
        return sanitize(text, nlp=nlp, protected=protected)
    except Exception:
        return None
