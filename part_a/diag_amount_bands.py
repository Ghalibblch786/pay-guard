"""Validation-ONLY diagnostic: calibration within transaction-Amount bands, using the frozen models.
Does not read the test split. Run after part_a.stage2a:  python -m part_a.diag_amount_bands
"""
import json

import joblib
import numpy as np
import xgboost as xgb

from config import OUTPUTS, ROOT
from part_a.data import FEATURES, TARGET, load, split_cuts

FROZEN = ROOT / "part_a" / "frozen"
BANDS = [(0, 10), (10, 100), (100, 1000), (1000, float("inf"))]


def main():
    df = load()
    t_val, t_test = split_cuts(df)
    val = df[(df["Time"] >= t_val) & (df["Time"] < t_test)]
    coef = json.loads((FROZEN / "m2_frozen_config.json").read_text())["calibration"]["coefficients"]
    xm = xgb.XGBClassifier(); xm.load_model(FROZEN / "xgb_primary.json")
    margins = {"xgboost": xm.predict(val[FEATURES], output_margin=True),
               "logreg": joblib.load(FROZEN / "logreg_baseline.joblib").decision_function(val[FEATURES])}
    y, a = val[TARGET].to_numpy(), val["Amount"].to_numpy()
    out = {}
    for name, m in margins.items():
        p = 1 / (1 + np.exp(-(coef[name]["slope"] * m + coef[name]["intercept"])))
        rows = []
        for lo, hi in BANDS:
            k = (a >= lo) & (a < hi)
            rows.append({"amount_band": f"[{lo},{hi})", "n": int(k.sum()), "expected_frauds": float(p[k].sum()),
                         "actual_frauds": int(y[k].sum()), "expected_loss_eur": float((p * a)[k].sum()),
                         "actual_fraud_eur": float(a[k & (y == 1)].sum())})
        out[name] = rows
    (OUTPUTS / "m2_validation_amount_band_calibration.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
