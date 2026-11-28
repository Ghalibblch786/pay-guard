"""Logic behind the dashboard: load saved results, score a transaction, explain a decision. No screen code here.

Nothing is trained here. The fraud side uses the saved (frozen) model and VALIDATION transactions only; the test set is
never scored. Headline figures are read from the result files in outputs/, so the screen cannot drift from them.
"""
import hashlib
import json

import joblib
import numpy as np
import pandas as pd

from config import OUTPUTS, ROOT
from part_a.data import FEATURES, TARGET, load, split_cuts
from part_b.safety_rules import RULES
from part_b.sensitive_flags import detect_sensitive

FROZEN = ROOT / "part_a" / "frozen"
REVIEW_COSTS = ["5.0", "1.0", "25.0"]        # EUR, hypothetical; the first is the suggested setting

RULE_LABELS = {
    "fraud_allegation": "Mentions fraud, theft or a payment they did not approve",
    "legal_threat": "Mentions a lawyer or legal action",
    "regulator_escalation": "Mentions a regulator or public authority",
    "unlawful_conduct": "Alleges discrimination or law-breaking",
    "safety_self_harm": "Mentions personal safety or self-harm",
    "vulnerable_or_hardship": "Suggests a vulnerable person or serious hardship",
    "injection_suspected": "Contains text that tries to instruct the system",
}
SENSITIVE_LABELS = {
    "health_medical": "Health information",
    "minors": "Information about a child",
    "government_id": "Government ID",
    "financial_account_details": "Bank or card details",
    "credentials_authentication": "Password or security code",
    "immigration_legal_case": "Immigration or legal case",
    "self_harm_safety": "Self-harm or personal safety",
}


def read_json(name: str) -> dict:
    return json.loads((OUTPUTS / name).read_text())


# ---------------------------------------------------------------- headline figures

def fraud_summary() -> dict:
    """Saved single test-set evaluation of the suggested setting (logistic regression, Rule B, EUR 5)."""
    test = read_json("m2_test_results.json")
    rule = test["models"]["logreg"]["rules"]["rule_B_c=5.0"]
    return {"transactions": test["n"], "frauds": test["n_fraud"], "caught": rule["tp"], "missed": rule["fn"],
            "false_alarms": rule["fp"], "genuine": rule["fp"] + rule["tn"], "cost": rule["cost"],
            "cost_if_nothing_flagged": test["flag_nothing_cost"]}


def complaint_summary() -> dict:
    run, scored = read_json("m5_run_main_v3.json"), read_json("m6_eval_metrics.json")
    extra = read_json("m6_posthoc_checks.json")
    everything = scored["requires_human"]["end_to_end_all"]
    return {"processed": run["records"], "to_model": run["routes"]["model"], "sensitive": run["routes"]["flagged_human_only"],
            "sent_to_person": extra["main_run_operational"]["final_requires_human"],
            "labeled": scored["n_labeled"], "labeled_sent": everything["tp"] + everything["fp"],
            "labeled_needed": scored["human_requires_human_yes"],
            "category_right": scored["category_model_handled"]["correct"], "category_n": scored["category_model_handled"]["n"],
            "category_guess": round(scored["category_model_handled"]["majority_baseline"]["accuracy"] * scored["category_model_handled"]["n"]),
            "urgency_right": scored["urgency_model_handled"]["exact"],
            "urgency_guess": extra["evaluation"]["majority_urgency_baseline"]["correct"],
            "summaries": scored["summary_faithfulness"], "seconds": run["latency_s"]["mean"]}


# ---------------------------------------------------------------- fraud

def load_fraud() -> dict:
    """Saved model, frozen settings and the VALIDATION transactions. Raises FileNotFoundError without creditcard.csv."""
    config = json.loads((FROZEN / "m2_frozen_config.json").read_text())
    saved = FROZEN / config["models"]["logreg"]["file"]
    if hashlib.sha256(saved.read_bytes()).hexdigest() != config["models"]["logreg"]["sha256"]:
        raise ValueError("the saved model does not match the frozen record")   # a joblib file runs code when loaded
    model = joblib.load(saved)

    data = load()
    validation_start, test_start = split_cuts(data)
    validation = data[(data["Time"] >= validation_start) & (data["Time"] < test_start)].reset_index(drop=True)
    validation["probability"] = probabilities(model, config, validation)
    return {"model": model, "config": config, "validation": validation}


def probabilities(model, config: dict, rows: pd.DataFrame) -> np.ndarray:
    """Model score -> calibrated fraud probability, using the saved calibration."""
    cal = config["calibration"]["coefficients"]["logreg"]
    return 1 / (1 + np.exp(-(cal["slope"] * model.decision_function(rows[FEATURES]) + cal["intercept"])))


def threshold(config: dict, review_cost: str) -> float:
    """Rule B: flag when the probability is above review_cost / average fraud amount."""
    return config["decision_rules"]["rule_B"]["p_thresholds_by_c"][review_cost]


def explain_transaction(model, config: dict, row: pd.Series) -> tuple:
    """Exact breakdown for logistic regression. Returns (starting value, table of each field's push).

    log-odds of fraud = starting value + sum of pushes. The starting value is an average training transaction.
    A positive push raises the risk, a negative one lowers it.
    """
    scaler, regression = model[0], model[1]
    cal = config["calibration"]["coefficients"]["logreg"]
    scaled = scaler.transform(pd.DataFrame([row[FEATURES]], columns=FEATURES).astype(float))[0]
    pushes = cal["slope"] * regression.coef_[0] * scaled
    start = cal["slope"] * regression.intercept_[0] + cal["intercept"]
    table = pd.DataFrame({"field": [field_name(f) for f in FEATURES], "push": pushes})
    return float(start), table.sort_values("push", key=abs, ascending=False).reset_index(drop=True)


def field_name(feature: str) -> str:
    if feature == "Amount":
        return "Payment amount"
    if feature == "Time":
        return "Time since the data starts"
    return f"Hidden signal {feature}"


def example_transactions(validation: pd.DataFrame, limit: float) -> dict:
    """A few validation payments PICKED to show each kind of outcome. They are not a representative sample."""
    flagged, fraud = validation["probability"] > limit, validation[TARGET] == 1
    groups = {"Flagged, and it was fraud": validation[flagged & fraud],
              "Flagged, but it was genuine (false alarm)": validation[flagged & ~fraud],
              "Not flagged, but it was fraud (missed)": validation[~flagged & fraud],
              "Not flagged, and it was genuine": validation[~flagged & ~fraud].iloc[::5000]}
    return {name: rows.head(3).index.tolist() for name, rows in groups.items() if len(rows)}


# ---------------------------------------------------------------- complaints

def matched_words(text: str) -> dict:
    """For each safety rule that fires, the words that set it off (shown on screen only, never saved)."""
    found = {}
    for name, pattern in RULES.items():
        words = sorted({m.group(0).strip().lower() for m in pattern.finditer(text)})
        if words:
            found[name] = words
    return found


def sensitive_reasons(text: str) -> list:
    return [SENSITIVE_LABELS[c] for c in sorted(detect_sensitive(text).categories)]


def why_a_person(record) -> list:
    """Plain-language reasons behind the final 'needs a person' answer."""
    if record.route == "flagged_human_only":
        return ["It contains sensitive information, so no model reads it."]
    if record.route == "fallback":
        return ["The model gave no usable answer, so the safe default applies."]
    reasons = []
    if record.model_requires_human:
        reasons.append("The model said a person is needed.")
    reasons += [f"Safety rule: {RULE_LABELS[r].lower()}." for r in record.safety_rules]
    return reasons
