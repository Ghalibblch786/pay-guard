"""M3 Step 2 diagnostics: attribute unexpected behaviours to a layer. AGGREGATE COUNTS ONLY (no text, IDs or hashes printed or saved).
Usage (isolated mode): python -I part_b/diagnose_step2.py <export.zip> <out.json>
"""
import hashlib, json, re, sys, time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import zipfile
import pandas as pd

import part_b.sanitizer as S
from part_b.run_sanitizer_aggregate import EXPECTED, N, PAY, build_protected, norm

TERMS = ["fraud", "scam", "chargeback", "venmo", "zelle", "citi", "visa", "mastercard", "cash app", "bank of america", "discover", "usaa", "sofi", "chime"]


def main(zp, out):
    t0 = time.time()
    z = zipfile.ZipFile(zp)
    with z.open(z.namelist()[0]) as f: df = pd.read_csv(f, dtype=str, keep_default_na=False)
    pay = df[df["Product"].isin(PAY)]; cnt = pay["Company"].value_counts(); protected = build_protected(cnt[cnt >= 25].index)
    d = pay[pay[N].str.strip() != ""].copy()
    d["key"] = d[N].map(lambda s: hashlib.sha256(norm(s).encode()).hexdigest()); d["cid"] = d["Complaint ID"].astype("int64")
    d = d.sort_values(["Date received", "cid"]).drop_duplicates("key", keep="first"); d["w"] = d[N].str.split().str.len(); d = d[d.w.between(30, 1500)]
    assert d["Product"].value_counts().to_dict() == EXPECTED
    nlp = S.load_nlp()
    res = {"email_regex_raw_narratives_matching": {}, "url_regex_raw_narratives_matching": {}}
    for name, rx in [("standard", S._EMAIL), ("obfuscated_dot_words", S._EMAIL_OBF), ("obfuscated_(at)_[at]", S._EMAIL_OBF2), ("(rule removed in D-27)", S._EMAIL_OBF2)]:
        res["email_regex_raw_narratives_matching"][name] = int(d[N].map(lambda s, rx=rx: bool(rx.search(s))).sum())
    for name, rx in [("http_or_www", S._URL), ("bare_domain", S._URL_BARE)]:
        res["url_regex_raw_narratives_matching"][name] = int(d[N].map(lambda s, rx=rx: bool(rx.search(s))).sum())
    nonidem, second_pass, nonidem_regex_only = 0, Counter(), 0
    loss = {t: Counter() for t in TERMS}
    for raw in d[N]:
        r1 = S.sanitize(raw, nlp=nlp, protected=protected); low_raw, low1 = raw.lower(), r1.text.lower()
        r2 = S.sanitize(r1.text, nlp=nlp, protected=protected)
        if r2.text != r1.text:
            nonidem += 1; second_pass.update({k: v for k, v in r2.counts.items()})
            ro1 = S.sanitize(raw, nlp=None, protected=protected); ro2 = S.sanitize(ro1.text, nlp=None, protected=protected)
            nonidem_regex_only += int(ro2.text != ro1.text)
        for t in TERMS:
            if re.search(r"\b" + re.escape(t) + r"\b", low_raw):
                loss[t]["raw"] += 1
                if t not in low1:
                    loss[t]["lost_with_ner"] += 1
                    rn = S.sanitize(raw, nlp=None, protected=protected)
                    loss[t]["lost_even_without_ner"] += int(t not in rn.text.lower())
    res["idempotence"] = {"violations": nonidem, "second_pass_replacements_by_placeholder": dict(second_pass), "of_these_also_non_idempotent_regex_only": nonidem_regex_only}
    res["term_loss_attribution"] = {t: dict(c) for t, c in loss.items() if c["raw"]}
    res["runtime_seconds"] = round(time.time() - t0, 1)
    json.dump(res, open(out, "w"), indent=2); print("wrote", out, res["runtime_seconds"])


if __name__ == "__main__": main(sys.argv[1], sys.argv[2])
