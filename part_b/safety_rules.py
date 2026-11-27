"""Deterministic safety layer (B5). A rule can only FORCE human review; nothing here can switch it off.

Written from the labeling guide, without looking at any evaluation record. Runs locally on the RAW text (redaction may hide evidence).
Filing with the CFPB is deliberately NOT a trigger: every record in this dataset is a CFPB complaint. Keyword rules over- and under-match.
"""
import re

R = re.compile
RULES = {
    "fraud_allegation": R(r"(?i)\b(?:fraud\w*|scam\w*|unauthori[sz]ed|stolen|stole|theft|identity\s+theft|phishing|hack(?:ed|er|ers|ing)|impersonat\w*|"
                          r"(?:did\s+not|didn'?t|never)\s+(?:authori[sz]e|approve|make\s+(?:this|these|that|the)\s+(?:charge|purchase|transaction|payment|withdrawal)s?)|"
                          r"without\s+(?:my\s+)?(?:consent|permission|authori[sz]ation|knowledge))\b"),
    "legal_threat": R(r"(?i)\b(?:lawyers?|attorneys?(?!\s+general)|lawsuit|law\s+suit|sue|suing|litigation|small\s+claims|class\s+action|legal\s+(?:action|counsel|proceedings?)|take\s+(?:this|you|them)\s+to\s+court|subpoena|arbitration)\b"),
    "regulator_escalation": R(r"(?i)\b(?:attorney\s+general|federal\s+trade\s+commission|FTC|FDIC|OCC|comptroller\s+of\s+the\s+currency|(?:state\s+)?banking\s+(?:commission(?:er)?|department)|department\s+of\s+financial\s+services)\b"),
    "unlawful_conduct": R(r"(?i)\b(?:discriminat\w*|illegal(?:ly)?|unlawful(?:ly)?|violat(?:e|ed|es|ing|ion|ions)\s+(?:of\s+)?(?:the\s+)?(?:\w+\s+){0,4}(?:act|law|regulation)s?|regulation\s+[EZ])\b"),
    "safety_self_harm": R(r"(?i)\b(?:suicid\w*|kill\s+(?:my\s*self|myself)|end(?:ing)?\s+my\s+life|self[- ]harm|hurt\s+myself|want\s+to\s+die|no\s+reason\s+to\s+live|domestic\s+(?:violence|abuse)|stalk(?:er|ing|ed)|death\s+threats?|threatened\s+(?:to\s+kill|me))\b"),
    "vulnerable_or_hardship": R(r"(?i)\b(?:elderly|elder\s+abuse|dementia|alzheimer\w*|homeless|evict\w*|(?:cannot|can'?t|unable\s+to)\s+(?:pay\s+(?:my\s+)?(?:rent|bills|mortgage)|buy\s+(?:food|medicine|medication))|disabled)\b"),
    "injection_suspected": R(r"(?i)(?:\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}\b(?:previous|prior|above|earlier|all|your|these|the)\b[^.\n]{0,20}\b(?:instructions?|rules?|prompt)\b|\bsystem\s+prompt\b|\byou\s+are\s+now\b|"
                             r"\brequires_human\b|</?\s*(?:complaint|system|instructions?)\s*>)"),
}


def fired_rules(text: str) -> list:
    """Names of the rules that match. Never returns matched text."""
    return sorted(name for name, rx in RULES.items() if rx.search(text))
