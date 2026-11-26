"""Stage 3d: AGGREGATE-ONLY inspection of one COMPLETE CFPB archive export (read in memory from the zip; nothing extracted to disk).
Never prints or saves narrative text.   Usage (isolated mode):  python -I part_b/inspect_full.py <export.zip> <out.json>
"""
import hashlib, json, re, sys, zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from inspect_archive import PII  # same heuristic patterns as Stage 3a/3b (not a guarantee of anonymization)

PAY = ["Credit card", "Checking or savings account", "Money transfer, virtual currency, or money service", "Prepaid card"]


def pct(a, b): return round(100 * a / b, 2) if b else None


def wstats(w):
    q = [0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]
    return {"n": int(len(w)), "min": int(w.min()), "mean": round(float(w.mean()), 1), "max": int(w.max()), **{f"p{int(x*100)}": float(w.quantile(x)) for x in q}} if len(w) else {"n": 0}


def main(zp, out):
    z = zipfile.ZipFile(zp); name = z.namelist()[0]
    with z.open(name) as f: df = pd.read_csv(f, dtype=str, keep_default_na=False)
    res = {"member": name, "n_rows": int(len(df)), "columns": list(df.columns)}
    res["empty_cells_per_column"] = {c: int((df[c].str.strip() == "").sum()) for c in df.columns}
    res["duplicate_complaint_id_rows"] = int(df["Complaint ID"].duplicated().sum()); res["unique_complaint_ids"] = int(df["Complaint ID"].nunique())
    res["fully_duplicated_rows"] = int(df.duplicated().sum())
    N = "Consumer complaint narrative"; has = df[N].str.strip() != ""
    res["narratives_non_empty"] = {"n": int(has.sum()), "pct": pct(has.sum(), len(df))}
    d = pd.to_datetime(df["Date received"]); res["date_received_min_max"] = [str(d.min().date()), str(d.max().date())]
    # by product
    g = df.assign(h=has).groupby("Product").agg(rows=("h", "size"), with_narrative=("h", "sum")).sort_values("rows", ascending=False)
    g["pct"] = (100 * g.with_narrative / g.rows).round(2); res["by_product"] = g.reset_index().to_dict("records")
    # by week received (all products and payment-related)
    wk = d.dt.date.map(lambda x: (x - timedelta(days=x.weekday())).isoformat())
    pay = df["Product"].isin(PAY)
    t = pd.DataFrame({"wk": wk, "h": has, "pay": pay})
    r = t.groupby("wk").agg(rows=("h", "size"), narr=("h", "sum"), pay_rows=("pay", "sum")).join(t[t.pay].groupby("wk").h.sum().rename("pay_narr")).fillna(0).astype(int)
    r["pct_all"] = (100 * r.narr / r.rows).round(2); r["pct_pay"] = (100 * r.pay_narr / r.pay_rows.replace(0, pd.NA)).astype(float).round(2)
    res["by_week_received"] = r.reset_index().to_dict("records")
    # by day for the payment-related narratives (to see time pattern at finer grain)
    dd = pd.DataFrame({"day": d.dt.strftime("%Y-%m-%d"), "h": has, "pay": pay})
    rd = dd[dd.pay].groupby("day").agg(pay_rows=("h", "size"), pay_narr=("h", "sum")); rd["pct"] = (100 * rd.pay_narr / rd.pay_rows).round(1)
    res["payment_by_day"] = rd.reset_index().to_dict("records")
    # position in file (deciles of row order) - to test the 'fill falls along the file' hypothesis from the prefix
    pos = pd.Series(range(len(df))) * 10 // len(df)
    res["fill_by_file_position_decile"] = [{"decile": int(k), "rows": int(v.size), "pct_all": pct(has[v.index].sum(), v.size), "pct_pay": pct((has & pay)[v.index].sum(), pay[v.index].sum())} for k, v in pos.groupby(pos)]
    # payment-related products: exact counts + length thresholds
    words = df[N].str.split().str.len().where(has)
    res["payment_products"] = {}
    for p in PAY:
        m = df["Product"] == p; mh = m & has
        res["payment_products"][p] = {"rows": int(m.sum()), "with_narrative": int(mh.sum()), "pct": pct(mh.sum(), m.sum()),
            "narr_words_ge20": int((mh & (words >= 20)).sum()), "narr_words_ge30": int((mh & (words >= 30)).sum()), "narr_words_ge50": int((mh & (words >= 50)).sum()),
            "narr_words_30_to_1500": int((mh & words.between(30, 1500)).sum()), "words": wstats(words[mh].dropna()),
            "xxxx_redaction_narratives": int(df.loc[mh, N].str.contains(r"X{2,}", regex=True).sum()), "top_issues_with_narrative": df.loc[mh, "Issue"].value_counts().head(8).to_dict()}
    res["words_all_narratives"] = wstats(words[has].dropna()); res["words_payment_narratives"] = wstats(words[has & pay].dropna())
    res["payment_narratives_total"] = int((has & pay).sum()); res["payment_narratives_30_to_1500_words"] = int((has & pay & words.between(30, 1500)).sum())
    # duplicate narrative texts (aggregate only: hashed, nothing stored)
    hs = df.loc[has, N].map(lambda s: hashlib.sha256(s.strip().encode()).hexdigest())
    res["duplicate_narrative_texts"] = {"rows_with_a_duplicate_text": int(hs.duplicated(keep=False).sum()), "extra_copies": int(hs.duplicated().sum())}
    # PII-pattern counts (heuristics; not a guarantee)
    def pii_counts(s):
        out = {}
        for k, pat in PII.items():
            rx = re.compile(pat); c = s.map(lambda x: len(rx.findall(x)))
            out[k] = {"narratives_with_match": int((c > 0).sum()), "pct": pct((c > 0).sum(), len(s)), "total_matches": int(c.sum())}
        return out
    res["pii_all_narratives"] = pii_counts(df.loc[has, N]); res["pii_payment_narratives"] = pii_counts(df.loc[has & pay, N])
    json.dump(res, open(out, "w"), indent=2); print("wrote", out)


if __name__ == "__main__": main(sys.argv[1], sys.argv[2])
