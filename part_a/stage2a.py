"""M2 Stage 2a: XGBoost vs logistic baseline, train-OOF Platt calibration, cost analysis, freeze.

Uses TRAIN and VALIDATION only. The test split is never sliced here (only its start time is read from the Time column).
Run from repo root:  python -m part_a.stage2a
Stage 2b (single test evaluation) is a separate script run only after explicit approval.
"""
import hashlib
import json
import platform
import sys

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss

from config import OUTPUTS, ROOT, SEED
from part_a.data import CSV, FEATURES, TARGET, load, split_cuts, time_chunks
from part_a.evaluate import threshold_for_precision
from part_a.train import build_baseline

# ---- predeclared before any result was seen ----
PRIMARY_SEED = SEED            # 42: used for comparison, OOF calibration, frozen model, and the eventual test run
ROBUSTNESS_SEEDS = [43, 44]    # reported only; never used to pick the primary
N_CHUNKS = 5                   # expanding-window folds inside train: fit on chunks[:k], predict chunk k, k=1..4
REVIEW_COST_BASE = 5.0         # HYPOTHETICAL, euros per flagged transaction (not a PayGuard figure)
REVIEW_COST_SENSITIVITY = [1.0, 25.0]
XGB_PARAMS = dict(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                  tree_method="hist", n_jobs=1)  # untuned; n_jobs=1 for determinism
# Calibration adequacy on validation (predeclared): sum(p)/observed frauds in [0.67, 1.5], AND among rows with
# calibrated p >= 0.1, observed rate / mean predicted within [0.5, 2].
ADEQUACY = {"expected_vs_observed_ratio": [0.67, 1.5], "high_bin_p_min": 0.1, "high_bin_obs_over_pred": [0.5, 2.0]}
FROZEN_DIR = ROOT / "part_a" / "frozen"


# ---------- models ----------
def fit_logreg(d):
    return build_baseline().fit(d[FEATURES], d[TARGET])


def fit_xgb(d, seed):
    y = d[TARGET]
    spw = float((y == 0).sum() / (y == 1).sum())  # same imbalance treatment as class_weight="balanced"
    return xgb.XGBClassifier(scale_pos_weight=spw, random_state=seed, **XGB_PARAMS).fit(d[FEATURES], y)


def margin(model, X):
    """Raw log-odds-like score (pre-sigmoid). Platt is fit on this, so no clipping of saturated probabilities."""
    if hasattr(model, "decision_function"):
        return model.decision_function(X)
    return model.predict(X, output_margin=True)


# ---------- calibration ----------
def oof_margins(fit, train):
    """Expanding-window out-of-fold margins on train. Returns margins, labels, and a fold table."""
    chunks = time_chunks(train, N_CHUNKS)
    ms, ys, table = [], [], []
    for k in range(1, N_CHUNKS):
        tr, te = pd.concat(chunks[:k]), chunks[k]
        m = fit(tr)
        ms.append(margin(m, te[FEATURES])); ys.append(te[TARGET].to_numpy())
        table.append({"fold": k, "fit_time": [float(tr.Time.min()), float(tr.Time.max())], "fit_rows": len(tr),
                      "fit_frauds": int(tr[TARGET].sum()), "pred_time": [float(te.Time.min()), float(te.Time.max())],
                      "pred_rows": len(te), "pred_frauds": int(te[TARGET].sum())})
    return np.concatenate(ms), np.concatenate(ys), table


def fit_platt(m, y):
    return LogisticRegression(penalty=None, max_iter=1000).fit(m.reshape(-1, 1), y)


def calib_diagnostics(y, p):
    y, p = np.asarray(y), np.asarray(p)
    d = {"sum_p": float(p.sum()), "observed_frauds": int(y.sum()), "ratio_expected_over_observed": float(p.sum() / y.sum()),
         "brier": float(brier_score_loss(y, p)), "log_loss": float(log_loss(y, p, labels=[0, 1])), "bins": []}
    for lo, hi in [(0, 1e-3), (1e-3, 1e-2), (1e-2, 0.1), (0.1, 0.5), (0.5, 1.0001)]:
        mk = (p >= lo) & (p < hi)
        if mk.any():
            d["bins"].append({"bin": f"[{lo},{min(hi, 1)})", "n": int(mk.sum()), "frauds": int(y[mk].sum()),
                              "mean_pred": float(p[mk].mean()), "observed_rate": float(y[mk].mean())})
    hi_mk = p >= ADEQUACY["high_bin_p_min"]
    r_ok = ADEQUACY["expected_vs_observed_ratio"][0] <= d["ratio_expected_over_observed"] <= ADEQUACY["expected_vs_observed_ratio"][1]
    if hi_mk.any():
        ratio_hi = float(y[hi_mk].mean() / p[hi_mk].mean())
        hi_ok = ADEQUACY["high_bin_obs_over_pred"][0] <= ratio_hi <= ADEQUACY["high_bin_obs_over_pred"][1]
    else:
        ratio_hi, hi_ok = None, False
    d.update({"high_bin_obs_over_pred": ratio_hi, "adequate": bool(r_ok and hi_ok)})
    return d


# ---------- costs ----------
def total_cost(y, amount, flag, c):
    """c per flagged transaction (true or false alert) + Amount of every missed (unflagged) fraud."""
    y, amount, flag = np.asarray(y), np.asarray(amount), np.asarray(flag, dtype=bool)
    return float(c * flag.sum() + amount[(y == 1) & ~flag].sum())


def policy_row(y, amount, flag, c):
    y, flag = np.asarray(y), np.asarray(flag, dtype=bool)
    tp, fp = int((flag & (y == 1)).sum()), int((flag & (y == 0)).sum())
    return {"flagged": int(flag.sum()), "tp": tp, "fp": fp, "fn": int(y.sum()) - tp, "cost": total_cost(y, amount, flag, c)}


def min_cost_in_sample(y, amount, scores, c):
    """In-sample reference only: best top-k cutoff by realized validation cost (ignores score ties)."""
    order = np.argsort(-scores, kind="stable")
    y_o, a_o = np.asarray(y)[order], np.asarray(amount)[order]
    caught = np.cumsum(np.where(y_o == 1, a_o, 0.0))
    total_missed = a_o[y_o == 1].sum()
    k = np.arange(1, len(y_o) + 1)
    cost = c * k + total_missed - caught
    best = int(np.argmin(cost))
    return {"top_k": best + 1, "cost": float(cost[best])}


def paired_bootstrap_diff(y, s_a, s_b, n_boot=1000, seed=PRIMARY_SEED):
    y, s_a, s_b = map(np.asarray, (y, s_a, s_b))
    rng = np.random.default_rng(seed)
    diffs = []
    while len(diffs) < n_boot:
        i = rng.integers(0, len(y), len(y))
        if y[i].sum() == 0:
            continue
        diffs.append(average_precision_score(y[i], s_a[i]) - average_precision_score(y[i], s_b[i]))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {"mean_diff": float(np.mean(diffs)), "ci95": [float(lo), float(hi)], "frac_positive": float(np.mean(np.array(diffs) > 0))}


# ---------- pipeline ----------
def run_model(fit, train, val):
    m_oof, y_oof, folds = oof_margins(fit, train)
    platt = fit_platt(m_oof, y_oof)
    model = fit(train)
    val_m = margin(model, val[FEATURES])
    val_p = platt.predict_proba(val_m.reshape(-1, 1))[:, 1]
    return {"model": model, "platt": platt, "folds": folds, "oof_prev": float(y_oof.mean()), "oof_n": len(y_oof),
            "val_margin": val_m, "val_p": val_p}


def evaluate_val(r, val, mean_fraud_amt):
    y, amt = val[TARGET].to_numpy(), val["Amount"].to_numpy()
    out = {"pr_auc": float(average_precision_score(y, r["val_margin"])), "calibration": calib_diagnostics(y, r["val_p"]), "cost": {}}
    thr90 = threshold_for_precision(y, r["val_p"], 0.90)
    for c in [REVIEW_COST_BASE] + REVIEW_COST_SENSITIVITY:
        p_thr = c / mean_fraud_amt  # Rule B: amount-agnostic, derived from assumptions + TRAIN data only
        entry = {"rule_B_p_gt_c_over_mean_fraud_amount": {**policy_row(y, amt, r["val_p"] > p_thr, c), "p_threshold": float(p_thr)},
                 "rule_A_REJECTED_p_times_amount_gt_c": policy_row(y, amt, r["val_p"] * amt > c, c),
                 "ref_precision90_threshold_INSAMPLE": policy_row(y, amt, r["val_p"] >= thr90, c) if thr90 is not None else None,
                 "ref_min_cost_cutoff_INSAMPLE": min_cost_in_sample(y, amt, r["val_p"], c),
                 "flag_nothing_cost": total_cost(y, amt, np.zeros(len(y), bool), c)}
        out["cost"][str(c)] = entry
    return out


def sha256_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    df = load()
    t_val, t_test = split_cuts(df)  # reads the Time column only
    train = df[df["Time"] < t_val]  # same rule as time_split, but the test frame is never constructed here
    val = df[(df["Time"] >= t_val) & (df["Time"] < t_test)]
    mean_fraud_amt = float(train.loc[train[TARGET] == 1, "Amount"].mean())  # TRAIN only
    results = {"primary_seed": PRIMARY_SEED, "mean_fraud_amount_train": mean_fraud_amt}

    primary = {"logreg": run_model(fit_logreg, train, val),
               "xgboost": run_model(lambda d: fit_xgb(d, PRIMARY_SEED), train, val)}
    results["models"] = {k: evaluate_val(v, val, mean_fraud_amt) for k, v in primary.items()}
    results["folds"] = primary["xgboost"]["folds"]
    results["calibration_fit_prevalence_oof"] = primary["xgboost"]["oof_prev"]
    results["prevalence"] = {"train": float(train[TARGET].mean()), "oof_calibration_region": primary["xgboost"]["oof_prev"],
                             "validation": float(val[TARGET].mean())}
    results["paired_bootstrap_pr_auc_xgb_minus_logreg"] = paired_bootstrap_diff(
        val[TARGET], primary["xgboost"]["val_margin"], primary["logreg"]["val_margin"])

    # robustness seeds: XGBoost only (logistic regression is deterministic); never used to choose the primary
    rob = {}
    for s in ROBUSTNESS_SEEDS:
        r = run_model(lambda d, s=s: fit_xgb(d, s), train, val)
        e = evaluate_val(r, val, mean_fraud_amt)
        rob[str(s)] = {"pr_auc": e["pr_auc"], "calib_ratio": e["calibration"]["ratio_expected_over_observed"],
                       "adequate": e["calibration"]["adequate"], "cost_c5_rule": e["cost"][str(REVIEW_COST_BASE)]["rule_B_p_gt_c_over_mean_fraud_amount"]["cost"]}
    results["xgb_robustness_seeds"] = rob

    adequate = all(v["calibration"]["adequate"] for v in results["models"].values())
    results["calibration_adequate_all_models"] = adequate
    OUTPUTS.mkdir(exist_ok=True)
    (OUTPUTS / "m2_stage2a_results.json").write_text(json.dumps(results, indent=2))

    if not adequate:
        print(json.dumps(results, indent=2))
        print("\nCALIBRATION INADEQUATE under the predeclared criterion: NOT freezing. Pausing for review.")
        return

    FROZEN_DIR.mkdir(exist_ok=True)
    joblib.dump(primary["logreg"]["model"], FROZEN_DIR / "logreg_baseline.joblib")
    primary["xgboost"]["model"].save_model(FROZEN_DIR / "xgb_primary.json")
    code_files = ["part_a/data.py", "part_a/evaluate.py", "part_a/train.py", "part_a/stage2a.py"]
    body = {
        "stage": "M2 stage 2a freeze", "config_version": "v3",
        "dataset": {"file": "data/raw/creditcard.csv", "sha256": sha256_file(CSV), "dedupe_exact_duplicates": True,
                    "rows_after_dedupe": len(df)},
        "features": FEATURES, "target": TARGET,
        "split": {"rule": "sort by Time (stable); cut at Time values found at 70% and 85% row positions; ties go to the later split",
                  "validation_starts_at_time": float(t_val), "test_starts_at_time": float(t_test),
                  "train_rows": len(train), "train_frauds": int(train[TARGET].sum()),
                  "val_rows": len(val), "val_frauds": int(val[TARGET].sum()),
                  "test": "not accessed during Stage 2a (only its start time is read from the Time column)"},
        "preprocessing": {"logreg": "StandardScaler fit on the data passed to fit (train only) inside a Pipeline",
                          "xgboost": "none (tree model; scale-invariant)"},
        "models": {"logreg": {"class": "LogisticRegression(class_weight='balanced', max_iter=1000)", "file": "logreg_baseline.joblib",
                              "sha256": sha256_file(FROZEN_DIR / "logreg_baseline.joblib"), "seed": "n/a (deterministic)"},
                   "xgboost": {"params": XGB_PARAMS, "scale_pos_weight": "negatives/positives of the training data it is fit on",
                               "seed": PRIMARY_SEED, "file": "xgb_primary.json", "sha256": sha256_file(FROZEN_DIR / "xgb_primary.json")}},
        "seeds": {"primary": PRIMARY_SEED, "robustness_only_not_used_for_test": ROBUSTNESS_SEEDS},
        "calibration": {"method": "Platt (sigmoid) on raw margin, fit on train out-of-fold scores",
                        "folds": results["folds"], "oof_rows": primary["xgboost"]["oof_n"],
                        "coefficients": {k: {"slope": float(v["platt"].coef_[0, 0]), "intercept": float(v["platt"].intercept_[0])}
                                         for k, v in primary.items()}},
        "decision_rules": {
            "rule_A": {
                "formula": "flag if calibrated_p * Amount > c",
                "role": "Original decision rule, specified in the approved M2 proposal before any Stage 2a result was computed (the v1 config file itself was written by the same run that first computed validation results). Primary comparator.",
                "assumptions": ["calibrated fraud probability", "constant review cost c per flagged transaction (hypothetical)",
                                "a flagged fraud is fully prevented (loss avoided = Amount)"],
                "known_limits_from_validation": "Calibration had only been checked in aggregate. A later validation-only diagnostic "
                    "(outputs/m2_validation_amount_band_calibration.json) showed over-prediction in Amount bands above EUR 10, which "
                    "p*Amount amplifies. At c=5 it cost XGBoost EUR 1,726 on validation vs ~EUR 630 for in-sample reference cutoffs."},
            "rule_B": {
                "formula": "flag if calibrated_p > c / mean_fraud_amount_train",
                "role": "Validation-informed, secondary operating-policy alternative. NOT independently pre-registered. "
                        "An AVERAGE-LOSS APPROXIMATION, not a transaction-specific expected-cost calculation: it treats every missed "
                        "fraud as costing the same constant amount.",
                "selection_informed_by_validation": True,
                "thresholds_tuned_on_validation": False,
                "claim": "No claim of theoretical superiority over Rule A; Rule A is the principled rule under its own assumptions.",
                "mean_fraud_amount_train_eur": mean_fraud_amt,
                "p_thresholds_by_c": {str(c): c / mean_fraud_amt for c in [REVIEW_COST_BASE] + REVIEW_COST_SENSITIVITY},
                "assumptions": ["calibrated fraud probability (aggregate only)", "constant review cost c (hypothetical)",
                                "every missed fraud costs the TRAIN mean fraud Amount (real fraud sizes are highly skewed)",
                                "a flagged fraud is fully prevented"],
                "known_limits": "Cannot distinguish a small from a large transaction at equal p; depends entirely on the hypothetical c "
                                "and on a mean from 2013 European data; at low c its threshold sits where calibration is weakest."},
            "test_protocol": "Both rules are deterministic functions of the frozen scores and are evaluated on the test set once; "
                             "neither is chosen using test results."},
        "config_history": [
            {"version": "v1", "sha256": (FROZEN_DIR / "superseded_v1_config.sha256").read_text().strip(),
             "content": "Rule A only. Written by the same run that first produced validation results; the rule itself had been specified in the approved proposal beforehand."},
            {"version": "v2", "sha256": (FROZEN_DIR / "superseded_v2_config.sha256").read_text().strip(),
             "content": "Rule A replaced by Rule B after validation results (user decision D-09); validation-informed"},
            {"version": "v3", "content": "Both rules retained with the roles above (user decision D-10). Models, calibration, features, "
                                         "splits, seeds and parameters unchanged from v1 and v2."}],
        "cost_definition": "total = c * (number flagged, true or false alerts) + sum(Amount of every missed, unflagged fraud)",
        "costs": {"currency": "EUR (matches dataset Amount); ALL VALUES HYPOTHETICAL, not PayGuard operating costs",
                  "review_cost_base": REVIEW_COST_BASE, "review_cost_sensitivity": REVIEW_COST_SENSITIVITY},
        "calibration_adequacy_criterion": ADEQUACY,
        "software": {"python": sys.version.split()[0], "platform": platform.platform(), "numpy": np.__version__,
                     "pandas": pd.__version__, "scikit-learn": sklearn.__version__, "xgboost": xgb.__version__, "joblib": joblib.__version__},
        "code_sha256": {f: sha256_file(ROOT / f) for f in code_files},
    }
    text = json.dumps(body, indent=2, sort_keys=True)
    (FROZEN_DIR / "m2_frozen_config.json").write_text(text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    (FROZEN_DIR / "m2_frozen_config.sha256").write_text(digest + "\n")
    print(json.dumps(results, indent=2))
    print("\nFROZEN. config sha256:", digest)


if __name__ == "__main__":
    main()
