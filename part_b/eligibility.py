"""Eligible population (SPECS D-17, D-18) and the ONE sanitizer configuration shared by the leak review and, later, the pipeline.

Returned objects contain raw narrative text: never print or log them. Sanitized text is NOT thereby approved for external use.
"""
import hashlib, json, zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from part_b.export_audit_hashes import ACCEPTED_ZIP_SHA256
from part_b.run_sanitizer_aggregate import EXPECTED, N, PAY, build_protected, norm
from part_b.sanitizer import try_sanitize

ROOT = Path(__file__).resolve().parents[1]
MIN_COMPANY_ROWS = 25          # same protected-company rule as the Step 2 run
EXPECTED_PROTECTED_TERMS = 111
# Files whose content can change what gets selected or what the sanitized text looks like.
FINGERPRINT_FILES = ["part_b/sanitizer.py", "part_b/sensitive_flags.py", "part_b/eligibility.py", "part_b/run_sanitizer_aggregate.py"]


class EligibilityError(RuntimeError):
    """Messages must never include data."""


@dataclass(repr=False)         # no auto repr: it would print narratives
class Eligible:
    texts: list
    products: list
    protected: set
    archive_sha256: str
    ids: list                  # Complaint IDs, for the LOCAL manifest only


def load_eligible(zip_path, expected_sha=ACCEPTED_ZIP_SHA256, expected_counts=EXPECTED, expected_terms=EXPECTED_PROTECTED_TERMS) -> Eligible:
    digest = hashlib.sha256(Path(zip_path).read_bytes()).hexdigest()
    if digest != expected_sha:
        raise EligibilityError("archive is not the accepted D-16 file")
    with zipfile.ZipFile(zip_path) as z, z.open(z.namelist()[0]) as f:
        df = pd.read_csv(f, dtype=str, keep_default_na=False)
    pay = df[df["Product"].isin(PAY)]
    company_rows = pay["Company"].value_counts()
    protected = build_protected(company_rows[company_rows >= MIN_COMPANY_ROWS].index)
    d = pay[pay[N].str.strip() != ""].copy()
    d["key"] = d[N].map(lambda s: hashlib.sha256(norm(s).encode()).hexdigest()); d["cid"] = d["Complaint ID"].astype("int64")
    d = d.sort_values(["Date received", "cid"]).drop_duplicates("key", keep="first")
    d = d[d[N].str.split().str.len().between(30, 1500)]
    if d["Product"].value_counts().to_dict() != expected_counts:
        raise EligibilityError("eligible population differs from the recorded counts")
    if len(protected) != expected_terms:
        raise EligibilityError("protected company list differs from the Step 2 configuration")
    return Eligible(list(d[N]), list(d["Product"]), protected, digest, list(d["Complaint ID"]))


def sanitize_configured(raw: str, nlp, protected: set) -> str:
    """The shared configuration: all rules + local NER + the protected company list. Raises instead of returning partly sanitized text.
    (sanitize() silently skips NER when nlp is None, so that case is refused here.)"""
    if nlp is None:
        raise EligibilityError("language model is missing")
    result = try_sanitize(raw, nlp=nlp, protected=protected)
    if result is None or not result.ner_used:
        raise EligibilityError("sanitization failed")
    return result.text


def fingerprint(protected: set, nlp, root: Path = ROOT) -> dict:
    """Everything that defines the sanitized output and the unflagged pool. A sign-off is valid only while this is unchanged."""
    import spacy
    fp = {f: hashlib.sha256((root / f).read_bytes()).hexdigest() for f in FINGERPRINT_FILES}
    fp["protected_terms"] = hashlib.sha256(json.dumps(sorted(protected)).encode()).hexdigest()
    fp["spacy"] = spacy.__version__
    fp["model"] = f"{nlp.meta['name']}-{nlp.meta['version']}"
    return fp
