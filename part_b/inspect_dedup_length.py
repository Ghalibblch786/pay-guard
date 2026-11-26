"""Stage 3e planning: AGGREGATE-ONLY duplicate-narrative and length-eligibility impact (June 2026 export, payment-related products).
Hashes normalized text in memory; outputs counts only. Never prints or saves narrative text, hashes or Complaint IDs.
Usage (isolated mode):  python -I part_b/inspect_dedup_length.py <export.zip> <out.json>
"""
import hashlib, json, re, sys, unicodedata, zipfile

import pandas as pd

PAY = ["Credit card", "Checking or savings account", "Money transfer, virtual currency, or money service", "Prepaid card"]
N = "Consumer complaint narrative"


def norm_raw(s): return s.strip()
def norm_proposed(s): return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip()      # Unicode NFC + collapse whitespace; case and punctuation kept
def norm_casefold(s): return norm_proposed(s).casefold()                                      # sensitivity only


def h(s): return hashlib.sha256(s.encode()).hexdigest()


def main(zp, out):
    z = zipfile.ZipFile(zp)
    with z.open(z.namelist()[0]) as f: df = pd.read_csv(f, dtype=str, keep_default_na=False)
    df = df[df["Product"].isin(PAY) & (df[N].str.strip() != "")].copy()
    df["words"] = df[N].str.split().str.len()
    res = {"payment_narratives": int(len(df)), "by_product": df["Product"].value_counts().to_dict()}
    sens = {}
    for name, fn in [("raw_strip", norm_raw), ("PROPOSED_nfc_collapse_whitespace", norm_proposed), ("sensitivity_casefold", norm_casefold)]:
        key = df[N].map(lambda s: h(fn(s))); extra = key.duplicated()
        sens[name] = {"rows_in_dup_groups": int(key.duplicated(keep=False).sum()), "extra_copies_to_remove": int(extra.sum()),
                      "removed_by_product": df.loc[extra, "Product"].value_counts().to_dict()}
    res["normalization_sensitivity"] = sens
    df["key"] = df[N].map(lambda s: h(norm_proposed(s)))
    g = df.groupby("key")
    sizes = g.size(); dup_groups = sizes[sizes > 1]
    res["dup_groups"] = {"n_groups": int(len(dup_groups)), "size_dist": {"2": int((dup_groups == 2).sum()), "3-5": int(dup_groups.between(3, 5).sum()), "6-20": int(dup_groups.between(6, 20).sum()), ">20": int((dup_groups > 20).sum())},
                         "largest_group_size": int(dup_groups.max()) if len(dup_groups) else 0}
    m = df[df.key.isin(dup_groups.index)]
    gg = m.groupby("key")
    res["dup_group_heterogeneity"] = {"share_groups_with_>1_company": round(float((gg["Company"].nunique() > 1).mean()), 3), "share_groups_with_>1_state": round(float((gg["State"].nunique() > 1).mean()), 3),
        "share_groups_with_>1_date_received": round(float((gg["Date received"].nunique() > 1).mean()), 3), "share_groups_with_>1_product": round(float((gg["Product"].nunique() > 1).mean()), 3),
        "share_groups_with_>1_issue": round(float((gg["Issue"].nunique() > 1).mean()), 3)}
    res["dup_group_words_median"] = float(m.groupby("key")["words"].first().median()) if len(m) else None
    # keep one representative per group: earliest Date received, ties by smallest Complaint ID
    df["cid"] = df["Complaint ID"].astype("int64")
    keep = df.sort_values(["Date received", "cid"]).drop_duplicates("key", keep="first")
    res["after_dedup_by_product"] = keep["Product"].value_counts().to_dict(); res["after_dedup_total"] = int(len(keep))
    # length eligibility, evaluated AFTER dedup (and before, for reference)
    def length_table(d):
        t = {}
        for p in PAY + ["ALL"]:
            x = d if p == "ALL" else d[d["Product"] == p]
            t[p] = {"n": int(len(x)), "lt30": int((x.words < 30).sum()), "30_to_1500": int(x.words.between(30, 1500).sum()), "gt1500": int((x.words > 1500).sum()),
                    "lt20": int((x.words < 20).sum()), "lt50": int((x.words < 50).sum()), "gt1000": int((x.words > 1000).sum()), "gt2000": int((x.words > 2000).sum())}
        return t
    res["length_after_dedup"] = length_table(keep); res["length_before_dedup"] = length_table(df)
    elig = keep[keep.words.between(30, 1500)]
    res["eligible_after_dedup_and_30_1500"] = {"n": int(len(elig)), "by_product": elig["Product"].value_counts().to_dict()}
    tot = len(elig); alloc = {p: round(400 * int((elig["Product"] == p).sum()) / tot, 1) for p in PAY}
    res["proportional_allocation_n400"] = alloc
    res["words_after_filters"] = {k: float(elig.words.quantile(q)) for k, q in [("p25", .25), ("p50", .5), ("p75", .75), ("p95", .95)]}
    # narratives shared across products (same text under >1 product)
    res["texts_shared_across_products"] = int((df.groupby("key")["Product"].nunique() > 1).sum())
    json.dump(res, open(out, "w"), indent=2); print("wrote", out)


if __name__ == "__main__": main(sys.argv[1], sys.argv[2])
