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

## Part A: fraud detection

**Status:** complete (M1-M2). The test set was evaluated **once**, using a frozen configuration (hash below). Nothing
was tuned, recalibrated or changed after seeing test results. All figures come from `outputs/` and `part_a/frozen/`.

### Summary
- A class-weighted logistic regression baseline and an XGBoost model both rank fraud well on a held-out, later-in-time set.
  **XGBoost's PR-AUC advantage is not statistically established**: test +0.046, paired 95% bootstrap CI -0.031 to +0.152.
- Both models, under either decision rule, cut *modelled* cost by roughly half compared with flagging nothing (52 test frauds).
  Differences among the four model/rule combinations at the base case are well inside the noise.
- Those are **hypothetical modelled savings under stated assumptions, not business savings** (see "Cost model").
- Rule B's apparent validation advantage over Rule A **did not generalize** to the test set.

### Data, split and duplicates
ULB `creditcard.csv` (284,807 rows, 492 frauds, SHA-256 `76274b69...8a89`).
- **Duplicates (judgment call):** 1,081 extra exact-duplicate rows (19 fraud; 18 of those in train; no label conflicts) were
  **dropped** because they share the same `Time` (so cannot cross splits) and would double-count identical events. They
  could be genuine repeated transactions; the alternative was not tested. 283,726 rows remain.
- **Split:** sorted by `Time`, cut at the `Time` values found at the 70% and 85% row positions; rows sharing a timestamp
  (~160k rows share one) always go to the same split.

| Split | Rows | Frauds | Fraud rate | Time span (seconds / hours) |
|---|---|---|---|---|
| Train | 198,607 | 366 | 0.184% | 0-132,905 (~36.9 h) |
| Validation | 42,558 | 55 | 0.129% | 132,906-151,319 (~5.1 h) |
| Test | 42,561 | 52 | 0.122% | 151,320-172,792 (~6.0 h) |

The fraud rate falls over time (0.184% -> 0.129% -> 0.122%; 0.165% in the region used to fit the calibrator).

### Metrics
PR-AUC (average precision) is the headline: at ~0.12-0.18% prevalence, accuracy and ROC-AUC look excellent for almost any
model. ROC-AUC is secondary only; accuracy is never reported. 95% CIs are row bootstraps (1,000 resamples), which capture noise from
having few frauds but not uncertainty from the choice of time split, and which assume independent rows.

### Models and calibration
- **Baseline:** `StandardScaler` (fit on train only, inside a Pipeline) + `LogisticRegression(class_weight="balanced")`.
- **XGBoost:** fixed, untuned parameters chosen in advance (300 trees, depth 4, learning rate 0.05, subsample/colsample 0.8,
  `scale_pos_weight` = negatives/positives). Primary seed 42; seeds 43/44 were reported for robustness only
  (validation PR-AUC 0.852 / 0.852 vs 0.846). Neither model was tuned, so XGBoost's ceiling is unknown.
- **Calibration:** class weighting inflates scores, so Platt (sigmoid) calibrators were fit on **train-only out-of-fold** scores
  (4 expanding-window time folds; 262 out-of-fold frauds; the last fold has only 28). Validation and test were never used to fit them.
- The final models are trained on train only and are **not** refit on validation, so the frozen rule matches the scores it was built on.

### Results: discrimination
| | Validation PR-AUC | **Test PR-AUC (95% CI)** | Test ROC-AUC (secondary) |
|---|---|---|---|
| Logistic regression | 0.837 (0.743-0.917) | **0.700 (0.573-0.852)** | 0.977 |
| XGBoost | 0.846 | **0.757 (0.642-0.864)** | 0.980 |

Paired bootstrap, XGBoost minus logistic: validation +0.009 (CI -0.013 to +0.034); **test +0.046 (CI -0.031 to +0.152)**,
XGBoost ahead in 76% of test resamples. The intervals include zero, so the data do not establish that XGBoost is better.
Both models scored lower on test than on validation; validation was optimistic, though with 52-55 frauds some of that gap is noise.

### Results: calibration (test)
- Logistic: 48.6 expected vs 52 actual frauds (ratio 0.93). XGBoost: 69.9 expected vs 52 actual (ratio **1.34**), the same
  over-prediction seen on validation. This is consistent with the prevalence shift but was not isolated from other causes.
  Both passed the adequacy criterion that was predeclared before any result was seen (aggregate ratio within 0.67-1.5, and
  observed/predicted within 0.5-2 for p >= 0.1).
- By transaction Amount band (descriptive, post hoc, 2-31 frauds per band): XGBoost over-predicts above EUR 10 (expected vs
  actual: EUR 10-100: 16.1 vs 11; EUR 100-1,000: 16.9 vs 10); logistic does not (10.5 vs 11; 7.1 vs 10).

### Decision rules and cost model
**Cost definition:** total cost = c x (number of flagged transactions, true or false alerts) + the Amount of every missed
(unflagged) fraud. All values are in EUR (matching the dataset's `Amount`) and are **hypothetical**: base review cost c = 5, with
sensitivity values 1 and 25. They are not PayGuard operating costs.

**Assumptions behind the cost model (all unverified):**
- *Fraud prevention:* every flagged fraud is fully prevented (no partial recovery, no retries, no fraud that succeeds anyway).
- *Missed-fraud loss:* equals the transaction Amount only; chargeback fees, investigation cost, recoveries, churn and reputational
  harm are ignored.
- *Review cost:* a constant c per flagged transaction; no analyst capacity limit, no customer-friction cost for false positives,
  no cost difference between true and false alerts.
- *Baseline:* "flag nothing" assumes no existing fraud controls; PayGuard presumably has some, so incremental savings would be smaller.
- *Probabilities:* both rules assume calibrated fraud probabilities, which was verified only in aggregate (and, for XGBoost,
  found to over-predict).

**Two rules, with different roles** (both frozen before the test evaluation, both evaluated once):
- **Rule A, flag if `p x Amount > c`:** the original rule, specified in the approved M2 proposal before any Stage 2a result
  existed; the primary comparator. It is the principled rule *if* its assumptions hold.
- **Rule B, flag if `p > c / 120.29`** (EUR 120.29 = mean fraud Amount in train; thresholds 0.0083 / 0.0416 / 0.2078 for
  c = 1 / 5 / 25): a **validation-informed, secondary operating-policy alternative** and an **average-loss approximation, not a
  transaction-specific expected-cost calculation** (it treats every missed fraud as costing the same constant). It was **not
  independently pre-registered**: it was adopted after Rule A performed poorly on validation (XGBoost at c = 5: EUR 1,726 vs
  ~EUR 630 for in-sample reference cutoffs). Its thresholds were not tuned on validation, but the decision to use it was
  informed by validation. No claim of theoretical superiority over Rule A is made.
- Config history is preserved in `part_a/frozen/`: v1 (Rule A only), v2 (Rule A replaced by Rule B after validation results),
  v3 (both rules with roles; used for the test evaluation).

### Results: decision costs (test; 52 frauds, EUR 6,169 total fraud value, flag-nothing cost = EUR 6,169)
Base case c = EUR 5 (cost 95% CI is a row bootstrap):

| Model / rule | Flagged | TP | FP | FN | TN | Precision | Recall | Cost (95% CI) | Modelled saving vs flag nothing |
|---|---|---|---|---|---|---|---|---|---|
| Logistic, Rule A | 49 | 17 | 32 | 35 | 42,477 | 0.347 | 0.327 | 2,649 (516-5,739) | 3,520 |
| Logistic, Rule B | 59 | 39 | 20 | 13 | 42,489 | 0.661 | 0.750 | 2,667 (629-5,713) | 3,501 |
| XGBoost, Rule A | 217 | 18 | 199 | 34 | 42,310 | 0.083 | 0.346 | 2,855 (1,216-5,565) | 3,314 |
| XGBoost, Rule B | 105 | 39 | 66 | 13 | 42,443 | 0.371 | 0.750 | 2,897 (815-5,893) | 3,271 |

Cost sensitivity (EUR; same fixed rules re-derived from each c, nothing tuned on test):

| c | Logistic A | Logistic B | XGBoost A | XGBoost B |
|---|---|---|---|---|
| 1 | 2,621 | 2,447 | **1,075** (812-1,495) | 1,815 |
| 5 | 2,649 | 2,667 | 2,855 | 2,897 |
| 25 | 3,038 | 3,709 | 3,711 | 3,647 |

Precision, recall and confusion matrices for c = 1 and 25 are in `outputs/m2_test_results.json`.

**Reading these honestly**
- At the base case the four costs differ by far less than their confidence intervals (which span roughly EUR 500-5,900);
  no combination is shown to be cheaper. Cost *differences* were not given their own intervals.
- **Rule B's validation advantage did not generalize.** On validation at c = 5, Rule B cost XGBoost EUR 742 against EUR 1,726 for
  Rule A (logistic: 729 vs 938). On test the two are essentially tied (XGBoost: 2,897 vs 2,855; logistic: 2,667 vs 2,649),
  and in some sensitivity cases Rule A is clearly better (XGBoost at c = 1: 1,075 vs 1,815; logistic at c = 25: 3,038 vs 3,709).
  Rule B was better in others (logistic at c = 1: 2,447 vs 2,621). One validation comparison on 55 frauds did not predict test behaviour.
- XGBoost at c = 1 under Rule A has the lowest cost seen, but c = 1 is a hypothetical sensitivity setting and was not the
  predeclared base case, so it should not be treated as the "best configuration".
- Under Rule B at c = 5 both models miss fraud worth the identical EUR 2,372 (about 80-90% of their cost), consistent with both
  missing the same high-value frauds. This was not verified.

### Why the higher-PR-AUC model need not have the lowest cost
PR-AUC summarizes ranking quality across all possible thresholds and counts every fraud equally. Operational cost is
determined by one operating point, weights each fraud by its Amount, and charges for every false alert. At c = 5 under Rule B
both models reach the same recall (0.750), but XGBoost flags 105 transactions to logistic's 59 (precision 0.371 vs 0.661) and so
pays for more false alerts. XGBoost's probabilities also over-predict (ratio 1.34), which is consistent with a probability-based
threshold admitting more false alerts, though this was not isolated. Finally, the cost is dominated by a few high-value missed
frauds, which PR-AUC does not weight. Hence a better ranking metric and a lower operating cost can disagree.

### Real-time inference (A6)
This describes how the prototype *would* be used for per-transaction scoring. **No production payment integration, serving
layer, feature store, latency test or load test has been built;** everything here was run offline in batch.
1. **Inputs per transaction:** the 30 dataset features (`Time`, `V1`-`V28`, `Amount`), in the training column order.
2. **Preprocessing consistency:** the logistic model's scaler is fitted on training data and stored with it
   (`logreg_baseline.joblib`); XGBoost needs no scaling. Serving must apply the identical transformation and feature order
   (training-serving skew is the main silent risk), and use the pinned library versions in `requirements.txt`.
3. **Scoring:** model margin -> Platt calibrator (slope/intercept stored in the frozen config) -> calibrated probability p.
4. **Decision:** Rule A (needs the transaction Amount) or Rule B (constant threshold), both parameterized by the review cost c;
   a flagged transaction is routed to review or step-up verification. Choice of c and of action are business decisions.
5. **Why this prototype cannot be deployed as is:**
   - `V1`-`V28` are anonymized PCA components of undisclosed raw features; PayGuard's real features, and any PCA transform, are
     not available, so the model would have to be retrained on PayGuard's own data.
   - `Time` is seconds since the dataset's first transaction, which has no meaning in production and would drift out of range; a
     real model should replace it with something like hour of day, or drop it.
   - Strong fraud signals are typically history-based (per-customer or per-merchant velocity, rolling aggregates). They are absent
     here and would need online aggregation with point-in-time-correct training to avoid leakage; they also add latency.
   - Labels arrive late (chargebacks take weeks), so training data lags, and the calibrator and the fraud-rate assumption need
     periodic refitting. The prevalence drift already seen within two days illustrates why.
   - Inference latency of the tree model is expected to be small but was **not measured**; review capacity, alert volume and
     the monitoring needed to catch drift and silent failures are addressed (for Part B) in the memo, not built here.

### Limitations (A7)
- **Few frauds:** 52 in test (55 in validation, 28 in the last calibration fold). All CIs are wide, and cost is driven by a handful of
  high-value frauds.
- **Short window:** two days in total; the test set covers only ~6 hours at the end of day 2. Behaviour over weeks or seasons is unknown,
  and the single time split is itself a source of uncertainty that the bootstrap does not capture.
- **Historical European card data (2013):** amounts, fraud patterns and customers differ from an emerging-market wallet like
  PayGuard's. The features are anonymized, so there is no business interpretation or feature engineering.
- **Duplicate removal** (1,081 rows) is a judgment call whose alternative was not evaluated.
- **Prevalence shift:** fraud rate fell from 0.184% (train) to 0.122% (test); calibration was fit on a 0.165% region, so
  XGBoost's probabilities over-predict (test ratio 1.34).
- **Hypothetical costs:** every cost figure rests on invented review costs (EUR 1/5/25) and the assumptions listed above.
  Modelled savings are not forecasts of PayGuard's savings.
- **Design choices informed by validation:** the replacement of the original rule by Rule B was informed by validation results,
  and validation PR-AUC was optimistic relative to test.
- **Untuned models; unmeasured latency; no production integration.**

### Frozen artifacts (all preserved; hashes verified before the test evaluation)
| Artifact | SHA-256 |
|---|---|
| Config v3 (used for test) `part_a/frozen/m2_frozen_config.json` | `dedccf6a3ff45e3821abbc25e76b0055cbe10bbd6d222cf4a2402b2e77de94ce` |
| Config v2 (superseded) | `47e046e066966a1a77df25ca3a4f9b076b3e5d856673b6cfd57feb0b4832bb05` |
| Config v1 (superseded) | `7c9b1f4d7b9359723be94ebd3f9fd1fae87c22ced3bb51211cb271bdf1a266c2` |
| Test results `outputs/m2_test_results.json` | `f54b10a50105ac741d2d00d397ac02d959c92aa739bbaba9445ee181b14eb985` |

`part_a/final_test.py` was written after the freeze, so it is not among the config's code hashes; it only loads frozen artifacts and
refuses to run on the test split twice.

## Part B: LLM triage
_To be written (M3-M6)._

## What I cut and why
_To be completed; see SPECS.md §11 for the planned cut list._
