"""M3 Step 2: run the sanitizer + sensitive-content flagger IN MEMORY over the eligible population and report AGGREGATES ONLY.
Never prints, saves or transmits narrative text (raw or sanitized), Complaint IDs or text hashes. No network, no LLM.

Eligible = payment-related products, non-empty narrative, exact-duplicate removal (SHA-256 of NFC + collapsed-whitespace text, earliest Date
received then smallest Complaint ID kept), 30-1,500 words (SPECS D-17, D-18). Protected company names come ONLY from the export's public
'Company' column.   Usage (isolated mode):  python -I part_b/run_sanitizer_aggregate.py <export.zip> <out.json>
"""
import hashlib, json, re, statistics, sys, time, unicodedata, zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd

from part_b.inspect_archive import PII
from part_b.sanitizer import PLACEHOLDERS, load_nlp, sanitize, try_sanitize
from part_b.sensitive_flags import CATEGORIES, detect_sensitive

PAY = ["Credit card", "Checking or savings account", "Money transfer, virtual currency, or money service", "Prepaid card"]
N = "Consumer complaint narrative"
EXPECTED = {"Checking or savings account": 3155, "Credit card": 2723, "Money transfer, virtual currency, or money service": 1290, "Prepaid card": 208}
GENERIC = {"bank", "banks", "credit", "union", "financial", "services", "national", "first", "federal", "savings", "trust", "group", "holdings", "capital", "american",
           "united", "community", "the", "company", "corporation", "state", "city", "county", "mutual", "investment", "payments", "payment", "card", "cards", "loan", "loans"}
SUFFIX = re.compile(r"\b(inc|llc|l\.l\.c|corp|corporation|co|company|ltd|plc|lp|llp|n\.?a|na|national association|group|holdings|usa|us|services|financial|bank|banks)\b\.?", re.I)
BRANDS = ["zelle", "venmo", "paypal", "cash app", "chase", "wells fargo", "bank of america", "capital one", "discover", "american express", "visa", "mastercard", "western union",
          "moneygram", "coinbase", "apple pay", "citi", "usaa", "navy federal", "truist", "pnc", "chime", "sofi", "robinhood"]
KEYWORDS = ["fraud", "unauthorized", "scam", "refund", "attorney", "lawsuit", "dispute", "chargeback", "stolen", "sue", "lawyer", "police", "cfpb"]


def norm(s): return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip()


def build_protected(company_series):
    """Protected terms from the public Company column only: full cleaned name and the name core (legal suffixes removed); generic/short cores dropped."""
    out = set()
    for c in company_series:
        full = re.sub(r"[^\w&' .-]", " ", c.lower()).strip(" .")
        core = re.sub(r"\s+", " ", SUFFIX.sub(" ", full)).strip(" .-&")
        for term in (full, core):
            if len(term) >= 5 and term not in GENERIC and not all(w in GENERIC for w in term.split()):
                out.add(term)
    return out


def pct(a, b): return round(100 * a / b, 2) if b else None


def dist(xs):
    xs = sorted(xs)
    return {"mean": round(statistics.mean(xs), 2), "median": statistics.median(xs), "p95": xs[int(0.95 * (len(xs) - 1))], "max": xs[-1]} if xs else {}


def assert_no_text(obj, path=""):
    """Safety net: every string in the output must be a short label, never narrative-like text."""
    if isinstance(obj, dict):
        for k, v in obj.items(): assert_no_text(k, path); assert_no_text(v, path + "/" + str(k))
    elif isinstance(obj, (list, tuple)):
        for v in obj: assert_no_text(v, path)
    elif isinstance(obj, str):
        assert len(obj) <= 70, f"string too long at {path}"


def main(zp, out):
    t0 = time.time()
    z = zipfile.ZipFile(zp)
    with z.open(z.namelist()[0]) as f: df = pd.read_csv(f, dtype=str, keep_default_na=False)
    pay_rows = df[df["Product"].isin(PAY)]
    cnt = pay_rows["Company"].value_counts()
    protected = build_protected(cnt[cnt >= 25].index)            # Company column only; companies with >=25 payment-product complaints
    d = pay_rows[pay_rows[N].str.strip() != ""].copy()
    d["key"] = d[N].map(lambda s: hashlib.sha256(norm(s).encode()).hexdigest()); d["cid"] = d["Complaint ID"].astype("int64")
    d = d.sort_values(["Date received", "cid"]).drop_duplicates("key", keep="first")
    d["words"] = d[N].str.split().str.len(); d = d[d.words.between(30, 1500)]
    got = d["Product"].value_counts().to_dict(); assert got == EXPECTED, "eligible population differs from Stage 3e"
    res = {"eligible_n": int(len(d)), "eligible_by_product": got, "protected_company_terms": len(protected), "companies_considered": int((cnt >= 25).sum())}
    nlp = load_nlp()
    totals, narr_with, flags_by_prod, flag_overlap = Counter(), Counter(), defaultdict(Counter), Counter()
    by_prod_changed, by_prod_repl = Counter(), defaultdict(Counter)
    fails, fail_cls, nonidem, resid_total, resid_narr = Counter(), Counter(), 0, Counter(), Counter()
    repl_per_narr, ph_per_100w, high_ph, shrunk = [], [], 0, 0
    kw_raw, kw_kept, brand_raw, brand_kept = Counter(), Counter(), Counter(), Counter()
    local_only, ner_skips, ner_passes, second_pass = Counter(), Counter(), Counter(), Counter()
    for raw, prod in zip(d[N], d["Product"]):
        flagged = False
        try:
            fr = detect_sensitive(raw); flagged = fr.is_sensitive
            for c in fr.categories: flags_by_prod[prod][c] += 1
            flags_by_prod[prod]["ANY_FLAG"] += int(flagged); flag_overlap[min(len(fr.categories), 3)] += 1
        except Exception as e:
            flagged = True; fails["flagger_error"] += 1; fail_cls[type(e).__name__] += 1
        r = try_sanitize(raw, nlp=nlp, protected=protected)
        if r is None:
            fails["sanitizer_failed"] += 1; local_only[prod] += 1; continue
        if flagged: local_only[prod] += 1
        ner_skips.update(r.ner_skips); ner_passes[r.ner_passes] += 1
        n_repl = sum(r.counts.values()); words = max(len(raw.split()), 1)
        repl_per_narr.append(n_repl); ph_per_100w.append(100 * n_repl / words)
        if n_repl: by_prod_changed[prod] += 1
        if n_repl / words > 0.10: high_ph += 1
        if len(r.text.split()) < 0.5 * words: shrunk += 1
        for k, v in r.counts.items(): totals[k] += v; narr_with[k] += 1; by_prod_repl[prod][k] += v
        r2 = try_sanitize(r.text, nlp=nlp, protected=protected)
        if r2 is None or r2.text != r.text:
            nonidem += 1
            if r2 is not None: second_pass.update(r2.counts)
        for name, pat in PII.items():                           # residual scan on the SANITIZED text (counts only)
            if name in ("redaction_xxxx", "redacted_amount_braces"): continue
            m = len(re.findall(pat, r.text))
            if m: resid_total[name] += m; resid_narr[name] += 1
        if re.search(r"\b[Xx]{2,}\b", r.text): resid_narr["leftover_XXXX"] += 1
        low_raw, low_new = raw.lower(), r.text.lower()
        for k in KEYWORDS:
            if re.search(r"\b" + k + r"\b", low_raw): kw_raw[k] += 1; kw_kept[k] += int(bool(re.search(r"\b" + k + r"\b", low_new)))
        for b in BRANDS:
            if re.search(r"\b" + re.escape(b) + r"\b", low_raw): brand_raw[b] += 1; brand_kept[b] += int(bool(re.search(r"\b" + re.escape(b) + r"\b", low_new)))
    n_ok = len(repl_per_narr)
    res["processing"] = {"sanitized_ok": n_ok, "failures": dict(fails), "failure_exception_classes": dict(fail_cls), "failed_closed_rate_pct": pct(fails["sanitizer_failed"], len(d))}
    res["narratives_changed"] = {"n": int(sum(by_prod_changed.values())), "pct_of_ok": pct(sum(by_prod_changed.values()), n_ok), "by_product": dict(by_prod_changed)}
    res["replacement_totals"] = {k: {"replacements": int(totals[k]), "narratives_with": int(narr_with[k]), "pct_narratives": pct(narr_with[k], n_ok)} for k in PLACEHOLDERS if totals[k]}
    res["replacements_by_product"] = {p: dict(c) for p, c in by_prod_repl.items()}
    res["replacements_per_narrative"] = dist(repl_per_narr); res["placeholders_per_100_words"] = dist([round(x, 2) for x in ph_per_100w])
    res["over_redaction_indicators"] = {"narratives_over_10pct_placeholder_words": high_ph, "narratives_shrunk_below_half_words": shrunk}
    res["sensitive_flags_by_product"] = {p: {k: int(v) for k, v in flags_by_prod[p].items()} for p in PAY}
    res["sensitive_flag_any_rate_pct_by_product"] = {p: pct(flags_by_prod[p]["ANY_FLAG"], EXPECTED[p]) for p in PAY}
    res["sensitive_flags_total"] = {"any": int(sum(flags_by_prod[p]["ANY_FLAG"] for p in PAY)), "by_category": {c: int(sum(flags_by_prod[p][c] for p in PAY)) for c in CATEGORIES},
                                    "categories_per_flagged_narrative": {"1": int(flag_overlap[1]), "2": int(flag_overlap[2]), "3_or_more": int(flag_overlap[3])}}
    res["local_only_routing"] = {"by_product": dict(local_only), "total": int(sum(local_only.values())), "pct_of_eligible": pct(sum(local_only.values()), len(d)), "note": "flagged OR sanitizer failed: would never leave the machine"}
    res["residual_pattern_counts_in_sanitized_text"] = {k: {"narratives": int(resid_narr[k]), "matches": int(resid_total[k])} for k in list(PII) + ["leftover_XXXX"] if resid_narr[k]}
    res["idempotence_violations"] = nonidem
    res["idempotence_second_pass_replacements"] = dict(second_pass)
    res["ner_skips_first_pass"] = dict(ner_skips); res["ner_passes_distribution"] = {str(k): int(v) for k, v in sorted(ner_passes.items())}
    res["critical_keyword_survival"] = {k: {"raw_narratives": int(kw_raw[k]), "kept_after_sanitizing": int(kw_kept[k])} for k in KEYWORDS if kw_raw[k]}
    res["brand_survival_check"] = {b: {"raw_narratives": int(brand_raw[b]), "kept_after_sanitizing": int(brand_kept[b])} for b in BRANDS if brand_raw[b]}
    res["runtime_seconds"] = round(time.time() - t0, 1)
    assert_no_text(res)
    json.dump(res, open(out, "w"), indent=2); print("wrote", out, "| eligible", len(d), "| seconds", res["runtime_seconds"])


if __name__ == "__main__": main(sys.argv[1], sys.argv[2])
