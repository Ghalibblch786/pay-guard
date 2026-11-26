"""Stage 3a: AGGREGATE-ONLY inspection of one CFPB narratives-archive export. Never prints or saves narrative text.

Usage (isolated mode, untrusted input):  python -I part_b/inspect_archive.py <export.zip> <out.json>
"""
import json
import re
import sys
import zipfile

import pandas as pd

TARGET_PRODUCTS = ["Money transfer, virtual currency, or money service", "Checking or savings account",
                   "Credit card", "Prepaid card"]
PII = {  # pattern: description. Counts = narratives with >=1 match / total matches. Regexes are heuristics, not a guarantee.
    "email": r"[\w.+-]+@[\w-]+\.[\w.-]+",
    "phone_us": r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)",
    "ssn_like": r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)",
    "digits_9plus": r"(?<![\d.,$])\d{9,}(?![\d])",
    "card_like_13_19": r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)",
    "url": r"https?://\S+|www\.\S+",
    "street_address": r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s+){1,3}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct)\b",
    "zip5_like": r"(?<![\d$.,])\d{5}(?:-\d{4})?(?![\d%])",
    "date_like": r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    "redaction_xxxx": r"X{2,}",
    "redacted_amount_braces": r"\{\$[\d,\.]+\}",
}


def pct(a, b):
    return round(100 * a / b, 2) if b else None


def find_col(cols, *needles):
    for c in cols:
        if all(n in c.lower() for n in needles):
            return c
    return None


def main(zip_path, out_path):
    z = zipfile.ZipFile(zip_path)
    names = z.namelist()
    res = {"zip_members": names}
    with z.open(names[0]) as f:
        df = pd.read_csv(f, dtype=str, keep_default_na=False)
    cols = list(df.columns)
    res["format"] = "csv"
    res["columns"] = cols
    res["n_rows"] = int(len(df))
    c_id, c_prod, c_issue = find_col(cols, "complaint", "id"), find_col(cols, "product"), find_col(cols, "issue")
    c_date, c_narr = find_col(cols, "date", "received"), find_col(cols, "narrative")
    res["key_fields_present"] = {"Complaint ID": c_id, "Product": c_prod, "Issue": c_issue, "Date received": c_date,
                                 "Consumer complaint narrative": c_narr}
    res["other_columns_of_interest"] = {k: find_col(cols, k) for k in ("consent", "sub-product", "sub-issue", "tags")}
    if c_id:
        res["unique_complaint_ids"] = int(df[c_id].nunique()); res["duplicate_id_rows"] = int(df[c_id].duplicated().sum())
    if c_date:
        d = pd.to_datetime(df[c_date], errors="coerce"); res["date_received_min_max"] = [str(d.min().date()), str(d.max().date())]
        res["rows_by_month"] = {str(k): int(v) for k, v in d.dt.to_period("M").value_counts().sort_index().items()}
    if not c_narr:
        res["blocker"] = "no narrative column"; json.dump(res, open(out_path, "w"), indent=2); print(json.dumps(res, indent=2)); return
    narr = df[c_narr]
    has = narr.str.strip() != ""
    res["narratives_non_empty"] = {"n": int(has.sum()), "pct": pct(has.sum(), len(df))}
    prod_tab = df.groupby(c_prod).apply(lambda g: pd.Series({"rows": len(g), "with_narrative": int((narr[g.index].str.strip() != "").sum())}), include_groups=False)
    prod_tab["pct_with_narrative"] = (100 * prod_tab.with_narrative / prod_tab.rows).round(2)
    res["products"] = prod_tab.sort_values("rows", ascending=False).reset_index().to_dict("records")
    res["target_products_exact_name_found"] = {p: bool((df[c_prod] == p).any()) for p in TARGET_PRODUCTS}
    words = narr[has].str.split().str.len()
    q = [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
    res["narrative_words_all"] = {"min": int(words.min()), "max": int(words.max()), "mean": round(float(words.mean()), 1),
                                  **{f"p{int(x*100)}": float(words.quantile(x)) for x in q}}
    tgt = has & df[c_prod].isin(TARGET_PRODUCTS)
    w2 = narr[tgt].str.split().str.len()
    if len(w2):
        res["narrative_words_target_products"] = {"n": int(len(w2)), **{f"p{int(x*100)}": float(w2.quantile(x)) for x in q}}
        res["target_products_words_ge30_le1500"] = {p: int(((df[c_prod] == p) & has & (narr.str.split().str.len().between(30, 1500))).sum()) for p in TARGET_PRODUCTS}
    # top issues for target products (metadata, not narrative)
    if c_issue:
        res["top_issues_target_products"] = {p: df.loc[df[c_prod] == p, c_issue].value_counts().head(6).to_dict() for p in TARGET_PRODUCTS}
    # PII-pattern counts over non-empty narratives: counts only
    txt = narr[has]
    pii = {}
    for name, pat in PII.items():
        rx = re.compile(pat)
        counts = txt.map(lambda s: len(rx.findall(s)))
        pii[name] = {"narratives_with_match": int((counts > 0).sum()), "pct_of_narratives": pct((counts > 0).sum(), len(txt)), "total_matches": int(counts.sum())}
    res["pii_pattern_counts_all_non_empty"] = pii
    ttxt = narr[tgt]
    res["pii_pattern_counts_target_products"] = {name: {"narratives_with_match": int((ttxt.map(lambda s: len(re.findall(pat, s))) > 0).sum())}
                                                   for name, pat in PII.items()}
    json.dump(res, open(out_path, "w"), indent=2)
    print("wrote", out_path)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
