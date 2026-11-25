# PayGuard take-home

Fraud-detection prototype (Part A), LLM complaint-triage prototype (Part B), production memo (Part C, `memo.md`).
Status: in progress. Sections below are filled in as each milestone completes.

## Setup
Tested on **macOS (Apple Silicon) with Python 3.12 only**. Linux/Windows untested.

```bash
# macOS only: XGBoost needs the OpenMP runtime
brew install libomp

# environment (uv)
uv venv --python 3.12
uv pip install -r requirements.txt        # exact pinned versions

# or plain pip
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# verify
.venv/bin/python -m pytest -q
```
Without `libomp`, importing/using XGBoost fails with `Library not loaded: @rpath/libomp.dylib`.
`pyproject.toml` lists the top-level dependencies; `requirements.txt` is the pinned freeze.
Part B needs a Gemini API key: copy `.env.example` to `.env` and fill in `GEMINI_API_KEY`.
Run scripts from the repo root, e.g. `python -m part_a.train`.

## Part A: fraud detection (in progress; M1 done, M2 pending)

**Data & split.** ULB `creditcard.csv` (284,807 rows, 492 frauds, SHA-256 `76274b69...8a89`). Exact duplicate
rows (1,081 extra copies, 19 of them fraud, 18 of those in train, no label conflicts) are **dropped**: they share the
same `Time`, so they cannot cross splits, but they would double-count identical events. This is a judgment call:
they could be genuine repeated transactions. Remaining 283,726 rows are sorted by `Time` and split by **time value**
at the 70% / 85% positions (rows sharing a timestamp always go to the same split; ~160k rows share a timestamp
with another row, so this matters). Result: train 198,607 rows / 366 frauds; validation 42,558 / 55; test 42,561 / 52.
The fraud rate drifts down over the two days (0.18% train vs 0.13% / 0.12% val / test).

**Metrics.** PR-AUC (average precision) is the headline because at ~0.15% prevalence accuracy and ROC-AUC look
excellent for almost any model. ROC-AUC is reported as secondary only. 95% CIs come from a row bootstrap, which captures
noise from having few frauds but not the choice of split.

**Baseline (M1).** StandardScaler (fit on train only, inside a Pipeline) + class-weighted logistic regression.
Validation only; the test set has not been used.

| Validation | Value |
|---|---|
| PR-AUC | 0.837 (95% CI 0.743-0.917) |
| ROC-AUC (secondary) | 0.982 |
| Threshold for >=90% precision (picked on val) | 0.999995 |
| At that threshold | 42 TP, 4 FP, 13 FN, precision 0.913, recall 0.764 |

**Limits found so far.**
- The 90%-precision operating point rests on **4 false positives**: one more would drop precision below 90%.
  The recall of 76% is optimistic because the threshold was chosen on the same validation data.
- With 55 validation frauds, differences of a few PR-AUC points between models will not be distinguishable.
- **Scores are not calibrated probabilities.** Class weighting inflates them: the [0.9, 1.0) score bin has mean
  prediction 0.97 but an observed fraud rate of 26%, and the [0.0, 0.1) bin predicts 2.1% against an observed 0.006%.
  The chosen threshold (0.999995) sits at the extreme edge of the score range. Any cost calculation that treats the
  score as a probability would be wrong; calibration (or rank/threshold-based costing) must be settled in M2.
- Two days of data: time drift beyond a mild fraud-rate decline cannot be assessed. Features V1-V28 are anonymized PCA
  outputs, so no feature engineering or business interpretation is possible.

### M2 Stage 2a (validation only; test set not yet used)
XGBoost (fixed, untuned parameters) vs the logistic baseline, both with Platt calibration fit on **train out-of-fold**
scores (4 expanding-window time folds). Primary seed 42; seeds 43/44 reported for robustness only.
- **PR-AUC:** logistic 0.837, XGBoost 0.846; paired bootstrap difference +0.009 (95% CI -0.013 to +0.034), i.e. not distinguishable from zero.
- **Calibration check on validation (independent):** expected/observed frauds 1.05 (logistic) and 1.35 (XGBoost); the
  fraud rate fell from 0.165% (calibration region) to 0.129% (validation), so the calibrator over-predicts.
- **Decision rules: two rules are retained, with different roles.**
  - **Rule A, `flag if p x Amount > c`** is the original rule, specified in the approved M2 proposal before any Stage 2a result
    was computed. It is the primary comparator. It is the principled rule *if* its assumptions hold (calibrated p, constant review
    cost c, flagged fraud fully prevented). On validation it performed poorly: at c = 5 it cost XGBoost EUR 1,726 (logistic 938)
    against about EUR 630 for in-sample reference cutoffs. A validation-only diagnostic (`part_a/diag_amount_bands.py`) shows
    calibration is fine for transactions under EUR 10 but over-predicts above that (XGBoost, EUR 10-100: 14.8 expected vs 7 actual
    frauds; EUR 100-1,000: 24.3 vs 16), and `p x Amount` amplifies that error. Bands hold only 1-31 frauds and the fraud rate also
    fell between calibration and validation, so this is consistent with, not proof of, amount-specific miscalibration.
  - **Rule B, `flag if p > c / 120.29`** (EUR 120.29 = mean fraud Amount in train; thresholds 0.0083 / 0.0416 / 0.2078 for
    c = 1 / 5 / 25) is a **validation-informed, secondary operating-policy alternative**. It is an **average-loss approximation,
    not a transaction-specific expected-cost calculation**: every missed fraud is treated as costing the same constant amount,
    so it cannot tell a small from a large transaction at equal p. It was **not independently pre-registered**: it was
    adopted after seeing Rule A's validation results. Its thresholds were not tuned on validation, but the decision to use it was
    informed by validation. We make no claim that it is theoretically better than Rule A. At c = 5 on validation it cost XGBoost
    EUR 742 and logistic EUR 729; this single comparison on 55 frauds does not show it generalizes.
  - Both rules are deterministic functions of the frozen scores and are evaluated once on the test set; neither is chosen using test results.
- **Costs are hypothetical** (EUR; review cost c = 5 base, 1 and 25 sensitivity), not PayGuard figures. Cost = c x flagged
  + Amount of every missed fraud.
- **Limits of both rules:** they depend entirely on the hypothetical c; calibration was verified only in aggregate and
  by Amount band on validation; costs are dominated by a few large frauds (validation fraud median EUR 8); at low c, Rule B's
  threshold sits where calibration is weakest.
- **Config history** (all kept in `part_a/frozen/`): v1 (Rule A only; `superseded_v1_config.*`), v2 (Rule A replaced by Rule B
  after validation results; `superseded_v2_config.*`), **v3 (current: both rules with roles; `m2_frozen_config.json`, hash in
  `m2_frozen_config.sha256`)**. Models, calibration, features, split and seeds are identical across all three.

## Part B: LLM triage
_To be written (M3-M6)._

## What I cut and why
_To be completed; see SPECS.md §11 for the planned cut list._
