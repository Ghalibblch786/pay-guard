"""Checks added AFTER the scores were seen (not in the frozen plan). Aggregates only.

  python -m part_b.posthoc_checks
"""
import json
from collections import Counter
from pathlib import Path

from part_b.evaluate_triage import LABELS, ROOT, macro_f1, read_labels, read_results
from part_b.run_triage import FINAL_PROMPT, RUNS


def wilson_lower(successes: int, n: int, z: float = 1.96) -> float:
    """Lower end of the 95% Wilson interval. Unlike a bootstrap, it stays informative with zero misses."""
    p = successes / n
    centre = p + z * z / (2 * n)
    spread = z * ((p * (1 - p) + z * z / (4 * n)) / n) ** 0.5
    return (centre - spread) / (1 + z * z / n)


def main() -> None:
    labels = read_labels(LABELS)
    evaluation = read_results(RUNS / f"eval_{FINAL_PROMPT}" / "results.jsonl")
    handled = [l for l in labels if evaluation[l["key"]]["route"] == "model"]
    truth = [l["category"] for l in handled]
    top_category = Counter(l["category"] for l in labels).most_common(1)[0][0]
    top_urgency, top_urgency_hits = Counter(l["urgency"] for l in handled).most_common(1)[0]
    positives = [l for l in labels if l["requires_human"]]
    caught = sum(evaluation[l["key"]]["requires_human"] for l in positives)

    main_rows = list(read_results(RUNS / f"main_{FINAL_PROMPT}" / "results.jsonl").values())
    model_rows = [r for r in main_rows if r["route"] == "model"]
    out = {
        "note": "post hoc: added after the frozen-plan scores were seen",
        "evaluation": {
            "recall_wilson_lower95": round(wilson_lower(caught, len(positives)), 3),
            "majority_category_macro_f1": round(macro_f1(truth, [top_category] * len(truth)), 3),
            "majority_urgency_baseline": {"urgency": top_urgency, "correct": top_urgency_hits, "n": len(handled)},
        },
        "main_run_operational": {
            "records": len(main_rows),
            "final_requires_human": sum(r["requires_human"] for r in main_rows),
            "model_handled": len(model_rows),
            "model_alone_requires_human": sum(r["model_requires_human"] is True for r in model_rows),
            "rules_or_flags_without_model": sum(bool(r["safety_rules"]) or r["flagged"] for r in main_rows),
            "model_category_counts": dict(Counter(r["category"] for r in model_rows)),
            "model_urgency_counts": dict(Counter(r["urgency"] for r in model_rows)),
        },
    }
    (ROOT / "outputs" / "m6_posthoc_checks.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
