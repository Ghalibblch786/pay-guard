"""Summarize the user's verdicts from data/processed/flag_audit/flag_audit_verdicts.csv (no narrative text in that file). Prints COUNTS ONLY.
EXPLORATORY: ~3 items per category, flagged narratives only: not a reliable precision estimate and silent about false negatives.
  python -I part_b/flag_audit_summary.py
"""
import csv
from collections import Counter, defaultdict
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "data" / "processed" / "flag_audit" / "flag_audit_verdicts.csv"


def summarize(rows):
    by_cat, total = defaultdict(Counter), Counter()
    for r in rows:
        v = (r["verdict"] or "").strip().lower()
        if v not in ("y", "n", "u"): raise ValueError("verdict must be y, n or u for every row")
        by_cat[r["category"]][v] += 1; total[v] += 1
    return {c: dict(v) for c, v in sorted(by_cat.items())}, dict(total)


if __name__ == "__main__":
    by_cat, total = summarize(list(csv.DictReader(open(PATH))))
    for c, v in by_cat.items(): print(f"{c:28s} correct {v.get('y', 0)}  wrong {v.get('n', 0)}  unclear {v.get('u', 0)}")
    print("TOTAL", total, "| EXPLORATORY ONLY: tiny samples, flagged narratives only; not a precision estimate and no information on missed flags")
