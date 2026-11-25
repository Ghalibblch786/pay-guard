# SPECS.md — PayGuard Build Specification

> Living document. Replaces PLAN.md. Claude keeps the **Status** columns, the **Decision log**,
> and the **Milestones** checkboxes current as work progresses. It must never contradict
> `SCOPE.md` (frozen). If it would, stop and ask the user.

Last updated: 2026-11-26 · Current milestone: **M2 CLOSED (pending user review of closure report); M3 not started**

---

## 1. Goals and mindset
- Optimise for **judgment > eval rigor > code quality > communication > results** (SCOPE §8).
- Every non-obvious choice gets a one-line "because" in the decision log (§9) and later the README.
- Cut scope deliberately; record cuts in §11.
- Everything must be explainable and modifiable by the user live. Prefer simple over clever.

## 2. Requirements traceability
Status: ☐ todo · ◐ in progress · ☑ done

### Part A — Fraud
| ID | Requirement | Acceptance check | Status |
|---|---|---|---|
| A1 | Leak-free, time-aware train/test split | Split code documented; scaler/resampling fit on train only; duplicates handled | ☑ (tests pass) |
| A2 | Justified metrics | README states why PR-AUC leads, why accuracy is not used; recall @ fixed precision reported | ☑ |
| A3 | Baseline model | Logistic regression (class-weighted), metrics reported | ☑ (val) |
| A4 | Stronger model | XGBoost, same split/metrics, compared to A3 with variance estimate | ☑ (test: XGB 0.757 vs LR 0.700, paired diff +0.046, CI [-0.031, +0.152]: not significant) |
| A5 | Threshold + cost discussion | Explicit cost model with stated assumptions; threshold chosen from it; FP vs FN trade-off table/plot | ☑ |
| A6 | Real-time inference note | ≤ 1 page: latency, history-dependent features, label delay, drift, PCA-anonymized feature limitation | ☑ (README; explicitly not a production implementation) |
| A7 | Honest limits | Only 492 frauds → noisy metrics; dataset is 2 days, anonymized; stated in README | ☑ (README) |

### Part B — LLM triage
| ID | Requirement | Acceptance check | Status |
|---|---|---|---|
| B1 | Reproducible CFPB slice | Filters, date range, seed, row count, file hash documented; script regenerates it | ☐ |
| B2 | Taxonomy (5–8 categories) | Definitions + `other` escape hatch in `taxonomy.yaml`; used by prompt and labeling guide | ☐ |
| B3 | Structured output | Pydantic schema with enum-constrained `category`/`urgency`; all 5 fields present | ☐ |
| B4 | Failure/retry handling | Bounded retries with validation error fed back; timeouts; rate-limit backoff; safe fallback record (`requires_human=true`, `category=other`); no dropped rows | ☐ |
| B5 | Safety rules | Deterministic keyword/regex layer forces `requires_human=true` for fraud allegations, legal threats, regulator mentions, safety/self-harm language | ☐ |
| B6 | Prompt-injection defence + tests | ≥ 3–5 adversarial complaints; delimiters + data-not-instructions prompt; results reported | ☐ |
| B7 | Hand-labeled eval set | ≥ 50 complaints labeled **before** viewing model output; labeling guide; ambiguity noted | ☐ |
| B8 | Evaluation | Per-field metrics; confusion matrix; urgency scored ordinally; `requires_human` recall emphasised; summary faithfulness spot-check | ☐ |
| B9 | Scale measurement plan | README section: audited sampling, agreement, distribution drift, escalation rate | ☐ |
| B10 | Cost/latency | Tokens + latency measured on slice; extrapolated to 50k/month with assumptions | ☐ |
| B11 | Prompt iteration log | Each prompt version + score recorded | ☐ |

### Part C — Memo
| ID | Requirement | Acceptance check | Status |
|---|---|---|---|
| C1 | One prototype chosen | Part B (recommended; confirm in §9) | ☐ |
| C2 | Architecture diagram | Simple, in-memo | ☐ |
| C3 | Monitoring of silent failures | Each failure paired with a concrete detector and threshold | ☐ |
| C4 | Data: privacy/residency/retention | In-country inference decision, PII redaction before model calls, retention rule | ☐ |
| C5 | Phased rollout w/ human-in-the-loop | Phases with exit criteria | ☐ |
| C6 | Needs from PayGuard | Concrete list | ☐ |
| C7 | Length/tone | 1–2 pages, technical-executive, no filler | ☐ |

### Deliverables / policy
| ID | Requirement | Status |
|---|---|---|
| D1 | Runs from clean env (fresh venv + fresh clone tested) | ☐ |
| D2 | README: setup, approach, results, what was cut and why | ☐ |
| D3 | `memo.md` | ☐ |
| D4 | `AI_USAGE.md` accurate and specific | ◐ |
| D5 | Live-session rehearsal (walkthrough + 3 modifications) | ☐ |
| D6 | Optional ≤ 5 min screen recording | ☐ |

---

## 3. Architecture

### 3.1 Repository layout
```
pay-guard/
├── SCOPE.md            # frozen contract
├── SPECS.md            # this file
├── CLAUDE.md           # instructions for Claude
├── AI_USAGE.md         # disclosure log (auto-updated)
├── README.md           # setup, approach, results, cuts
├── memo.md             # Part C
├── pyproject.toml      # or requirements.txt
├── .env.example        # API key names only; never commit .env
├── data/               # gitignored; download instructions in README
│   ├── raw/
│   └── processed/
├── part_a/
│   ├── data.py         # load, dedupe, time split
│   ├── train.py        # baseline + stronger model
│   ├── evaluate.py     # metrics, cost model, threshold
│   └── notebook.ipynb  # optional narrative (thin; logic lives in .py)
├── part_b/
│   ├── make_slice.py   # reproducible CFPB sample
│   ├── taxonomy.yaml   # categories + definitions
│   ├── schema.py       # Pydantic TriageRecord
│   ├── prompts.py      # versioned prompts
│   ├── triage.py       # LLM call, retries, fallback, safety rules
│   ├── run_batch.py    # batch over slice, cached outputs
│   ├── evaluate.py     # metrics vs hand labels, cost/latency
│   ├── labels/         # hand labels + labeling guide
│   └── adversarial/    # injection + sensitive-case tests
├── tests/              # small: schema, fallback, safety rules, split leakage
└── outputs/            # metrics, plots, cached LLM responses (gitignored if large)
```

### 3.2 Part A flow
```
creditcard.csv → dedupe/check → time-ordered split (train | val | test)
   → fit scaler on train only → LogReg (class_weight) ─┐
                               → XGBoost ─────┴→ PR-AUC, recall@precision, CI
   → cost model (assumed FP/FN costs) → threshold on validation → report on test once
```

### 3.3 Part B flow
```
CFPB CSV → make_slice.py (filters+seed) → slice.csv
   → [hand labels, made BEFORE model run]
   → for each complaint:
        sanitize/delimit text → LLM (structured output) → Pydantic validate
           ├ invalid → retry w/ error feedback (max N) → fallback record
           └ valid → safety-rule layer (keywords) may force requires_human=true
        → cache result (+ tokens, latency)
   → evaluate.py: per-field metrics, confusion matrix, escalation recall, cost @ 50k/mo
```

### 3.4 Production architecture (memo target, Part B)
`ingest → PII redaction → in-country LLM inference → schema validation + rules → router →
human review queue → audit log → monitoring (golden set, drift, escalation rate)`

### 3.5 Tech choices (defaults; override in decision log)
Python 3.11+, pandas, scikit-learn, XGBoost, Pydantic v2, pytest, matplotlib. LLM provider: **TBD (D-02)**.
Principle: scripts first, thin notebooks only for narrative. Fixed seeds everywhere.

---

## 4. Part A design notes
- **Split:** order by `Time`; e.g. first 70% train / next 15% val / last 15% test. Report class counts per split.
- **Metrics:** PR-AUC (primary), recall at fixed precision (e.g. 90%), confusion matrix at chosen threshold; ROC-AUC secondary only. Bootstrap CI because of ~492 positives.
- **Imbalance:** prefer class weights over resampling; if resampling is used, training fold only.
- **Cost model:** FN cost = transaction `Amount` (+ assumed chargeback fee); FP cost = fixed review/friction cost. Choose threshold on validation; evaluate on test once.
- **Not doing:** tuning grids, stacking, deep nets.

## 5. Part B design notes
- **Taxonomy draft (5–8):** unauthorized_or_fraud, disputes_chargebacks, account_access, fees_billing, payments_transfers_failures, refunds, loans_credit_other, other_unclear. Finalise in M3 and freeze before labeling.
- **Urgency rubric:** high = money lost/at risk now, legal/regulatory threat, safety; medium = blocked service with workaround; low = informational/complaint about past issue.
- **`requires_human` policy:** true if fraud allegation, legal/regulator threat, safety language, low confidence, or fallback. Optimise **recall**.
- **Eval:** category accuracy + macro-F1 + confusion matrix; urgency exact and within-1; `requires_human` recall/precision; summary faithfulness manual check on ≥ 20 samples.
- **Injection:** complaint text wrapped in delimiters, instructed as data; adversarial set checked for category/urgency manipulation.
- **Cost:** record input/output tokens per call; per-complaint cost × 50,000.

---

## 6. Milestones
Time estimates total ≈ 8 h plus buffer. Update checkboxes as work completes.

### M0 — Setup and decisions (45 min)
Why: early decisions prevent rework; starting the AI log now avoids missed disclosure.
- [x] Repo skeleton, dependency file, `.gitignore`, `.env.example`, seeds (`config.py`)
- [x] Resolve open decisions D-01..D-04 (§9)
- [x] XGBoost smoke test passes (libomp installed via brew; 2 tests pass; train + predict verified)
- [x] README setup section incl. macOS libomp note
- [x] `AI_USAGE.md` logging confirmed working
- (README skeleton dropped from M0: written as results appear, not before)

### M1 — Part A baseline (75 min)
Why: the baseline is the yardstick; correct split first means no later number is contaminated.
- [ ] Download data, checks (balance, duplicates, `Time`)
- [ ] Time-ordered split + leakage test
- [ ] Logistic regression baseline + metrics (A1–A3)

### M2 — Part A stronger model, threshold, note (90 min)
Why: comparison and cost reasoning are what graders read.
- [x] Gradient-boosting model, same protocol, variance/CI (A4)
- [x] Cost model + threshold (A5)
- [x] Real-time note (A6), limits (A7)
- [x] README Part A section written

### M3 — Part B slice and taxonomy (45 min)
Why: taxonomy and slice define "correct"; changing them later invalidates labels.
- [ ] `make_slice.py` + documented filters/seed/hash (B1)
- [ ] `taxonomy.yaml` + labeling guide (B2)

### M4 — Part B hand labeling (45 min)
Why: labeling before seeing model output avoids anchoring and reveals taxonomy weaknesses.
- [ ] ≥ 50 labels, ambiguity notes (B7)

### M5 — Part B pipeline (90 min)
Why: robustness before accuracy; caching keeps iteration cheap.
- [ ] Schema, prompt v1, structured output (B3)
- [ ] Retries, fallback, timeouts (B4)
- [ ] Safety-rule layer (B5)
- [ ] Batch run with cache, token/latency logging (B10 part)

### M6 — Part B evaluation and adversarial tests (75 min)
Why: highest-weighted evidence; spend saved Part A tuning time here.
- [ ] Metrics vs hand labels, confusion matrix (B8)
- [ ] Injection + sensitive-case tests (B6)
- [ ] 1–2 measured prompt iterations logged (B11)
- [ ] Cost at 50k/month, scale-measurement plan (B9, B10)

### M7 — Part C memo (75 min)
Why: written last so it is grounded in real findings; cutting to 2 pages makes it executive-grade.
- [ ] Draft per C1–C6, diagram
- [ ] Trim to ≤ 2 pages (C7)

### M8 — Polish and rehearsal (60–75 min)
Why: reproducibility failure is the most avoidable loss; the live session weighs as much as the submission.
- [ ] Clean-env test: fresh venv + fresh clone (D1)
- [ ] README finalised (D2); `AI_USAGE.md` finalised (D4)
- [ ] Rehearse walkthrough + 3 live modifications (D5)
- [ ] Optional recording (D6)

### Buffer: 30–60 min for API limits, download friction, plotting surprises.

**Suggested schedule:** Day 1 = M0–M2 · Day 2 = M3–M6 · Day 3 = M7–M8 + buffer.

---

## 7. Risks and mitigations
| Risk | Mitigation |
|---|---|
| Leakage in Part A | Time split, fit-on-train-only, leakage unit test |
| Noisy metrics (492 frauds) | Bootstrap CI; say so plainly |
| LLM API limits/cost | Cache every response; small model first; slice ≤ 500 |
| Labeling bias | Label before model run; keep guide; note ambiguous items |
| Can't explain code in live session | Keep code simple; rehearse (D5); log "explain-back" in AI_USAGE |
| Scope creep | §11 cut list; SCOPE.md is the arbiter |
| Missed AI disclosure | CLAUDE.md rule: update AI_USAGE.md every working session |

## 8. Definition of done
All §2 rows ☑, D1 verified from a clean clone, README/memo/AI_USAGE complete and consistent with the code, rehearsal done.

## 9. Decision log
| ID | Decision | Status | Rationale |
|---|---|---|---|
| D-01 | Memo covers Part B | **Decided** (user deferred to the brief, which leaves the choice to the candidate; Part B chosen) | More to say on privacy/residency/silent failures; Part A overlaps the real-time note |
| D-02 | LLM provider: Gemini free tier (SDK `google-genai`); exact model chosen in M5 | **Decided** | Free. Risks: rate limits, structured-output reliability unverified, free-tier data-use terms (public CFPB data only; relevant to the memo's residency section) |
| D-03 | Stronger model: **XGBoost** (user's choice; supersedes LightGBM) | **Decided**; needs `libomp` on macOS (installed; documented in README). Fallback: sklearn `HistGradientBoostingClassifier` | Standard, handles imbalance via `scale_pos_weight` |
| D-06 | Drop exact duplicate rows (1,081 copies; 19 fraud) | **Decided** (M1; user asked to inspect first) | Same Time => cannot cross splits, no label conflicts; keeping them double-counts events. Not provable that they are errors |
| D-07 | Split by Time value at 70/85% positions; ties go to the later split | **Decided** (M1) | Prevents timestamp leakage; sizes approximate |
| D-08 | Calibrate before using scores as probabilities in cost model | **Open for M2** | M1 showed severe miscalibration (bin [0.9,1) pred 0.97 vs observed 0.26) |
| D-09 | Rule A (`p*Amount > c`) replaced by Rule B in config v2 after Stage 2a validation results (Rule A cost XGBoost EUR 1,726 at c=5 vs ~EUR 630 reference) | **Superseded by D-10** (kept as history) | Rule B was validation-informed. v1/v2 configs and hashes archived in `part_a/frozen/superseded_v*_config.*` |
| D-10 | **Both rules retained (config v3).** Rule A = original rule specified in the approved M2 proposal before results; primary comparator. Rule B (`p > c/120.29`) = validation-informed secondary operating-policy alternative, an average-loss approximation, not transaction-specific, not independently pre-registered, no claim of theoretical superiority. Both evaluated once on test | **Decided** (user, option 1) | Rule A is principled under its assumptions but did poorly on validation, likely from amount-dependent over-prediction (not proven). Roles fixed before the test set is touched |
| D-04 | Final taxonomy | **OPEN** until M3 | Must be frozen before labeling |
| D-05 | Python 3.12 + uv venv; deps in `pyproject.toml`, pinned `requirements.txt` (pip-compatible) | **Decided** | No uv-only lockfile so reviewers can use plain pip. Tested on macOS arm64 only |

## 10. Open questions for the user
- Which LLM provider (Claude API, other hosted, local)? Is there an API key budget?
- Confirm memo topic (Part B)?

## 11. Cut list (intentional)
Hyperparameter search · ensembling · deep learning · second LLM-provider comparison · real streaming/feature store · UI · large label set (50–60 labels ⇒ wide CIs; stated in README).

---

## 12. Working protocol (summary; full rules in CLAUDE.md)
Proposal → user approval → execute → answer the two review questions → stop → next proposal.
This spec is a guide, not a script: deviations are allowed and must be logged in §9.

## 13. Milestone review log
Short record of the two post-milestone questions. Full answers are given in chat.

| Milestone | What could invalidate this result? | What would a skeptical reviewer say? |
|---|---|---|
| M0 | Pins from one macOS arm64 machine; pandas 3.x is new; Gemini reliability untested | Pins unfiltered (transitive); no fresh-clone proof yet (M8) |
| M1 | 4 FPs decide the 90%-precision threshold; recall tuned on same val data; only 55 val frauds; 2-day window; dedupe choice; drift in fraud rate | Threshold 0.999995 is knife-edge; baseline never tuned; CI ignores split choice; scores uncalibrated |
| M2b (test, single evaluation) | Test has 52 frauds (EUR 6,169 total); PR-AUC fell from validation (LR 0.837->0.700, XGB 0.846->0.757), so validation was optimistic; Rule B's validation advantage did not carry over (XGB c=5: A 2,855 vs B 2,897; c=1: A 1,075 vs B 1,815); cost CIs very wide; both models' missed-fraud EUR at Rule B c=5 identical (2,372), consistent with the same large frauds being missed (not verified); hypothetical costs | XGBoost not shown better than logistic (CI spans 0) and has worse precision at c=5; one fixed time split; test used for reporting only but design decisions (Rule B) were validation-informed; XGB over-predicts (ratio 1.34) | M2a (v3: Rules A and B) | Amount-band over-prediction >EUR 10 may be prevalence shift + noise, not amount-specific (bands hold 1-31 frauds); both rules rest on hypothetical c; | Rule B assumes one constant loss per missed fraud (train mean EUR 120) while fraud sizes are very skewed (val median EUR 8); depends entirely on the hypothetical c; low thresholds (c=1 -> p>0.0083) sit where calibration is weakest (XGB bin [0.001,0.01): predicted 0.25% vs observed 0.04%); rule choice was informed by validation results; original: Cost rule rests on amount-conditional calibration that was only checked in aggregate; fraud value is concentrated (val fraud median EUR 8, total EUR 8,396, ~all in 24 caught frauds), so costs are noise-dominated; prevalence shift train->val (0.165%->0.129%) biases p up; no test yet; hypothetical costs | PR-AUC gain is within noise; rule worse than simple top-k references (in-sample, so the gap is overstated); XGBoost costs MORE than logistic under the rule; OOF fold 4 has only 28 frauds; untuned XGBoost; p*Amount assumes full prevention |
| M3 | — | — |
| M4 | — | — |
| M5 | — | — |
| M6 | — | — |
| M7 | — | — |
| M8 | — | — |

---

## 14. Progress and goal checklist
Tick items only when verified, not when written. Claude updates this at the end of every milestone.

### 14.1 Milestone gates
For each milestone: proposal drafted → approved by user → executed → two review questions answered → docs updated.

| Milestone | Proposal | Approved | Executed | Review Qs answered | SPECS + AI_USAGE updated |
|---|---|---|---|---|---|
| M0 Setup & decisions | ☑ | ☑ | ☑ | ☑ | ☑ |
| M1 Part A baseline | ☑ | ☑ | ☑ | ☑ | ☑ |
| M2 Part A stronger model, threshold | ☑ | ☑ (+2a/2b gates) | ☑ | ☑ | ☑ |
| M3 Part B slice & taxonomy | ☐ | ☐ | ☐ | ☐ | ☐ |
| M4 Part B hand labeling | ☐ | ☐ | ☐ | ☐ | ☐ |
| M5 Part B pipeline | ☐ | ☐ | ☐ | ☐ | ☐ |
| M6 Part B evaluation & adversarial | ☐ | ☐ | ☐ | ☐ | ☐ |
| M7 Part C memo | ☐ | ☐ | ☐ | ☐ | ☐ |
| M8 Polish & rehearsal | ☐ | ☐ | ☐ | ☐ | ☐ |

### 14.2 Goals achieved? (maps to SCOPE §8 grading criteria)
**Judgment**
- [x] Every metric choice is justified in writing (A2)
- [ ] Every cut is listed with a reason in the README (§11)
- [ ] Limits and optimistic numbers are stated plainly (A7, B8)
- [ ] Decision log is complete and consistent with the code

**Evaluation rigor**
- [x] Part A: no leakage (time split, fit-on-train-only, leakage test passes)
- [x] Part A: variance/CI reported; test set used once
- [ ] Part B: hand labels made before viewing model output
- [ ] Part B: "correct" defined per field; `requires_human` recall reported
- [ ] Part B: injection and sensitive-case tests run and reported
- [ ] Part B: scale-measurement plan written

**Code quality**
- [ ] Runs from a fresh clone + fresh venv (D1)
- [ ] Small test suite passes
- [ ] Seeds fixed; slice reproducible (hash matches)
- [ ] No secrets or data committed
- [ ] Code is simple enough to explain line by line

**Communication**
- [ ] README: setup, approach, results, what was cut and why
- [ ] Memo ≤ 2 pages, concrete, diagram included
- [ ] AI_USAGE.md specific and truthful; authorship table final

**Results (least weighted)**
- [x] Part A: baseline vs stronger model compared with reasoning
- [ ] Part B: scores reported honestly, including failures

### 14.3 Final submission checklist
- [ ] All SCOPE §7 deliverables present (code, README, memo, AI_USAGE; optional recording)
- [ ] SCOPE.md unchanged since creation (unless user requested edits)
- [ ] SCOPE §3–§5 "Required" items each verified against this spec (§2 all ☑)
- [ ] Repo pushed to GitHub; link works for reviewers
- [ ] Live-session rehearsal done: walkthrough of every file + 3 live modifications (e.g. swap metric, change threshold, add a category)
- [ ] Can explain every line and every decision without notes
