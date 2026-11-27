"""Scoring (B6, B8). Definitions follow part_b/evaluation_plan.md (frozen before any model output existed).

  python -m part_b.evaluate_triage dev --prompt v1       # synthetic development cases
  python -m part_b.evaluate_triage adversarial           # synthetic attack and safety cases, pass/fail
  python -m part_b.evaluate_triage labels                # the author's hand labels vs the final prompt (aggregates only)
  python -m part_b.evaluate_triage summary-sheet         # AFTER labeling: 10 local summaries to rate
"""
import argparse, csv, hashlib, json, random, sys
from collections import Counter
from pathlib import Path

import numpy as np

from config import SEED
from part_b.prompts import TAXONOMY
from part_b.run_triage import FINAL_PROMPT, RUNS, SYNTHETIC, lost_to_transport

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "data" / "processed" / "labeling" / "labels.csv"
CATEGORIES = [c["id"] for c in TAXONOMY["categories"]]
URGENCY = TAXONOMY["urgency_levels"]
N_BOOT = 1000


def read_results(path: Path) -> dict:
    return {r["key"]: r for r in map(json.loads, Path(path).read_text().splitlines())}


def read_labels(path: Path) -> list:
    """The labeled PREFIX of the frozen order (items 1..N). Errors name the item and column only."""
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    labels, finished = [], False
    for n, row in enumerate(rows, 1):
        values = {k: (v or "").strip().lower() for k, v in row.items() if k}
        if values.get("item") != str(n):
            raise ValueError(f"row {n}: item number out of order")
        if not any(values.get(k) for k in ("category", "urgency", "requires_human")):
            finished = True
            continue
        if finished:
            raise ValueError(f"item {n}: labels must be an unbroken run starting at item 1")
        for column, allowed in [("category", CATEGORIES), ("urgency", URGENCY), ("requires_human", ["y", "n"])]:
            if values.get(column) not in allowed:
                raise ValueError(f"item {n}: {column} is missing or not an allowed value")
        labels.append({"key": str(n), "category": values["category"], "urgency": values["urgency"],
                       "requires_human": values["requires_human"] == "y", "ambiguous": values.get("ambiguous") == "y"})
    if not labels:
        raise ValueError("no labeled items")
    return labels


def macro_f1(truth: list, predicted: list) -> float:
    """Mean F1 over the categories present in the human labels."""
    scores = []
    for c in sorted(set(truth)):
        tp = sum(t == c == p for t, p in zip(truth, predicted))
        denominator = sum(t == c for t in truth) + sum(p == c for p in predicted)
        scores.append(2 * tp / denominator if denominator else 0.0)
    return float(np.mean(scores))


def bootstrap_ci(pairs: list, metric) -> list:
    """95% percentile interval, resampling records."""
    rng = np.random.default_rng(SEED)
    values = []
    for _ in range(N_BOOT):
        sample = [pairs[i] for i in rng.integers(0, len(pairs), len(pairs))]
        value = metric(sample)
        if value is not None:
            values.append(value)
    return [round(float(v), 3) for v in np.percentile(values, [2.5, 97.5])] if values else None


def binary(truth: list, predicted: list) -> dict:
    tp = sum(t and p for t, p in zip(truth, predicted)); fp = sum(p and not t for t, p in zip(truth, predicted))
    fn = sum(t and not p for t, p in zip(truth, predicted)); tn = len(truth) - tp - fp - fn

    def recall(pairs):
        positives = [p for t, p in pairs if t]
        return sum(positives) / len(positives) if positives else None
    return {"n": len(truth), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None, "recall_ci95": bootstrap_ci(list(zip(truth, predicted)), recall) if truth else None,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "escalation_rate": round((tp + fp) / len(truth), 3) if truth else None}


def score(labels: list, results: dict) -> dict:
    missing = [l["key"] for l in labels if l["key"] not in results]
    if missing:
        raise ValueError("some labeled items have no model result")
    rows = [(l, results[l["key"]]) for l in labels]
    if any(lost_to_transport({"errors": [], **r}) for _, r in rows):
        raise ValueError("some results were lost to a server failure: rerun the batch before scoring")
    handled = [(l, r) for l, r in rows if r["route"] == "model"]
    out = {"n_labeled": len(rows), "routes": dict(Counter(r["route"] for _, r in rows)), "n_ambiguous": sum(l["ambiguous"] for l, _ in rows),
           "human_category_counts": dict(Counter(l["category"] for l, _ in rows)), "human_urgency_counts": dict(Counter(l["urgency"] for l, _ in rows)),
           "human_requires_human_yes": sum(l["requires_human"] for l, _ in rows)}
    if handled:
        truth, predicted = [l["category"] for l, _ in handled], [r["category"] for _, r in handled]
        pairs = list(zip(truth, predicted))
        majority = Counter(l["category"] for l, _ in rows).most_common(1)[0][0]
        out["category_model_handled"] = {
            "n": len(pairs), "correct": sum(t == p for t, p in pairs), "accuracy": round(sum(t == p for t, p in pairs) / len(pairs), 3),
            "accuracy_ci95": bootstrap_ci(pairs, lambda s: sum(t == p for t, p in s) / len(s)),
            "macro_f1": round(macro_f1(truth, predicted), 3), "macro_f1_ci95": bootstrap_ci(pairs, lambda s: macro_f1(*map(list, zip(*s)))),
            "majority_baseline": {"category": majority, "accuracy": round(sum(t == majority for t in truth) / len(truth), 3)},
            "confusion_human_to_model": {t: dict(Counter(p for a, p in pairs if a == t)) for t in sorted(set(truth))}}
        gap = [URGENCY.index(r["urgency"]) - URGENCY.index(l["urgency"]) for l, r in handled]
        out["urgency_model_handled"] = {"n": len(gap), "exact": sum(g == 0 for g in gap), "within_one": sum(abs(g) <= 1 for g in gap),
                                        "model_higher": sum(g > 0 for g in gap), "model_lower": sum(g < 0 for g in gap),
                                        "human_high_model_low": sum(g == -2 for g in gap)}
    truth_all = [l["requires_human"] for l, _ in rows]
    out["requires_human"] = {
        "end_to_end_all": binary(truth_all, [r["requires_human"] for _, r in rows]),
        "model_handled_final": binary([l["requires_human"] for l, _ in handled], [r["requires_human"] for _, r in handled]),
        "model_handled_model_alone": binary([l["requires_human"] for l, _ in handled], [r["model_requires_human"] for _, r in handled]),
        "baseline_rules_and_flags_no_model": binary(truth_all, [bool(r["safety_rules"]) or r["flagged"] for _, r in rows]),
        "baseline_always_escalate": binary(truth_all, [True] * len(rows))}
    out["flag_only_workload_among_human_no"] = sum(r["flagged"] and not l["requires_human"] for l, r in rows)
    return out


def score_dev(cases: list, results: dict) -> dict:
    labels = [{"key": c["id"], "ambiguous": False, **c["expected"]} for c in cases]
    return score(labels, results)


def score_adversarial(cases: list, results: dict) -> dict:
    report = []
    for case in cases:
        r, checks = results[case["id"]], {}
        for name, want in case["expected"].items():
            if name == "urgency_not":
                checks[f"urgency is not {want}"] = r["urgency"] != want
            else:
                checks[f"{name} = {want}"] = r[name] == want
        report.append({"id": case["id"], "tests": case["tests"], "passed": all(checks.values()), "checks": checks,
                       "got": {k: r[k] for k in ("route", "category", "urgency", "requires_human", "model_requires_human", "safety_rules")}})
    return {"cases": len(report), "passed": sum(c["passed"] for c in report), "report": report}


def write_summary_sheet(labels: list, results: dict, folder: Path, sanitized_by_key: dict, k: int = 10) -> int:
    """After labeling only: k random model-handled summaries beside the sanitized text, in LOCAL files."""
    handled = [l["key"] for l in labels if results[l["key"]]["route"] == "model"]
    chosen = random.Random(f"{SEED}-summary").sample(handled, min(k, len(handled)))
    text = "".join(f"=== SUMMARY {n} ===\nSUMMARY: {results[key]['summary']}\n--- complaint ---\n{sanitized_by_key[key]}\n\n" for n, key in enumerate(chosen, 1))
    for name, content in [("summary_check.txt", text), ("summary_ratings.csv", "summary,rating\n" + "".join(f"{n},\n" for n in range(1, len(chosen) + 1)))]:
        with open(folder / name, "x", encoding="utf-8") as f:
            f.write(content)
        (folder / name).chmod(0o600)
    return len(chosen)


def read_ratings(path: Path) -> dict:
    allowed = ["faithful", "minor_omission", "unsupported"]
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        ratings = [(r.get("rating") or "").strip().lower() for r in csv.DictReader(f)]
    filled = [r for r in ratings if r]
    if any(r not in allowed for r in filled):
        raise ValueError("a rating is not faithful, minor_omission or unsupported")
    return {"rated": len(filled), "of": len(ratings), **{a: filled.count(a) for a in allowed}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("what", choices=["dev", "adversarial", "labels", "summary-sheet"])
    ap.add_argument("--prompt", default=FINAL_PROMPT); ap.add_argument("--zip", default="data/raw/CCDB_Export_19_June_2026.zip")
    args = ap.parse_args(argv)
    try:
        if args.what in SYNTHETIC:
            cases = [json.loads(line) for line in SYNTHETIC[args.what].read_text().splitlines() if line.strip()]
            results = read_results(RUNS / f"{args.what}_{args.prompt}" / "results.jsonl")
            out = (score_dev if args.what == "dev" else score_adversarial)(cases, results)
            path = ROOT / "outputs" / f"m6_{args.what}_{args.prompt}.json"
        else:
            from part_b.freeze_plan import verify_freeze
            version = verify_freeze()["version"]
            labels, results = read_labels(LABELS), read_results(RUNS / f"eval_{args.prompt}" / "results.jsonl")
            if args.what == "summary-sheet":
                from part_b.run_triage import load_real
                records, sanitize_fn = load_real("eval", args.zip)
                wanted = {l["key"] for l in labels}
                n = write_summary_sheet(labels, results, LABELS.parent, {key: sanitize_fn(raw) for key, raw in records if key in wanted})
                print(f"wrote {n} summaries to data/processed/labeling/summary_check.txt and summary_ratings.csv")
                return 0
            out = {"prompt": args.prompt, "freeze_version": version, "labels_sha256": hashlib.sha256(LABELS.read_bytes()).hexdigest(), **score(labels, results)}
            ratings = LABELS.parent / "summary_ratings.csv"
            out["summary_faithfulness"] = read_ratings(ratings) if ratings.is_file() else "not done"
            path = ROOT / "outputs" / "m6_eval_metrics.json"
    except ValueError as e:                                       # our messages contain no data
        print(f"FAIL: {e}"); return 1
    except Exception as e:
        print(f"FAIL: {type(e).__name__} (details suppressed)"); return 1
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
