"""M1: baseline fraud model. Fit on train, evaluate on VALIDATION only (test is untouched until M2).

Run from repo root:  python -m part_a.train
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from config import OUTPUTS, SEED
from part_a.data import FEATURES, TARGET, load, time_split
from part_a.evaluate import calibration_summary, report_at_threshold, summarize, threshold_for_precision


def build_baseline():
    """Scaler + class-weighted logistic regression in one Pipeline, so the scaler is fit on
    whatever data .fit() receives (train only) and cannot leak val/test statistics."""
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(class_weight="balanced", max_iter=1000, random_state=SEED),
    )


def main():
    train, val, _test = time_split(load())  # _test deliberately unused in M1
    model = build_baseline().fit(train[FEATURES], train[TARGET])
    val_scores = model.predict_proba(val[FEATURES])[:, 1]

    results = {"val": summarize(val[TARGET], val_scores)}
    thr = threshold_for_precision(val[TARGET], val_scores, min_precision=0.90)
    results["threshold_precision>=0.90 (chosen on val)"] = (
        report_at_threshold(val[TARGET], val_scores, thr) if thr is not None else "no threshold reaches 90% precision"
    )
    results["calibration_val"] = calibration_summary(val[TARGET], val_scores)

    OUTPUTS.mkdir(exist_ok=True)
    (OUTPUTS / "m1_baseline_metrics.json").write_text(json.dumps(results, indent=2))

    prec, rec, _ = precision_recall_curve(val[TARGET], val_scores)
    plt.figure(figsize=(5, 4))
    plt.plot(rec, prec)
    plt.axhline(val[TARGET].mean(), ls="--", c="gray", label="no-skill (base rate)")
    plt.xlabel("Recall"); plt.ylabel("Precision"); plt.title("Baseline LogReg, validation")
    plt.legend(); plt.tight_layout(); plt.savefig(OUTPUTS / "m1_baseline_pr_curve.png", dpi=120)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
