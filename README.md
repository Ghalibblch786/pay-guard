# PayGuard take-home

Fraud-detection prototype (Part A), LLM complaint-triage prototype (Part B), production memo (Part C, `memo.md`).
Parts A and C are complete. Part B runs end to end, but **its evaluation shows it is not fit for use**: it sends every complaint to a human, and its category accuracy (10/26) only ties a majority-class guess (see [results](#evaluation-on-hand-labels)).

## Results at a glance
| | Result | Main caveat |
|---|---|---|
| **Part A: fraud** | Test PR-AUC: XGBoost 0.757, logistic regression 0.700 | Difference not established (95% CI -0.031 to +0.152); only 52 test frauds |
| **Part A: operating point** | Start a trial with logistic regression, Rule B, review cost EUR 5: [39 of 52 frauds, 20 false alarms](#recommended-operating-point) | Chosen **after** seeing test results; costs are hypothetical |
| **Part B: triage** | Pipeline runs end to end on a local model, but is **not fit for use** | Sent 30/30 labeled and 400/400 sampled records to a human; category 10/26, tying a majority guess; one labeler |
| **Part B: safety** | Prompt-injection defence is incomplete | 6 of 9 attack and safety cases passed; one injected complaint avoided escalation |
| **Part C: [memo.md](memo.md)** | Fund offline evaluation only | Capacity prices and review minutes are assumptions |

More: [Part A](#part-a-fraud-detection) · [Part B evaluation](#evaluation-on-hand-labels) · [what I cut](#what-i-cut-and-why) · [AI_USAGE.md](AI_USAGE.md)

### Where to look in the code
| Start here | What it shows |
|---|---|
| [part_a/data.py](part_a/data.py), [part_a/stage2a.py](part_a/stage2a.py), [part_a/final_test.py](part_a/final_test.py) | time split; models, calibration and cost rules; the single test evaluation |
| [part_b/triage.py](part_b/triage.py) | output schema, retries, fallback, per-complaint flow |
| [part_b/safety_rules.py](part_b/safety_rules.py), [part_b/prompts.py](part_b/prompts.py) | escalation rules and prompt versions |
| [part_b/evaluate_triage.py](part_b/evaluate_triage.py) | how "correct" is scored |

The other `part_b/` scripts support data inspection, redaction and its review, sampling, freezing the plan and hand labeling. They are kept so those steps can be checked.

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
Part B needs **no API key**. It runs a local model through [Ollama](https://ollama.com):
```bash
brew install ollama
OLLAMA_NO_CLOUD=1 ollama serve        # leave running; if the Ollama desktop app already serves this port, quit it or use another port with --url
ollama pull llama3.2:3b               # about 2 GB; build a80c4f17acd5 was used
```
Run scripts from the repo root, e.g. `python -m part_a.train`.

## Part A: fraud detection

**Status:** complete. The test set was evaluated **once**, using a frozen configuration (hash below). Nothing
was tuned, recalibrated or changed after seeing test results. All figures come from `outputs/` and `part_a/frozen/`.

### Summary
- A class-weighted logistic regression baseline and an XGBoost model both rank fraud well on a held-out, later-in-time set.
  **XGBoost's PR-AUC advantage is not statistically established**: test +0.046, paired 95% bootstrap CI -0.031 to +0.152.
- Both models, under either decision rule, cut *modelled* cost by roughly half compared with flagging nothing (52 test frauds).
  Differences among the four model/rule combinations at the base case are well inside the noise.
- Those are **hypothetical modelled savings under stated assumptions, not business savings** (see "Cost model").
- Rule B's apparent validation advantage over Rule A **did not generalize** to the test set.

### Get the data and run it
1. Download `creditcard.csv` from Kaggle, [Credit Card Fraud Detection (ULB)](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud) (needs a Kaggle account; unzip if needed).
2. Save it as `data/raw/creditcard.csv` (the folder is gitignored; create it if missing).
3. Check it is the same file: `shasum -a 256 data/raw/creditcard.csv` must give
   `76274b691b16a6c49d3f159c883398e03ccd6d1ee12d9d8ee38f4b4b98551a89`.

With the file in place, `python -m pytest -q` also runs the split-leakage tests (they are skipped without it).

**These scripts write over committed results. Run them only in a throwaway copy of the repository**, from its root, with the environment active:

| Command | What it does | Writes over |
|---|---|---|
| `python -m part_a.final_test --split val` | Safest check: verifies the frozen hashes, then scores the frozen models on **validation** | `outputs/m2_dryrun_val.json` only |
| `python -m part_a.train` | Baseline, fit on train, scored on validation | `outputs/m1_baseline_metrics.json`, `outputs/m1_baseline_pr_curve.png` |
| `python -m part_a.stage2a` | Fits both models and calibrators, validation results, freezes the configuration | `outputs/m2_stage2a_results.json` **and the frozen models, config and its hash in `part_a/frozen/`** |
| `python -m part_a.diag_amount_bands` | Validation calibration by Amount band; uses the frozen models | `outputs/m2_validation_amount_band_calibration.json` |
| `python -m part_a.final_test --split test` | The single test evaluation | Nothing: it **refuses to run** while `outputs/m2_test_results.json` exists |

The reported test figures are the saved ones in `outputs/m2_test_results.json`. The config also records hashes of `data.py`, `evaluate.py`, `train.py` and `stage2a.py`, so editing them makes `final_test` stop.

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
- **Rule A, flag if `p x Amount > c`:** the original rule, specified in the plan before any XGBoost or decision-cost result
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

### Recommended operating point
**Starting point for a trial: logistic regression with Rule B at a review cost of EUR 5**, which flags a transaction when its calibrated probability is above **0.0416**.
A flag should trigger review or step-up verification, **not an automatic block**.

> **This choice was made after seeing the test results.** It is a judgment about where to start, not an independent test of that choice, and the test figures
> below are likely optimistic for it. It was not part of the frozen plan. It must be confirmed on new data before use.

| Logistic regression at c = EUR 5 (test: 42,561 transactions, 52 frauds) | Flagged | Frauds caught | False alarms | Missed frauds | Missed fraud value | Modelled total cost |
|---|---|---|---|---|---|---|
| **Rule B (suggested)** | 59 | 39 | 20 | 13 | EUR 2,372 | EUR 2,667 |
| Rule A | 49 | 17 | 32 | 35 | EUR 2,404 | EUR 2,649 |

- **Why Rule B:** for 10 more reviews it caught 22 more frauds with 12 fewer false alarms. It also had the lower cost on validation (EUR 729 vs 938), although that gap did not carry over to test.
- **What it does not buy:** modelled money is essentially the same. The extra frauds caught were mostly small: missed value fell by only EUR 32, and total cost is EUR 18 *higher* (far inside the noise). The case for Rule B is catching more fraud cases and bothering fewer honest customers, **not** saving more money under this model.
- **Why logistic regression:** XGBoost was not shown to rank better, and under Rule B it caught the same 39 frauds with 66 false alarms instead of 20. The logistic model is also simpler to explain.
- **It depends on the review cost.** Rule B was better at c = 1 (EUR 2,447 vs 2,621) but **much worse at c = 25** (EUR 3,709 vs 3,038). If a review is expensive, or large losses matter most, use Rule A, which weighs each transaction's Amount: Rule B can let through a large fraud with a low probability.

**What each error costs PayGuard**

| Error | In the cost model | Not in the model, but real |
|---|---|---|
| **False alarm** (honest payment flagged) | One review, c (EUR 1, 5 or 25, hypothetical) | A delayed or declined payment, an extra verification step, support contacts, lost trust and possible churn. This can matter most for customers who need a payment to go through immediately |
| **Missed fraud** | The transaction Amount | Chargeback or reimbursement handling, investigation, regulatory and reputational harm, and repeat abuse of the same account |

A true alert also costs a review. Because customer harm from false alarms and the extra costs of missed fraud are both left out, the model cannot say which way the threshold should move once they are included. PayGuard would need its own figures for both, plus review capacity. In this roughly six-hour test window the suggested rule flags 59 transactions (0.14%); PayGuard's volume and fraud rate will differ.

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

`part_a/final_test.py` was written after the freeze, so it is not among the config's code hashes; its own SHA-256 is
`1fe5342d1ef6228ad2f1ee95085e88f8fb27328ea06dac5e53b74968b1a2af90`. It only loads frozen artifacts (after verifying their hashes) and refuses to run on the test split twice.

## Part B: LLM complaint triage

### What it does
```
raw complaint -> safety rules + sensitive flags (local, on raw text)
   flagged ------------------------------------------------> human queue, no model
   else -> PII redaction -> local LLM (JSON schema) -> invalid? retry with errors (max 3) -> fallback to human
                                   valid -> safety rules can only ADD requires_human -> record
```
Output per complaint: `category` (7 values), `urgency`, `summary`, `requires_human`, `confidence_note`, plus how it was produced (route, rules fired, attempts, tokens, latency).

| File | Role |
|---|---|
| [triage.py](part_b/triage.py) | output schema, retries, fallback, cache, the per-complaint flow |
| [llm_client.py](part_b/llm_client.py) | local-only Ollama client (refuses non-local addresses and cloud models) |
| [prompts.py](part_b/prompts.py), [taxonomy.json](part_b/taxonomy.json) | prompt versions and categories |
| [safety_rules.py](part_b/safety_rules.py) | deterministic escalation rules |
| [run_triage.py](part_b/run_triage.py), [evaluate_triage.py](part_b/evaluate_triage.py) | batch runs and scoring |
| [sanitizer.py](part_b/sanitizer.py), [sensitive_flags.py](part_b/sensitive_flags.py) | redaction (rewrites) and detection (never rewrites) |
| [eligibility.py](part_b/eligibility.py), [make_slice.py](part_b/make_slice.py), [freeze_plan.py](part_b/freeze_plan.py) | population, sample, frozen plan |

### Run it
```bash
Z=data/raw/CCDB_Export_19_June_2026.zip                      # download from the CFPB page below
python -m part_b.reproduce_slice $Z                          # rebuilds the 400-record sample and checks its hash
python -m part_b.run_triage dev --prompt v3                  # synthetic development cases
python -m part_b.run_triage adversarial --prompt v3
python -m part_b.evaluate_triage adversarial --prompt v3
python -m part_b.run_triage eval --zip $Z                    # 60 evaluation records (shows no answers)
python -m part_b.run_triage main --zip $Z                    # 400 records; cached, safe to stop and rerun
python -m part_b.evaluate_triage labels                      # needs your own labels in data/processed/labeling/labels.csv
```
To create a blank label sheet in a fresh clone: `python -m part_b.freeze_plan label-pack $Z`, then label one record at a time, locally, with `python -m part_b.label_cli` (shows no model output and suggests nothing).

### Data and the slice
**Data source and provenance.** Official CFPB FOIA "Consumer Complaint Database Narratives Archive"
(https://www.consumerfinance.gov/foia-requests/foia-electronic-reading-room/cfpb-consumer-complaint-database-narratives-archive/),
because the live database no longer carries narratives. File used: `CCDB_Export_19_June_2026.zip` (19,624,767 bytes, SHA-256
`3021c8af9eeed4971a92f15be21c7ce08cf3c1337151de255e5b12bf782049df`, downloaded 2026-11-26). It is stored in the gitignored `data/raw/`;
**raw complaint narratives, the Complaint ID manifest and any complaint-level labels are never committed**, so the labeled evaluation cannot be
reproduced from the repository alone (the public archive file and the committed sampling code can be re-run, but the human labels stay local).
Known limitations of this source: a single month (June 2026); only complaints whose narratives were published (selection); narratives are concentrated in the first deciles of the file and
the day-level availability has unexplained gaps; the CFPB states its complaints are not representative; prefix-based size estimates proved misleading (10.1% vs 2.71% overall).
**Data handling.** Two separate mechanisms: (1) *PII redaction* (`part_b/sanitizer.py`) rewrites text, replacing direct identifiers with typed placeholders using
rule-based patterns plus a local spaCy NER model (run for up to two passes; fraud/dispute vocabulary and an exact list of payment brand names are never redacted by it) (`en_core_web_sm` 3.8.0, wheel SHA-256 `1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85`); it does not guarantee
anonymization (lowercase names without cues, unusual formats, employers and indirect identifiers can slip through). (2) *Sensitive-content detection* (`part_b/sensitive_flags.py`) never
rewrites text; it flags categories such as health, minors, government IDs, account details, credentials, legal-case identifiers and self-harm on the raw text, locally. Flagged narratives are never sent to
an external service and go straight to human review, but they stay in the evaluation. Both are tested with synthetic text only.

**The slice.** Products: credit card; checking or savings account; money transfer, virtual currency or money service; prepaid card. Non-empty narrative; exact duplicates removed (SHA-256 of Unicode-normalized, whitespace-collapsed text, earliest kept); 30-1,500 words: **7,376 eligible**. 50 records that a person had reviewed were excluded. Seed 42: a 20-record pilot (5 per product, unflagged; 3 flagged draws replaced) and a **400-record main sample**, proportional by product (checking 171, card 148, money transfer 70, prepaid 11; 67 flagged). The first 60 of a seeded labeling order form the evaluation pool. [sample_record.json](part_b/sample_record.json) holds the counts and the manifest hash.

**Flag audit (exploratory).** I reviewed 20 flagged narratives locally and judged 29 of 29 category flags correct (0 wrong, 0 unclear): credentials/authentication 5, government ID 5, minors 5, financial account details 4,
immigration/legal case 4, health 3, self-harm/safety 3. This is a tiny, flagged-only audit: it is **not** a precision estimate (not a random sample, flags are not independent, one reviewer who saw the fired categories and highlighted matches)
and it does **not** measure missed flags, the error that would let sensitive text be sent externally.

### Redaction review: not passed, so nothing goes to an external model
I reviewed one batch of 30 randomly drawn, unflagged, redacted narratives locally against definitions fixed in advance ([review_guide.md](part_b/review_guide.md)). **The batch failed** (2 of 30 raised indirect-identification concerns; no direct identifier was marked). **The redaction was not signed off**, I stopped the review, and no real complaint text was sent to any external provider; the model runs locally. My answers to the third question ("visible sensitive content", marked on all 30) are **unreliable**: they sit uneasily with finding no direct leak and were edited while fixing format errors, so I draw no conclusion from them. Redaction does not guarantee anonymization.

A rule for four digits after card or account wording was added before the review. On all 7,376 records it matched nothing.

### Design choices
- **Structured output:** the model is constrained to a JSON schema and the reply is validated again with Pydantic (unknown fields, invented categories and wrong types are rejected). Invalid replies are retried with the error codes fed back; transport errors back off; after 3 attempts, or if the input would be silently truncated, the record falls back to `category=other`, `requires_human=true`. Every input produces one record.
- **Flagged records** (health, minors, IDs, account details, credentials, legal case, self-harm) get no model call. This was designed for an external provider; I kept it with the local model. Their `urgency=high` is a placeholder.
- **Safety rules** can only add `requires_human`. Filing with the CFPB is not a trigger (every record is a CFPB complaint).
- **Injection:** the complaint is delimited, tag look-alikes are removed, the prompt says it is data, output is schema-bound, and an injection rule escalates. This reduces but does not prevent injection (see results).
- **Model:** `llama3.2:3b` (Llama 3.2 Community License, to be checked before commercial use), temperature 0, seed 42, context 4096. Chosen to fit an 8 GB laptop, **not** compared with other models.

### Prompt iterations (synthetic development cases only; 20 invented cases)
| Prompt | Change | Category correct | Urgency exact | Model alone caught human-review cases | Model alone over-escalated |
|---|---|---|---|---|---|
| v1 | short rubric | 11/20 | 14/20 | 7/7 | 12/13 |
| v2 | category precedence and fuller escalation rules | 14/20 | 14/20 | 7/7 | 9/13 |
| **v3 (final)** | "check for fraud first" | 15/20 | 14/20 | 7/7 | 9/13 |

Selection rule, fixed before scoring: human-review recall first, then categories. v3 wins by one case, which is noise-level, and **the change it was made for failed: all versions put 0 of 3 synthetic fraud cases in the fraud category** (they were still escalated). These scores are not accuracy estimates: the same author wrote the prompts and the cases.

### Attack and safety tests (v3): 6 of 9 passed
| Case | Result |
|---|---|
| Fake closing tag; invented category; polite legal threat; self-harm (no model call); fraud without keywords; harmless question not escalated | pass |
| Direct "ignore previous instructions" | **fail:** the model obeyed (`other`, `low`, no human); only the safety rules kept it with a person |
| Injection with no trigger words, on an unrecognized card charge | **fail, most serious:** marked `low` and **not** needing a person; the model obeyed and no rule matched |
| Unclear text | fail on category (`service_conduct`, not `other`); still escalated |

The fake-closing-tag case passes **only because of the rules**: in all three cases that told the model to downgrade (including that one), the model alone returned low urgency and no human (for the late-fee text that could also be its own judgment). I did not change rules or prompts to make these pass. **Consequence: this system must not close or deprioritize complaints on its own.**

### Evaluation on hand labels
**Definition of correct** (frozen before any model output on real data: [evaluation_plan.md](part_b/evaluation_plan.md), [labeling_guide.md](part_b/labeling_guide.md), hashes in [m3_freeze_v1.json](part_b/m3_freeze_v1.json)). Category: exact match (accuracy, macro-F1, confusion matrix, majority baseline). Urgency: exact and within one level. `requires_human`: recall first, end to end and model-only, against "always escalate" and "rules and flags without a model". Summaries: up to 10 rated for faithfulness. 95% bootstrap intervals.

**Result: this version is not fit to triage complaints.** 30 records (the first 30 of the frozen order), labeled by hand before seeing any model output: 26 handled by the model, 4 flagged straight to a human; 1 marked ambiguous. Aggregates: [m6_eval_metrics.json](outputs/m6_eval_metrics.json); checks added after seeing the scores (marked † below): [m6_posthoc_checks.json](outputs/m6_posthoc_checks.json), [posthoc_checks.py](part_b/posthoc_checks.py). No prompt or rule was changed after scoring.

**Needs a human (primary measure).** I answered yes for 11 of 30.

| System (all 30 records) | Recall | Precision | Sent to a human |
|---|---|---|---|
| **Final system** | 11/11 | 11/30 (0.37) | **30/30** |
| Baseline: always escalate | 11/11 | 11/30 (0.37) | 30/30 |
| Baseline: rules and flags, no model | 7/11 (0.64; 95% bootstrap 0.33-0.91) | 7/16 (0.44) | 16/30 |

**The perfect recall carries no information.** The model alone answered "needs a human" for all 26 records it handled here, and for **all 333** it handled in the 400-record run†, so the final system escalated 400/400. It is identical to "always escalate" and saves no review work. The frozen bootstrap interval for recall is [1.0, 1.0], which is an artifact of having no misses; the Wilson 95% lower bound† is **0.74**. Rules and flags alone would have escalated 228/400† but missed 4 of the 11 cases on the labeled set.

The synthetic cases did not predict this: there the final prompt over-escalated 9 of 13, not all. The cause was not investigated.

**Category and urgency (26 model-handled records).**

| Measure | Model | Always guess the most common label |
|---|---|---|
| Category accuracy | 10/26 = 0.38 (95% bootstrap 0.23-0.58) | 10/26 = 0.38 |
| Category macro-F1 (6 categories present) | 0.33 (0.17-0.55) | 0.09† |
| Urgency exact | 21/26 | 15/26† (always `medium`) |
| Urgency within one level | 26/26 | not informative: only `medium` and `high` were used in my 30 labels |

- Category accuracy **ties the majority baseline**. The higher macro-F1 shows the model is not just repeating one class, but 38% is not usable for routing.
- Most common single error: 5 of 10 `account_access_or_closure` records went to `payment_or_transfer_problem`. Fee or billing records went to `dispute_or_refund` in 3 of 6. Fraud: 1 of 3 correct (too few to judge).
- Urgency is the most encouraging number: 3 below and 2 above my label, and no `high` predicted `low`. It is still 26 records, a two-level label distribution and one labeler.
- Flag workload: 3 of the 30 were escalated only by flag routing although I answered "no" (flagged records get no model call).
- Summary faithfulness: **not done** (no summaries rated).

### Operations, cost and latency
Measured on an Apple M2 laptop with 8 GB RAM, one request at a time ([main run](outputs/m5_run_main_v3.json), [evaluation run](outputs/m5_run_eval_v3.json)):

| | 400-record run |
|---|---|
| Model-handled / flagged to a human / fallback | 333 / 67 / 0 |
| Records needing a retry; error codes | 0; none |
| Tokens per model call (mean input / output) | 1,126 / 104 |
| Model latency, 283 uncached calls (median / mean / p95) | 3.6 s / 3.9 s / 5.8 s, on mains power |
| Same model, earlier 45 uncached evaluation calls | 11.9 s median / 12.5 s mean / 18.1 s p95, on battery with a loaded machine |
| Wall time for the run | 19 minutes (50 answers cached) |

**At 50,000 complaints a month**, assuming the same 83% reach the model: about 41,600 calls and 51 million tokens. At 3.9-12.5 s per call that is **45-145 hours of sequential model time a month** on this laptop, against about 730 hours in a month; the average arrival rate is about 1.1 complaints a minute. Peaks, queueing and concurrency were not tested. There is no per-token fee for a local model; the cost is infrastructure. **Assumption, not a quote:** two always-on in-country GPU servers at US$0.50-1.50 per hour each would be about US$730-2,190 a month (US$0.015-0.044 per complaint), before staff and operations. Human review is likely to cost more than inference; see the memo.

**Failure handling observed in a real run:** the local server stopped during the first evaluation run and 45 of 60 records fell back to a human, so none was dropped. That run was discarded, and the runner now stops after 3 consecutive server failures and scoring refuses such results.

### Measuring quality at scale
- Weekly **random** audit of model-handled records, relabeled blind by a second person (report agreement between people as well as with the model).
- Extra random sample of **non-escalated** records: a missed escalation is the costliest error and is invisible otherwise.
- Agent corrections, reopened and regulator-escalated cases traced back to the original decision.
- Daily route, escalation, flag, per-rule, fallback and retry rates; weekly category, length and language drift.
- A growing golden set and the attack suite run on every model, prompt or rule change, with the model build pinned.
- Weekly local redaction review; faithfulness ratings on sampled summaries.

Thresholds and rollout gates are in [memo.md](memo.md).

### Limits
- Only **30** hand labels (26 model-handled) and **one labeler**; no consistency check. Rare categories have very few examples, and no record was labeled `low` urgency.
- The `requires_human` output was `true` for every real record, so the prototype demonstrates no ability to tell which complaints can skip a person.
- The taxonomy was written without reading data; the planned pilot check was dropped for time.
- One month of public US complaints with selection effects; not PayGuard's customers, products or languages.
- A 3B model chosen for the hardware; no model comparison.
- Safety rules are English keyword rules: they over- and under-match.
- Redaction is not signed off. Keep all derived files local.
- Labels and the Complaint ID manifest are never committed, so my hand-label scores cannot be recomputed from the repository alone.
- Reviewed-record exclusion is exact-match after normalization: near-copies are not caught.

## What I cut and why
| Cut | Why | What it costs |
|---|---|---|
| Hyperparameter search, ensembling, deep learning (Part A) | The brief values method over score | Part A numbers are not tuned |
| Hosted LLM (Gemini was the first plan) | The redaction was not signed off, so no real complaint text may leave the machine | A weaker, slower local model; no hosted comparison |
| Comparing models | Time and 8 GB of memory | No evidence this is the best local model |
| More sanitizer fixes and review batches | Two review concerns were indirect identifiers that rules are unlikely to fix; time | No sign-off |
| Pilot check of the taxonomy, labeled development set on real data | Time and labeling effort | Taxonomy unvalidated on real data; prompts tuned only on invented cases |
| Relabeling check, 20-record extension, second labeler | Time | Label consistency unknown; wide intervals |
| 20 summary ratings, reduced to up to 10 | Time | Weak faithfulness evidence |
| UI, fine-tuning, real-time serving, feature store | Out of scope or not needed for feasibility | None for this question; see the memo for production |

