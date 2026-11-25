"""M2 Stage 2b: single evaluation of the frozen v3 configuration.

  python -m part_a.final_test --split val    # dry run on VALIDATION (code check; must reproduce Stage 2a numbers)
  python -m part_a.final_test --split test   # THE single test evaluation; refuses to run twice

Nothing is fit, tuned or recalibrated here: models, Platt coefficients, rules and costs are all loaded from the frozen config.
"""
import argparse
import hashlib
import json

import joblib
import numpy as np
import xgboost as xgb
from sklearn.metrics import average_precision_score, roc_auc_score

from config import OUTPUTS, ROOT, SEED
from part_a.data import CSV, FEATURES, TARGET, load, split_cuts
from part_a.evaluate import pr_auc_with_ci
from part_a.stage2a import calib_diagnostics, paired_bootstrap_diff, sha256_file, total_cost

FROZEN = ROOT / "part_a" / "frozen"
TEST_RESULTS = OUTPUTS / "m2_test_results.json"
BANDS = [(0, 10), (10, 100), (100, 1000), (1000, float("inf"))]


def verify_frozen():
    """Abort unless every frozen artifact matches the recorded hashes."""
    text = (FROZEN / "m2_frozen_config.json").read_text()
    digest = hashlib.sha256(text.encode()).hexdigest()
    stored = (FROZEN / "m2_frozen_config.sha256").read_text().strip()
    assert digest == stored, f"config hash mismatch: {digest} != {stored}"
    cfg = json.loads(text)
    assert cfg["config_version"] == "v3"
    assert sha256_file(CSV) == cfg["dataset"]["sha256"], "dataset hash mismatch"
    for name in ("logreg", "xgboost"):
        f = FROZEN / cfg["models"][name]["file"]
        assert sha256_file(f) == cfg["models"][name]["sha256"], f"{name} model hash mismatch"
    for f, h in cfg["code_sha256"].items():
        assert sha256_file(ROOT / f) == h, f"code changed since freeze: {f}"
    return cfg, digest


def policy(y, amt, p, rule, c, cfg):
    if rule == "A":
        return p * amt > c
    return p > c / cfg["decision_rules"]["rule_B"]["mean_fraud_amount_train_eur"]


def cost_ci(y, amt, flag, c, rng, n_boot=1000):
    cs = []
    for _ in range(n_boot):
        i = rng.integers(0, len(y), len(y))
        cs.append(total_cost(y[i], amt[i], flag[i], c))
    return [float(v) for v in np.percentile(cs, [2.5, 97.5])]


def evaluate_split(df, cfg):
    y, amt = df[TARGET].to_numpy(), df["Amount"].to_numpy()
    lr = joblib.load(FROZEN / cfg["models"]["logreg"]["file"])
    xm = xgb.XGBClassifier(); xm.load_model(FROZEN / cfg["models"]["xgboost"]["file"])
    margins = {"logreg": lr.decision_function(df[FEATURES]), "xgboost": xm.predict(df[FEATURES], output_margin=True)}
    co = cfg["calibration"]["coefficients"]
    probs = {k: 1 / (1 + np.exp(-(co[k]["slope"] * m + co[k]["intercept"]))) for k, m in margins.items()}
    cs = [cfg["costs"]["review_cost_base"]] + cfg["costs"]["review_cost_sensitivity"]
    rng = np.random.default_rng(SEED)
    out = {"n": int(len(y)), "n_fraud": int(y.sum()), "base_rate": float(y.mean()), "total_fraud_eur": float(amt[y == 1].sum()),
           "flag_nothing_cost": total_cost(y, amt, np.zeros(len(y), bool), 0.0), "models": {}}
    for k in ("logreg", "xgboost"):
        pr, lo, hi = pr_auc_with_ci(y, margins[k])
        m = {"pr_auc": pr, "pr_auc_ci95": [lo, hi], "roc_auc_secondary": float(roc_auc_score(y, margins[k])),
             "calibration": calib_diagnostics(y, probs[k]), "rules": {}, "amount_band_calibration_descriptive": []}
        for lo_b, hi_b in BANDS:
            kk = (amt >= lo_b) & (amt < hi_b)
            m["amount_band_calibration_descriptive"].append({"band": f"[{lo_b},{hi_b})", "n": int(kk.sum()), "expected_frauds": float(probs[k][kk].sum()),
                                                             "actual_frauds": int(y[kk].sum())})
        for rule in ("A", "B"):
            for c in cs:
                flag = policy(y, amt, probs[k], rule, c, cfg)
                tp, fp = int((flag & (y == 1)).sum()), int((flag & (y == 0)).sum())
                fn = int(y.sum()) - tp; tn = len(y) - tp - fp - fn
                m["rules"][f"rule_{rule}_c={c}"] = {
                    "flagged": int(flag.sum()), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                    "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn),
                    "cost": total_cost(y, amt, flag, c), "cost_ci95_bootstrap": cost_ci(y, amt, flag, c, rng),
                    "saving_vs_flag_nothing": out["flag_nothing_cost"] - total_cost(y, amt, flag, c)}
        out["models"][k] = m
    out["paired_bootstrap_pr_auc_xgb_minus_logreg"] = paired_bootstrap_diff(y, margins["xgboost"], margins["logreg"])
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--split", choices=["val", "test"], required=True)
    split = ap.parse_args().split
    if split == "test" and TEST_RESULTS.exists():
        raise SystemExit("Test results already exist: the test set is evaluated ONCE. Refusing to run again.")
    cfg, digest = verify_frozen()
    df = load()
    t_val, t_test = split_cuts(df)
    assert float(t_val) == cfg["split"]["validation_starts_at_time"] and float(t_test) == cfg["split"]["test_starts_at_time"]
    part = df[(df["Time"] >= t_val) & (df["Time"] < t_test)] if split == "val" else df[df["Time"] >= t_test]
    res = {"config_sha256": digest, "split": split, **evaluate_split(part, cfg)}
    path = TEST_RESULTS if split == "test" else OUTPUTS / "m2_dryrun_val.json"
    path.write_text(json.dumps(res, indent=2))
    print(f"verified config {digest[:16]}...; wrote {path.name}")


if __name__ == "__main__":
    main()
