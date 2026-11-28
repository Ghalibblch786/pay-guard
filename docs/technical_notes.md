# Technical notes

The detail behind the [README](../README.md): data, method, results and limits. † marks a check added after the results were seen.

- [This data and real payment data](#this-data-and-real-payment-data)
- [Part A: fraud detection](#part-a-fraud-detection)
- [Part B: complaint triage](#part-b-complaint-triage)
- [Reproducing the results](#reproducing-the-results)

## This data and real payment data

The fraud data is the public ULB card dataset: European card payments over two days in 2013, 284,807 rows, 492 of them fraud.

| | This dataset | What PayGuard's data would look like | What changes |
|---|---|---|---|
| Fields | `Time`, `Amount` and 28 disguised fields (`V1`-`V28`) | Named fields: customer, device, merchant, place, channel | The model must be rebuilt; explanations become meaningful |
| History | None: no customer or card identifier | Months of activity per customer | Recent behaviour (how many payments, how fast, how unusual) is usually a key signal |
| Labels | Complete and ready | Arrive weeks later; some disputed; undetected fraud is labeled genuine | Training and monitoring lag behind |
| Time span | About 48 hours | Months, with seasons and campaigns | Performance must be tracked over time |
| Payment types | Cards | A wallet may also have transfers, cash-in and cash-out | Each may need its own signals or model |
| Behaviour | Fixed | Fraudsters change tactics in response to controls | Retraining and rule updates are routine |
| Timing | Scored offline in one batch | Decided while the payment waits | Signals must be ready in advance; speed limits the design |
| Existing controls | None | Rules already block some fraud | The data only shows fraud that got through them; the benefit must be measured against them |

### Fraud scenarios to cover in production
These are common patterns to check with PayGuard's fraud team. **None can be identified in this dataset.**

| Scenario | Signals we would need |
|---|---|
| Stolen card details: small test payments, then large ones | Payment sequence per card, merchant, speed |
| Account takeover, for example after a SIM swap or phishing | New device, number or password change before a transfer |
| Customer tricked into paying a scammer | New recipient, unusual amount. The customer authorises it, so card-theft signals may not appear |
| Mule accounts passing stolen money on | Many senders in, fast transfers out, links between accounts |
| New accounts opened with false identities | Sign-up data, shared devices or documents |

## Part A: fraud detection

### Method
- **Duplicates:** 1,081 extra exact copies were dropped (19 fraud, 18 of them in the training period). Copies share a timestamp, so they would count one event twice. They could be real repeat payments; we did not test keeping them. 283,726 rows remain.
- **Split by time,** at the timestamps found at the 70% and 85% positions. Rows with the same timestamp stay together.

| Split | Rows | Frauds | Fraud rate | Hours from start |
|---|---|---|---|---|
| Train | 198,607 | 366 | 0.184% | 0 to 36.9 |
| Validation | 42,558 | 55 | 0.129% | 36.9 to 42.0 |
| Test | 42,561 | 52 | 0.122% | 42.0 to 48.0 |

- **Metric:** PR-AUC (average precision). With about 0.15% fraud, accuracy and ROC-AUC look excellent for almost any model, so accuracy is not reported. Intervals are 95% bootstraps over rows (1,000 resamples); they do not cover the uncertainty from choosing one time split.
- **Baseline:** logistic regression with class weighting; scaling is fitted on training data only.
- **Stronger model:** XGBoost with settings fixed in advance and no tuning (300 trees, depth 4, learning rate 0.05, subsample and column sample 0.8, positive weight = negatives / positives, seed 42). Seeds 43 and 44 gave validation PR-AUC 0.852 against 0.846.
- **Calibration:** class weighting inflates scores, so each model's score is converted to a probability (Platt scaling) fitted on training data only, using time-ordered folds. Neither model was refitted on validation.
- **The test set was scored once,** with a saved ("frozen") configuration (SHA-256 `dedccaf6…94ce`).

### Results
| | Validation PR-AUC | Test PR-AUC (95% CI) | Test ROC-AUC |
|---|---|---|---|
| Logistic regression | 0.837 | **0.700** (0.573-0.852) | 0.977 |
| XGBoost | 0.846 | **0.757** (0.642-0.864) | 0.980 |

XGBoost minus logistic regression on test: +0.046, 95% interval **-0.031 to +0.152**. The data does not show that XGBoost is better. Both scored lower on test than validation. On test, logistic regression expected 48.6 frauds against 52 actual; XGBoost expected 69.9, an **over-prediction of 34%**. The fraud rate fell over time, which may explain some of it; this was not isolated.

### Decision rules and cost
Total cost = review cost c × number of flags + amount of every missed fraud. c = €5, also tried at €1 and €25. **All costs are hypothetical.** The estimate assumes a flagged fraud is fully stopped, a missed fraud costs only its amount, review capacity is unlimited, false alarms cost nothing beyond the review, and there are no existing controls.

- **Rule A:** flag if `probability × amount > c`. Written before any XGBoost or cost result. It is the principled rule when its assumptions hold.
- **Rule B:** flag if `probability > c / 120.29` (€120.29 is the average fraud amount in training). Adopted after Rule A did badly on validation, so **not pre-registered**. It treats every missed fraud as costing the same.

Test results at €5 (flag nothing costs €6,169):

| Model and rule | Flagged | Frauds caught | False alarms | Missed | Cost (95% CI) |
|---|---|---|---|---|---|
| Logistic, A | 49 | 17 | 32 | 35 | €2,649 (516-5,739) |
| Logistic, B | 59 | 39 | 20 | 13 | €2,667 (629-5,713) |
| XGBoost, A | 217 | 18 | 199 | 34 | €2,855 (1,216-5,565) |
| XGBoost, B | 105 | 39 | 66 | 13 | €2,897 (815-5,893) |

| Review cost | Logistic A | Logistic B | XGBoost A | XGBoost B |
|---|---|---|---|---|
| €1 | 2,621 | 2,447 | 1,075 | 1,815 |
| €5 | 2,649 | 2,667 | 2,855 | 2,897 |
| €25 | 3,038 | 3,709 | 3,711 | 3,647 |

- The four costs at €5 differ by far less than their uncertainty. No option is proven cheaper.
- Rule B's advantage on validation did not carry over to test.
- XGBoost with Rule A is cheapest at €1, but €1 was not the planned base case.
- A model that ranks better need not cost less: PR-AUC counts every fraud equally across all thresholds, while cost uses one threshold, weights frauds by amount and charges for each false alarm.

### Suggested operating point
**Logistic regression, Rule B, c = €5:** flag above a probability of **0.0416**, for review or extra verification, not an automatic block. **Chosen after seeing the test results**, so those figures are probably optimistic for it.

| | Flagged | Caught | False alarms | Missed fraud value | Total cost |
|---|---|---|---|---|---|
| Rule B (suggested) | 59 | 39 | 20 | €2,372 | €2,667 |
| Rule A | 49 | 17 | 32 | €2,404 | €2,649 |

- **For Rule B:** 22 more frauds caught with 12 fewer false alarms, and lower cost on validation (€729 against €938).
- **Against:** the extra frauds were mostly small. Missed value fell by only €32, and total cost is €18 higher. It does not save more money under this estimate.
- **Why logistic regression:** XGBoost with the same rule caught the same number with 66 false alarms, and logistic regression is easier to explain.
- **Depends on review cost:** Rule B is better at €1 and much worse at €25. If reviews are expensive or large losses matter most, use Rule A.

| Error | Priced | Real but not priced |
|---|---|---|
| False alarm | One review | Delayed or declined payment, extra step, support contact, lost trust, customer leaving |
| Missed fraud | The payment amount | Reimbursement handling, investigation, regulatory and reputation harm, repeat abuse |

### Real-time use
Nothing real-time was built or timed.
- **Same inputs in training and serving:** same field order, scaling, calibration and library versions. A mismatch fails silently.
- **Features:** `V1`-`V28` cannot be recreated, and `Time` (seconds since the data starts) has no meaning in production. History signals must be calculated ahead of time and kept current, and training must use only what was known at the moment of each payment.
- **Modelling strategy:** the time limit favours a small model scored in line, using prepared signals. A slower, richer check could run afterwards on flagged or high-value payments. Which fits depends on measured speed.
- **Upkeep:** confirmed fraud arrives late, so probabilities and the threshold need periodic re-checking.

### Limits
Only 52 test frauds; two days of old European data with disguised fields; one time split; untuned models; dropping duplicates was a judgment call; hypothetical costs; the rule choice was influenced by validation and, for the suggestion, by test results.

## Part B: complaint triage

### How one complaint is processed
1. **Safety rules** (English keywords) and **sensitive-content detection** run on the original text, locally.
2. Sensitive text (health, children, IDs, account details, passwords, legal cases, self-harm) goes to a person. **No model reads it.**
3. Other text is **redacted** (patterns plus a local name-recognition model).
4. A local model, `llama3.2:3b` (temperature 0, seed 42; check its licence before commercial use), returns `category`, `urgency`, `summary`, `requires_human` and `confidence_note`. It was chosen to fit an 8 GB laptop and **not compared** with others.
5. The reply must match a fixed schema: unknown fields and invented categories are rejected. Invalid replies are retried with the error, up to 3 attempts. Failure, or input too long, sends the complaint to a person. Every complaint gets a record.
6. Safety rules can **add** "needs a person", never remove it.

Against hidden instructions, the complaint is marked off as data, look-alike tags are removed, output is schema-bound and one rule escalates. This reduces the risk but does not prevent it.

Code: [triage.py](../part_b/triage.py), [safety_rules.py](../part_b/safety_rules.py), [prompts.py](../part_b/prompts.py), [taxonomy.json](../part_b/taxonomy.json), [evaluate_triage.py](../part_b/evaluate_triage.py). The other scripts in `part_b/` cover redaction, sampling, review and labeling, so those steps can be checked.

### Data
- **Source:** the CFPB [Narratives Archive](https://www.consumerfinance.gov/foia-requests/foia-electronic-reading-room/cfpb-consumer-complaint-database-narratives-archive/), used because the live database no longer carries complaint text. File `CCDB_Export_19_June_2026.zip`, SHA-256 `3021c8af9eeed4971a92f15be21c7ce08cf3c1337151de255e5b12bf782049df`, downloaded 2026-11-26.
- **Filter:** four payment-related products (credit card; checking or savings; money transfer, virtual currency or money service; prepaid card), exact duplicates removed, 30-1,500 words: **7,376 complaints**. 50 that a person had reviewed were excluded.
- **Sample (seed 42):** **400** in proportion by product (checking 171, card 148, money transfer 70, prepaid 11; 67 sensitive), plus a 20-record trial set. Labeling used the first 30 of a separate seeded order. Counts and fingerprint: [sample_record.json](../part_b/sample_record.json).
- **Limits:** one month (June 2026), only published narratives, uneven by day, and the CFPB says complaints are not representative.
- Complaint text, IDs and labels are **never committed**.

### Privacy checks
- **Redaction** replaces identifiers but does not make text anonymous.
- **Flag check:** I reviewed 20 sensitive-flagged complaints; all 29 category flags were correct. This is a tiny sample of flagged text only. It **does not measure missed sensitive content**.
- **Redaction review:** I reviewed 30 redacted complaints against rules fixed in advance ([review_guide.md](../part_b/review_guide.md)). **It failed:** 2 raised indirect-identification concerns; I marked no direct identifier. My answers on "visible sensitive content" are unreliable and support no conclusion. Redaction was **not signed off**, so no real complaint text went to an external provider.

### Evaluation
**Definition of correct** was fixed before any model output on real data ([evaluation plan](../part_b/evaluation_plan.md), [labeling guide](../part_b/labeling_guide.md)). 30 complaints were labeled before seeing model output: 26 handled by the model, 4 sensitive. No prompt or rule changed after scoring. Totals: [metrics](../outputs/m6_eval_metrics.json), [later checks†](../outputs/m6_posthoc_checks.json).

**Needs a person** (the primary measure; 11 of 30 did):

| System | Caught | Correct among those sent | Sent to a person |
|---|---|---|---|
| Final system | 11/11 | 11/30 | 30/30 |
| Send everything | 11/11 | 11/30 | 30/30 |
| Rules and flags, no model | 7/11 | 7/16 | 16/30 |

The perfect catch rate **means nothing**: it equals sending everything. The model alone said "needs a person" for all 26 here and all 333 in the larger run†. With 11 cases, the 95% lower bound on that catch rate is 0.74† (the planned bootstrap gives 1.0 to 1.0, which is uninformative with no misses). Rules alone would send 228 of 400†.

**Why it escalates everything was not tested.** A likely explanation is that the prompt asks for a person on any mention of fraud, law-breaking or hardship, which public complaints often contain. On invented cases it over-escalated 9 of 13, not all.

| Measure (26 model-handled) | Model | Always guess the most common |
|---|---|---|
| Category correct | 10 (95% interval 0.23-0.58 as a share) | 10 |
| Category macro-F1 | 0.33 (0.17-0.55) | 0.09† |
| Urgency exact | 21 | 15† |

All urgency answers were within one level, but only "medium" and "high" appeared in the labels. The most common category error: 5 of 10 account-access complaints were sent to payments.

**Summaries** (10 random, rated against the redacted text): faithful 1, minor omission 8, unsupported or misleading 1. In 9 of 10 no claim was unsupported, but only 1 was also complete. The 95% interval for the unsupported rate is about 2% to 40%†. One rater, who had seen the other scores; the detailed rating definitions were written after those scores.

**Attack and safety tests, 6 of 9 passed.** Failed: a direct "ignore previous instructions" (the model obeyed; rules still sent it to a person); a hidden instruction without trigger words (**not sent to a person**, the most serious); and unclear text (wrong category, still sent). In all three cases that told the model to downgrade, the model alone gave low urgency and no person. The case with a fake closing tag passed only because of the rules.

**Prompt versions** (20 invented cases, written by the same author as the prompts, so not an accuracy estimate):

| Version | Change | Category | Urgency | Needing a person caught | Over-escalated |
|---|---|---|---|---|---|
| v1 | Short instructions | 11/20 | 14/20 | 7/7 | 12/13 |
| v2 | Category order and fuller escalation rules | 14/20 | 14/20 | 7/7 | 9/13 |
| v3 (used) | "Check for fraud first" | 15/20 | 14/20 | 7/7 | 9/13 |

v3 won by one case. The change it was made for failed: every version put 0 of 3 invented fraud cases in the fraud category.

### Cost and speed
Measured on an 8 GB Apple M2 laptop, one request at a time ([run totals](../outputs/m5_run_main_v3.json)): 400 complaints; 333 to the model, 67 sensitive, no retries or fallbacks; about 1,126 input and 104 output tokens per call; mean 3.9 s and 95th percentile 5.8 s on mains power. An earlier run on battery under load averaged 12.5 s. At 50,000 a month with 83% reaching the model: about 41,600 calls, 51 million tokens and 45-145 hours of one-at-a-time model time. Peaks and parallel use are untested. At the **assumed** US$730-2,190 a month for two servers, that is US$0.015-0.044 per complaint before staff.

In the first evaluation run the model server stopped and 45 of 60 complaints fell back to a person, so none was lost. That run was discarded; the runner now stops after 3 server failures in a row.

### Measuring quality at scale
- Weekly random audit, labeled blind by a second person.
- A separate sample of cases **not** sent to a person, because missed escalations are otherwise invisible.
- Agent corrections, reopened cases and regulator escalations traced back.
- Daily escalation, flag, rule, retry and fallback rates; weekly changes in categories, length and language.
- Test cases and attack cases run on every model, prompt or rule change.
- Weekly redaction and summary checks. Alert thresholds are in the [memo](../memo.md).

### Limits
30 labels and one labeler; categories never checked on real data; one month of US complaints; one small model; English keyword rules that over- and under-match; redaction not signed off; labels are private, so these scores cannot be recomputed from the repository alone; excluding reviewed complaints catches exact copies only.

## Reproducing the results

Run from the repository folder with the environment active.

### Fraud
Put `creditcard.csv` in `data/raw/`. `shasum -a 256 data/raw/creditcard.csv` should print `76274b691b16a6c49d3f159c883398e03ccd6d1ee12d9d8ee38f4b4b98551a89`.

**These scripts write over saved results. Use a throwaway copy of the repository.**

| Command | What it does | Writes over |
|---|---|---|
| `python -m part_a.final_test --split val` | Safest check: verifies the frozen files, scores on validation | `outputs/m2_dryrun_val.json` |
| `python -m part_a.train` | Baseline on validation | `outputs/m1_baseline_metrics.json`, `m1_baseline_pr_curve.png` |
| `python -m part_a.stage2a` | Fits both models and calibration, then freezes | `outputs/m2_stage2a_results.json` **and the frozen files in `part_a/frozen/`** |
| `python -m part_a.final_test --split test` | The single test run | Refuses while saved test results exist |

Editing `data.py`, `evaluate.py`, `train.py` or `stage2a.py` makes `final_test` stop, because their fingerprints are recorded. (`stage2a.py` also produced an Amount-band diagnostic that its saved settings mention; the diagnostic script was removed, and its [result file](../outputs/m2_validation_amount_band_calibration.json) is kept.)

### Complaints
Download the archive file named above to `data/raw/`.
```bash
Z=data/raw/CCDB_Export_19_June_2026.zip
python -m part_b.reproduce_slice $Z        # rebuilds the sample and checks its fingerprint
python -m part_b.run_triage adversarial --prompt v3
python -m part_b.evaluate_triage adversarial --prompt v3
python -m part_b.run_triage main --zip $Z  # needs the local model; cached, safe to rerun
```
Scoring against human labels needs your own labels: `python -m part_b.freeze_plan label-pack $Z`, label with `python -m part_b.label_cli`, then `python -m part_b.run_triage eval --zip $Z` and `python -m part_b.evaluate_triage labels`.

**Charts and demo:** `python -m app.make_charts` redraws the README charts from saved results. `python -m app.save_demo` refreshes the saved demo answers and needs the local model.
