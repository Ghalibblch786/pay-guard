# SPECS.md — PayGuard Build Specification

> Living document. Replaces PLAN.md. Claude keeps the **Status** columns, the **Decision log**,
> and the **Milestones** checkboxes current as work progresses. It must never contradict
> `SCOPE.md` (frozen). If it would, stop and ask the user.

Last updated: 2026-11-28 · Current milestone: **Pushed; author review and rehearsal outstanding**

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
| A2 | Justified metrics | README states why PR-AUC leads, why accuracy is not used; recall @ fixed precision reported | ◐ metric choice justified; recall at fixed precision is not reported in README (earlier ☑ was wrong) |
| A3 | Baseline model | Logistic regression (class-weighted), metrics reported | ☑ (val) |
| A4 | Stronger model | XGBoost, same split/metrics, compared to A3 with variance estimate | ☑ (test: XGB 0.757 vs LR 0.700, paired diff +0.046, CI [-0.031, +0.152]: not significant) |
| A5 | Threshold + cost discussion | Explicit cost model with stated assumptions; threshold chosen from it; FP vs FN trade-off table/plot | ☑ README: operating point (D-35, chosen after test results, labeled so) and both error costs; no plot, tables only |
| A6 | Real-time inference note | ≤ 1 page: latency, history-dependent features, label delay, drift, PCA-anonymized feature limitation | ☑ (README; explicitly not a production implementation) |
| A7 | Honest limits | Only 492 frauds → noisy metrics; dataset is 2 days, anonymized; stated in README | ☑ (README) |

### Part B — LLM triage
| ID | Requirement | Acceptance check | Status |
|---|---|---|---|
| B1 | Reproducible CFPB slice | Filters, date range, seed, row count, file hash documented; script regenerates it | ☑ (rebuild from the public archive matched the manifest hash) |
| B2 | Taxonomy (5–8 categories) | Definitions + `other` escape hatch in `taxonomy.yaml`; used by prompt and labeling guide | ☑ (`taxonomy.json`; never piloted on real data) |
| B3 | Structured output | Pydantic schema with enum-constrained `category`/`urgency`; all 5 fields present | ☑ |
| B4 | Failure/retry handling | Bounded retries with validation error fed back; timeouts; rate-limit backoff; safe fallback record (`requires_human=true`, `category=other`); no dropped rows | ☑ (synthetic tests; real runs needed no retries) |
| B5 | Safety rules | Deterministic keyword/regex layer forces `requires_human=true` for fraud allegations, legal threats, regulator mentions, safety/self-harm language | ☑ |
| B6 | Prompt-injection defence + tests | ≥ 3–5 adversarial complaints; delimiters + data-not-instructions prompt; results reported | ☑ run and reported: 6/9; model followed the downgrade in 3/3, rules caught 2 |
| B7 | Hand-labeled eval set | ≥ 50 complaints labeled **before** viewing model output; labeling guide; ambiguity noted | ☑ 30 labels (target of 50 superseded, D-34; SCOPE asks for a small sample) |
| B8 | Evaluation | Per-field metrics; confusion matrix; urgency scored ordinally; `requires_human` recall emphasised; summary faithfulness spot-check | ☑ summary faithfulness: 10 rated (1 faithful, 8 minor omission, 1 unsupported); see 9q |
| B9 | Scale measurement plan | README section: audited sampling, agreement, distribution drift, escalation rate | ☑ |
| B10 | Cost/latency | Tokens + latency measured on slice; extrapolated to 50k/month with assumptions | ☑ (server prices are an assumption) |
| B11 | Prompt iteration log | Each prompt version + score recorded | ☑ |

### Part C — Memo
| ID | Requirement | Acceptance check | Status |
|---|---|---|---|
| C1 | One prototype chosen | Part B (recommended; confirm in §9) | ☑ (Part B) |
| C2 | Architecture diagram | Simple, in-memo | ☑ |
| C3 | Monitoring of silent failures | Each failure paired with a concrete detector and threshold | ☑ |
| C4 | Data: privacy/residency/retention | In-country inference decision, PII redaction before model calls, retention rule | ☑ |
| C5 | Phased rollout w/ human-in-the-loop | Phases with exit criteria | ☑ |
| C6 | Needs from PayGuard | Concrete list | ☑ |
| C7 | Length/tone | 1–2 pages, technical-executive, no filler | ☑ (2 A4 pages in a Chrome render, 10 pt) |

### Deliverables / policy
| ID | Requirement | Status |
|---|---|---|
| D1 | Runs from clean env (fresh venv + fresh clone tested) | ☑ fresh `git clone` of `a1ab783` (macOS): install, tests, sample rebuild, Part A validation check; model runs not repeated there |
| D2 | README: setup, approach, results, what was cut and why | ☑ Part A download and run instructions added (derived from the code; commands not re-run); results summary and key files first |
| D3 | `memo.md` | ☑ |
| D4 | `AI_USAGE.md` accurate and specific | ◐ current; author to confirm accuracy |
| D5 | Live-session rehearsal (walkthrough + 3 modifications) | ☐ |
| D6 | Optional ≤ 5 min screen recording | ☐ (optional; not done) |

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
- [x] Download data, checks (balance, duplicates, `Time`)
- [x] Time-ordered split + leakage test
- [x] Logistic regression baseline + metrics (A1–A3)

### M2 — Part A stronger model, threshold, note (90 min)
Why: comparison and cost reasoning are what graders read.
- [x] Gradient-boosting model, same protocol, variance/CI (A4)
- [x] Cost model + threshold (A5)
- [x] Real-time note (A6), limits (A7)
- [x] README Part A section written

### M3 — Part B data source, sanitizer, sample, taxonomy, labeling and evaluation design (revised; NOT implemented beyond data verification)
Why: fixes what "correct" means before any model exists; changing taxonomy/slice after labeling invalidates labels.
- [x] 3a-3d. Source verification: official June 2026 export downloaded, hashed, fully inspected (aggregates only); D-16 accepted
- [x] 3e-1. (DONE 2026-11-26; see section 9f) Install pinned spaCy + local model; sanitizer, sensitive-content flagger and ~100 synthetic tests (no real text)
- [x] 3e-2. (DONE 2026-11-26; see section 9g) Aggregate-only sanitizer run over the eligible population (replacement counts, residual scan, flag rates, failures)
- [~] 3e-2b. (DONE) D-27 fixes + Step 2 re-run, results in 9h; optional flag audit prepared (D-28)
- [x] 3e-2c. D-29 steps 1-3 done, run and accepted; overwrite safeguard (9j) accepted by user; hash saving in the 3e-3 review script still to build
- [x] 3e-3. User reviewed 30 sanitized narratives locally: batch 1 FAILED (9m)
- [x] 3e-4. Sign-off decision recorded: NOT signed off (9m)
- [x] 3e-5. `make_slice.py`: dedup (SHA-256) + 30-1,500 words + balanced pilot (5 x 4) + proportional main (~400) + label/extension order; local gitignored manifest
- [-] 3e-6. DROPPED (D-32): sanitized pilot reviewed (Claude reads only after the user's explicit go-ahead); taxonomy and labeling guide drafted with the user
- [x] 3e-7. Freeze taxonomy, guide, sampling procedure and evaluation plan with hashes; blank local label sheet (sanitized text only; columns include `contains_sensitive`)
- [x] 3e-8. Tests (dedup, length rule, disjointness, proportional allocation, reproducibility) and docs

### M4 — Part B hand labeling (45 min)
Why: labeling before seeing model output avoids anchoring and reveals taxonomy weaknesses.
- [x] 30 labels by the author, 1 marked ambiguous (B7; ≥ 50 superseded by D-34)

### M5 — Part B pipeline (90 min)
Why: robustness before accuracy; caching keeps iteration cheap.
- [x] Schema, prompt v1, structured output (B3)
- [x] Retries, fallback, timeouts (B4)
- [x] Safety-rule layer (B5)
- [x] Batch run with cache, token/latency logging (B10 part)

### M6 — Part B evaluation and adversarial tests (75 min)
Why: highest-weighted evidence; spend saved Part A tuning time here.
- [x] Metrics vs hand labels, confusion matrix, 10 summary ratings (B8)
- [x] Injection + sensitive-case tests (B6)
- [x] 1–2 measured prompt iterations logged (B11)
- [x] Cost at 50k/month, scale-measurement plan (B9, B10)

### M7 — Part C memo (75 min)
Why: written last so it is grounded in real findings; cutting to 2 pages makes it executive-grade.
- [x] Draft per C1–C6, diagram
- [x] Trim to ≤ 2 pages (C7)

### M8 — Polish and rehearsal (60–75 min)
Why: reproducibility failure is the most avoidable loss; the live session weighs as much as the submission.
- [x] Clean-env test: fresh clone + fresh venv passed (D1)
- [~] README finalised (D2); `AI_USAGE.md` updated, awaiting author confirmation (D4)
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
| CFPB removed narratives from live data (verified: CSV header) | Use the official FOIA Narratives Archive (D-11); verify its structure with one small export before anything else |
| Prefix-based estimates were misleading (Stage 3c prefix said 10.1% narratives overall; the full June file has 2.71%): never size or choose data from prefixes; use full-file aggregates | Done for June 2026 (Stage 3d) |
| Recent archive exports may contain no narratives (Aug 2026: 0.00%) | Locate which exports have narratives via approved, bounded probes before choosing the pool; if none usable, escalate to user (HF mirror only with explicit approval) |
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
| D-11 | **Part B data source: official CFPB FOIA Narratives Archive** (https://www.consumerfinance.gov/foia-requests/foia-electronic-reading-room/cfpb-consumer-complaint-database-narratives-archive/). Reason: the live CFPB CSV has no narrative column (verified 2026-11-26). The BEE-spoke-data Hugging Face mirror is NOT to be downloaded or used unless the official archive proves unusable AND the user explicitly approves | **Decided** (user) | Official source, same provider. Archive file structure/fields are UNVERIFIED until a first export is downloaded (needs approval). The user has already informed Stixor; no further email to Stixor |
| D-14 | Aug 2026 export has 1 of 667,140 narratives (accepted as a documented finding). Stage 3b found narratives in all four older exports probed (prefix-based estimates, see M3 Stage 3b findings). Narrative availability declines over time (38.5% -> 27.9% -> 26.7% -> 15.9% -> 0.0%) | **Resolved in part** (user accepted the finding; continue with the official archive only) | Aug 14 date discrepancy: no official explanation found (FOIA index lists the archive as 'Created AUG 14, 2026'; the Aug file has receipts to Aug 31 and sent-to-company dates to Sep 11). Not treated as an error |
| D-15 | Download of `CCDB_Export_19_June_2026.zip` | **Done** (user-approved; Stage 3d) | See D-16 and section 9d |
| D-16 | **ACCEPTED (user, 2026-11-26): Part B dataset = official CFPB FOIA archive export `CCDB_Export_19_June_2026.zip`** (19,624,767 bytes; SHA-256 `3021c8af9eeed4971a92f15be21c7ce08cf3c1337151de255e5b12bf782049df`; 620,794 records; 16,820 non-empty narratives; 7,671 in the four payment products; full CRC test passed). Limitations carried forward: ONE month; only complaints whose narratives were published (publication-selection bias); narratives concentrated in the first file deciles (payment fill 75.7/74.6/72.8/16.1/13.0/0.1/0/0/0.1/0 %), so prefix estimates were misleading (10.1% vs 2.71% overall); unexplained day-level gaps (six days <=3% payment fill); CFPB states complaints are not representative; narratives from a transitional period before CFPB removed them | **Decided** | Evidence in section 9d |
| D-17 | **APPROVED (user, 2026-11-26): exact deduplication with SHA-256.** Normalization: Unicode NFC + collapse whitespace + strip (case and punctuation kept); SHA-256 of the normalized text, computed locally; keep the earliest Date received, ties by smallest Complaint ID; no near-duplicate merging. Impact (payment narratives): 34 extra copies (0.44%): card 24, money transfer 9, checking 1, prepaid 0; 14 groups, largest 13; 57% of groups span >1 company, 29% >1 state, 36% >1 date (likely form letters from different consumers, whose frequency information is discarded). Aggregates recomputed with SHA-256: identical | **Approved** | Hashes and IDs stay in gitignored local files
| D-18 | **APPROVED (user): length eligibility 30-1,500 words, applied after dedup.** Excludes 230 narratives below 30 words (3.0%) and 31 above 1,500 (0.4%); eligible population 7,376 (3,155 checking / 2,723 card / 1,290 money transfer / 208 prepaid). Results do not cover the excluded 3.4%; out-of-range inputs would route to a human in production | **Approved** | Direction of selection bias unknown
| D-19 | **APPROVED: layered conservative sanitizer** (normalization; deterministic patterns; name cues; local spaCy NER; CFPB `XXXX` -> `[REDACTED]`; amounts, durations and company names kept), fail-closed, synthetic-only tests, no anonymization claim | **Approved** | Implementation awaits plan approval
| D-20 | **APPROVED: balanced pilot of 5 complaints per product (20 total)**, disjoint from the main sample by ID and by text hash; main sample ~400 proportional (about 148 / 171 / 70 / 11) drawn from the eligible population after removing the pilot; user labels 60 (about 22 / 26 / 10-11 / 2); extension batch of 20 if <12 requires_human, maximum 80 | **Approved** | Prepaid and money transfer are exploratory
| D-21 | **APPROVED: label the SANITIZED text** (the exact LLM input), with CFPB Product and Issue hidden; Issue only as a weak post-labeling check | **Approved** | Avoids label/input mismatch
| D-12 | Part B data protection: narratives never committed; full Complaint ID manifest local + gitignored; commit only code, source details, hashes, filters and aggregate statistics; scan for residual PII; sanitize before any external LLM call; document the procedure | **Decided** (user) | Narratives are real consumer text that CFPB withdrew from the live database |
| D-13 | Sampling/labeling parameters: ~400 main sample, payments-relevant products (names verified from data), proportional stratified, seed 42, separate pilot (disjoint), label 60, relabel 15 after a break, if <12 requires_human add one random batch of 20, max 80; CFPB Product/Issue hidden while labeling (Issue only a weak post-hoc check) | **Decided** (user) | See M3 proposal |
| D-22 | spaCy 3.8.18 + `en_core_web_sm` 3.8.0 installed (wheel SHA-256 `1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85`, 12,806,118 bytes, from the official explosion/spacy-models GitHub release; zip integrity passed) | **Done** | Local only; 29 packages added, no existing pin changed; `uv pip check` clean |
| D-23 | **Sensitive-content policy (user):** narratives flagged as sensitive are NEVER sent externally; they are routed straight to human review (`requires_human=true`, no LLM) AND are kept in the sample and the evaluation so `requires_human` performance is not artificially weakened. Evaluation reports end-to-end `requires_human` recall AND recall on the non-routed (LLM-handled) subset, the flagged-but-not-requires_human workload, and the flagger's own recall. A `contains_sensitive` label column is added to the labeling sheet (proposed, needs approval in the revised plan) | **Approved in principle** | Flagging is applied AFTER sampling, so flagged items stay eligible. Category/urgency are scored only on LLM-handled items |
| D-24 | **APPROVED: user reviews 30 random sanitized narratives locally** (outside this chat, recording only leak counts by type). Limitation: 0 leaks in 30 gives a 95% upper bound of ~9.5% leaky narratives per narrative, so it reduces risk but does not prove safety | **Approved** | Sanitizer fixes must be rule-level, not item-specific; a fresh sample is drawn after any fix |
| D-25 | `outputs/m3*.json` added to `.gitignore` (Part B aggregate outputs stay local; Part A outputs remain tracked) | **Done** | Verified with `git check-ignore` |
| D-26 | **Step 1 refinements (user):** (1) `contains_sensitive` is a human-labeling field; it is labeled on SANITIZED text, which may conceal evidence, so its ground truth is limited in accuracy (documented). (2) Sensitive categories include financial account details, bank routing numbers, passwords, security answers and authentication credentials (implemented). (3) Flagged narratives stay in the evaluation but go straight to human review; they are NEVER sent to an external LLM and NEVER included in the pilot text shared with Claude. (4) If flagged records are removed from the externally reviewed pilot they are replaced by eligible records from the same product where possible; the ORIGINAL local manifest is preserved and every replacement is documented in a separate local log. (5) PII redaction (`sanitizer.py`, rewrites text) is kept strictly separate from sensitive-content detection (`sensitive_flags.py`, never rewrites; runs on raw text locally) in code, tests and docs | **Decided** | (4) will be implemented in Step 5 |
| D-27 | **APPROVED and IMPLEMENTED (user, 2026-11-26):** (1) loose 'word at domain.tld' email rule removed; (2) NER spans containing critical fraud/dispute terms (fraud, scam, chargeback, unauthorized, stolen, phishing, hacked, dispute, refund, theft, ...) are never redacted; (3) exact payment-brand allowlist Zelle, Venmo, Cash App, Citi, Visa, Mastercard (whole NER span must equal the brand; 'Visa Patel' is still redacted); the old hard-coded protected-company list was deleted, the company list now comes only from the caller (Company column); (4) NER runs up to two passes, stopping when the text is stable | **Implemented** | 13 new tests (deterministic stub NER); suite 182 passing; Step 2 re-run on the same 7,376 narratives |
| D-28 | Optional 20-item sensitive-flag audit (user-approved): local gitignored files `data/processed/flag_audit/` (mode 600); items stratified across the 7 categories (rarest-category assignment, seed 7001; quotas 3,3,3,3,3,3,2 = 20; 29 verdict rows because multi-flag items are judged per category); user records y/n/u in a sheet that contains no text; EXPLORATORY ONLY: flagged narratives only, so no information on false negatives and not a reliable per-category precision | **Prepared; awaiting user inspection** | No hashes or IDs saved for audit items, so they are not excluded from the later sample (small contamination risk, decide at Step 5) |
| D-29 | **APPROVED, Variant A (user, 2026-11-26); steps 1-3 (audit export, shared helper, synthetic tests) IMPLEMENTED, see 9j; review-script hash saving and `make_slice.py` integration PENDING:** exclude the 20 flag-audit records and every 30-record sanitizer-review iteration from BOTH the pilot and the main sample. Approved safeguards: only SHA-256 hashes, stored locally in gitignored storage (`data/processed/exclusions/`, mode 600; no Complaint IDs, no text); exactly the D-17 normalization (NFC + whitespace collapse, case and punctuation kept); fail closed if the exclusion file is missing; aggregate exclusion counts only; synthetic tests for normalization consistency, exclusion behaviour and missing-file handling. Audit hashes to be recovered by re-running the seeded selection with a byte-identity check against the existing items file (abort if different); review hashes written when each review sample is generated. Expected cost: ~50 of 7,376 records (0.7%); rare sensitive categories lose a larger share (self-harm 3 of 7, immigration/legal 3 of 46) | **Approved (implementation deferred)** | Implementation order: hash export with safeguard, shared exclusions helper, review script (Step 3), `make_slice.py` integration (Step 5), tests, docs |
| D-30 | **Step 3 leak-review design APPROVED (user, 2026-11-26) with two clarifications:** 30 simple-random narratives from the UNFLAGGED, never-reviewed pool (narrows D-24's '30 random sanitized narratives'); local-only review; hash exclusions + two agreeing batch records; three-batch cap; retest needs changed sanitizer or flagger. Clarifications: (1) `missed_sensitive` renamed `visible_sensitive` = sensitive content visibly remaining in the sanitized text, NOT a flagger-recall or missed-flag measure; (2) `indirect_concern` defined with examples in `part_b/review_guide.md`. Pass rule: all 30 items `n` on direct_leak, indirect_concern and visible_sensitive; any `y` or `u` fails, no waiver | **Approved; tooling implemented (9k); real batch NOT approved** | The strict rule on subjective indirect identifiers may fail all three batches; then there is no external-use sign-off and the next move is a new decision |
| D-31 | **M3 completion plan APPROVED (user, 2026-11-26), with review guide and Step 3 tooling accepted:** Run A (card/account 4-digit rule, Step 2 re-run, remaining tools, drafts, batch 1), stop for review, Run B (decision, pilot, main sample), stop for pilot check, Run C (freeze, label pack, closure). Changes to earlier plan: AI does NOT read any real narrative, including the pilot (supersedes plan step 6); M3 may close without sanitizer sign-off (sign-off only gates external sending); the sign-off decision is final before sampling and no review batch may follow it; `contains_sensitive` renamed `visible_sensitive` and compared with flags as a 2x2 table, NOT flagger recall (supersedes that part of D-26 and the earlier eval plan). Taxonomy file is JSON, not YAML (no extra dependency) | **Approved; Run A done** | One person is reviewer, labeler and co-author of the taxonomy |
| D-32 | **Revised execution strategy (user, 2026-11-27):** finish within 2-3 hours; stop the sanitizer review (no new batch, no further fixes proposed); keep real complaint text local; AI takes ordinary implementation decisions and asks only when essential. Batch 1 recorded exactly as the author's sheet stood (FAILED); sign-off decision `not_signed_off`. To limit author effort, dropped: pilot check/labels, relabeling, extension, visible-sensitive field; label target reduced to the first >=30 of the frozen order with 3 fields (pending the author's explicit acceptance: SCOPE requires hand labels). D-02 (Gemini) SUPERSEDED: local Ollama `llama3.2:3b` (Llama community licence). D-23 kept: flagged records get no model call. Prompt versions compared on synthetic cases only | **Applied** | Taxonomy never checked on real data; one labeler; small n; small model chosen for an 8 GB laptop |
| D-33 | **Provider (user, 2026-11-27): stay local.** The author considered free Gemini and Groq. AI checked the terms that day (Gemini unpaid: content used to improve products, possible human review, 'do not submit ... personal information'; Groq: no retention by default, logs up to 30 days in some cases, ZDR available, US storage, data page silent on training) and advised against sending real complaint text, because redaction is not signed off. Nothing was sent to either | **Decided** | Small local model only; no hosted comparison |
| D-34 | **Evaluation closed at N=30 (2026-11-27).** The author labeled the first 30 of the frozen order (allowed by the frozen plan, N>=30); this supersedes the earlier >=50 target. Results show the system escalates every real record; no prompt or rule change after scoring. Checks added after seeing scores (Wilson bound, majority macro-F1 and urgency baselines, main-run escalation totals; `posthoc_checks.py`) are marked post hoc. AI changed the memo recommendation from funding shadow mode to funding offline evaluation only (author agreed, 2026-11-27). | | |
| D-35 | **Suggested operating point (user approved 2026-11-27, on AI's recommendation): logistic regression, Rule B, c = EUR 5, as a trial starting point.** Chosen AFTER test results: not an independent test, not part of the frozen config; no Part A code or result changed or rerun. Money outcome is essentially tied with Rule A; Rule B is much worse at c = 25. | | |
| D-36 | **Presentation and dashboard (user approved the plan, 2026-11-28).** README rewritten for a CTO with detail moved to `docs/technical_notes.md`; local Streamlit dashboard added (supersedes the no-UI cut in section 11 so a non-technical reader can see both prototypes run; it is not a chatbot, and the batch pipeline remains the Part B deliverable); fraud screen uses validation rows only; complaint screen uses invented or typed text and saves nothing typed; six scripts deleted (`summarize_review.py` and `inspect_archive.py` kept because tests or sample rebuilding use them; the Amount-band result file kept because the frozen config mentions it); SPECS and SCOPE moved to `docs/process/`. Frozen files and results unchanged. | | |
| D-04 | Final taxonomy | **OPEN** until M3 | Must be frozen before labeling |
| D-05 | Python 3.12 + uv venv; deps in `pyproject.toml`, pinned `requirements.txt` (pip-compatible) | **Decided** | No uv-only lockfile so reviewers can use plain pip. Tested on macOS arm64 only |

## 9b. M3 Stage 3b findings (bounded range probes; aggregates only; no narrative text read)
Method (validated on the downloaded Aug file: central directory over HTTP matches the local zip; a 2 MB compressed prefix inflated to
31.9 MB that is byte-identical to local decompression). Only PREFIXES of a deflate stream are decodable, so each estimate uses the first
~3 MB compressed. Row order is only roughly random (date-rank vs row-index correlation 0.11-0.46), so prefixes are NOT random samples
and the Wilson CIs below understate real uncertainty.

| Export (file size) | Records inspected | Non-empty narratives (prefix) | Payment-related with narrative (prefix): card / checking / money transfer / prepaid | Median words |
|---|---|---|---|---|
| Aug 2026 (10.5 MB; full file) | 667,140 | 1 (0.00%) | 0 | n/a |
| Nov-Dec 2025 (63.9 MB) | 42,926 | 6,812 (15.9%) | 896: 364 / 338 / 151 / 43 | 115 |
| Jul-Aug 2025 (84.2 MB) | 32,759 | 8,761 (26.7%) | 732: 265 / 280 / 164 / 23 | 128 |
| Jan-Feb 2025 (75.5 MB) | 31,826 | 8,880 (27.9%) | 735: 300 / 278 / 110 / 47 | 111 |
| Sep 2023-Mar 2024 (100.9 MB) | 25,068 | 9,647 (38.5%) | 1,373: 673 / 498 / 148 / 54 | 117 |

All four expose the same 16 columns including Complaint ID, Product, Issue, Date received and the narrative; no consent column. All four
payment-related product names appear with the same exact current names in every export. Residual-PII regex hits are rare but nonzero (e.g. 0-1 emails, 0-1 phones,
6-76 URLs, 12-41 5-digit/ZIP-like strings per thousands of narratives); 'XXXX' redaction tokens appear in ~58-75% of narratives.
Regexes do not guarantee anonymization.

## 9c. M3 Stage 3c findings (bounded probes of the six 2026 exports; aggregates only)
Same validated method (method re-validated: central directory matches, prefix byte-identical to local decompression). For all six: zip method 8,
local header name/method match the central directory, no zlib error, the 16 columns are identical to the reference, stream truncated as expected
(the whole-member CRC cannot be checked on a prefix). **Prefix counts are not full-export counts and are not representative:** within each 2026
prefix 54-94% of rows come from a single week of Date received; narrative fill varies from 0.3% to 64% across weeks; first-half vs second-half
fill falls in all six exports (e.g. Apr 3.4% -> 1.3%); product-run tests show non-random order. Do not compare prefix counts across exports (prefixes are 8-18% of 2026 files vs 3-5% of the earlier ones).

| Export (file) | Prefix share of file | Records | Narratives (halves) | Payment records -> narratives (fill) | Card / checking / money transfer / prepaid | Median words |
|---|---|---|---|---|---|---|
| Sep 2023-Mar 2024 (100.9 MB) | 3.0% | 25,068 | 38.5% (39.5/37.5) | 2,240 -> 1,373 (61.3%) | 673 / 498 / 148 / 54 | 117 |
| Jan-Feb 2025 (75.5 MB) | 4.0% | 31,826 | 27.9% (27.0/28.8) | 1,505 -> 735 (48.8%) | 300 / 278 / 110 / 47 | 111 |
| Jul-Aug 2025 (84.2 MB) | 3.6% | 32,759 | 26.7% (26.2/27.3) | 1,324 -> 732 (55.3%) | 265 / 280 / 164 / 23 | 128 |
| Nov-Dec 2025 (63.9 MB) | 4.7% | 42,926 | 15.9% (14.3/17.4) | 1,523 -> 896 (58.8%) | 364 / 338 / 151 / 43 | 115 |
| Jan-Feb 2026 (36.8 MB) | 8.1% | 84,202 | 3.5% (4.4/2.5) | 2,902 -> 1,291 (44.5%) | 487 / 500 / 260 / 44 | 157 |
| Mar 2026 (22.1 MB) | 13.6% | 70,986 | 5.1% (5.2/5.0) | 2,280 -> 1,323 (58.0%) | 512 / 528 / 255 / 28 | 146 |
| Apr 2026 (23.0 MB) | 13.1% | 96,160 | 2.4% (3.4/1.3) | 3,394 -> 963 (28.4%) | 351 / 407 / 175 / 30 | 182 |
| May 2026 (21.0 MB) | 14.3% | 72,905 | 4.4% (5.2/3.6) | 3,093 -> 1,322 (42.7%) | 569 / 455 / 251 / 47 | 171 |
| **Jun 2026 (19.6 MB)** | 15.3% | 42,510 | 10.1% (11.3/8.9) | 2,819 -> 2,046 (72.6%) | 755 / 862 / 365 / 64 | 184 |
| Jul 2026 (17.0 MB) | 17.7% | 53,133 | 7.2% (9.4/5.0) | 2,755 -> 1,838 (66.7%) | 695 / 732 / 348 / 63 | 184 |
| Aug 2026 (10.5 MB; full file) | 100% | 667,140 | 0.0% | 0 | 0 | n/a |

## 9d. M3 Stage 3d findings (FULL June 2026 export; aggregates only; no narrative text read, displayed or saved)
File `CCDB_Export_19_June_2026.zip`: 19,624,767 bytes (equals server Content-Length), SHA-256 `3021c8af...82049df`, downloaded 2026-11-26 08:55:35 UTC, gitignored in `data/raw/`;
full CRC test passed (nothing extracted to disk; the CSV is read in memory). 620,794 records, 16 columns, received 2026-06-01..06-30; no duplicate Complaint IDs, no fully duplicated rows.
Empty cells: narrative 603,974; Sub-issue 7,022; Company public response 231,305; Tags 606,941; State 571; ZIP 465.

| Product | Rows | With narrative | % | Narr. >=30 words | Narr. 30-1,500 words | Median words |
|---|---|---|---|---|---|---|
| Credit card | 7,453 | 2,840 | 38.1% | 2,754 | 2,744 | 217 |
| Checking or savings account | 7,671 | 3,270 | 42.6% | 3,172 | 3,156 | 203 |
| Money transfer, virtual currency, or money service | 3,037 | 1,340 | 44.1% | 1,303 | 1,299 | 190.5 |
| Prepaid card | 523 | 221 | 42.3% | 209 | 208 | 171 |
| **Payment-related total** | 18,684 | **7,671** | 41.1% | 7,438 | 7,407 | 205 |
| All products | 620,794 | 16,820 | 2.71% | | | 182 |
(credit reporting: 565,831 rows, 751 narratives = 0.13%; debt collection 18.5%).

Prefix (Stage 3c) vs full file: overall fill 10.13% vs 2.71% (prefix overstated ~3.7x); payment-product fill 65-79% vs 38-44%. Narratives are concentrated by FILE POSITION: payment fill by file decile = 75.7, 74.6, 72.8, 16.1, 13.0, 0.1, 0, 0, 0.1, 0 percent, so the first-15% prefix over-represented the narrative-rich region.
By receipt week payment fill is 30-50% (no monotone trend in June). By DAY it is very uneven and unexplained: six days (Jun 4, 5, 13, 19, 20, 27) have <=3% payment fill (e.g. 8 of 399) next to ~40-60% on other days.
Duplicate narrative texts: 1,772 rows share a text with another row (1,440 extra copies, 8.6% of narratives). Word counts, all narratives: median 182, mean 238.6, p95 632, max 4,136; payment narratives: median 205, mean 256.6, p95 650, max 3,131.
PII-pattern counts over all 16,820 narratives: email 0, US phone 0, SSN-like 0, 9+ digit 0, card-like 0, street address 0, URL 21 (22 matches), ZIP-like 23 (34), date-like 8; 'XXXX' redaction in 13,771 (81.9%), redacted-amount braces in 7,314 (43.5%).
These regexes cannot detect names, free-text addresses without a street suffix, employers, medical details or account fragments; redaction tokens show redaction was applied, not that text is anonymous.

## 9e. M3 Stage 3e planning aggregates (payment-related narratives, June 2026; `outputs/m3e_dedup_length_aggregates.json`; counts only)
| Product | Narratives | Duplicate copies removed | After dedup | <30 words | >1,500 words | Eligible (dedup, 30-1,500) | Proportional share of 400 |
|---|---|---|---|---|---|---|---|
| Credit card | 2,840 | 24 | 2,816 | 83 | 10 | 2,723 | 147.7 |
| Checking or savings account | 3,270 | 1 | 3,269 | 98 | 16 | 3,155 | 171.1 |
| Money transfer, virtual currency, or money service | 1,340 | 9 | 1,331 | 37 | 4 | 1,290 | 70.0 |
| Prepaid card | 221 | 0 | 221 | 12 | 1 | 208 | 11.3 |
| **Total** | 7,671 | **34** | 7,637 | 230 | 31 | **7,376** | 400 |
Alternative length cut-offs (before dedup): <20 words 101; <50 words 542; >1,000 words 106; >2,000 words 9. Eligible-narrative words: p25 121, median 211, p75 333, p95 637.5.

## 9f. M3 Step 1 results (synthetic data only; no real narrative was processed)
Files: `part_b/sanitizer.py` (PII redaction), `part_b/sensitive_flags.py` (sensitive-content detection), `tests/test_sanitizer.py` (139 parametrized test cases), `tests/test_sensitive_flags.py` (19 cases): 158 new cases; whole suite 165 passing (7 from Part A/setup).
Sanitizer layers: normalization; e-mail (incl. obfuscated); URL; dates (numeric incl. CFPB-masked, ISO, textual day+month); SSN-like; ZIP+4 and ZIP with context; phones; last-4 / masked numbers; long digit runs, alphanumeric IDs and cue+number ids (not when they look like money); addresses and PO boxes; name cues (case-insensitive 'my name is', honorifics, closings); employer cues; CFPB `XXXX`; local spaCy NER for PERSON and GPE/LOC (protected brand list). Fail-closed `try_sanitize`.
Measured on invented names: NER-only surname removal 19/20 (Capitalized) and 14/20 (lowercase); with the 'my name is' cue 20/20 for both. First-pass tests passed immediately, so adversarial synthetic probing was run: it found leaks (alphanumeric IDs, 5-digit account numbers, lowercase closing name, half-redacted `(at)` e-mail, a false positive on non-dollar amounts) that were fixed with general rules and regression tests.
Known limitations (also asserted in a test): lowercase names with no cue and no NER hit, street names without a number, dates without a year, `XXXX 1234`, 4-digit account fragments after 'card'/'account', employers and indirect identifiers, amounts without a currency marker may become `[NUMBER_ID]`. Sensitive-content rules are blunt keyword patterns: false positives cost human workload, false negatives are a privacy risk; their real false-positive rate on the data is unknown until Step 2.

## 9g. M3 Step 2 results (in memory, counts only; `outputs/m3_step2_sanitizer_aggregate.json`, `outputs/m3_step2_diagnostics.json`, both gitignored)
Eligible population reproduced exactly (7,376 = 3,155 checking / 2,723 card / 1,290 money transfer / 208 prepaid). Protected terms: 111, built ONLY from the Company column (62 companies with >=25 payment-product complaints; my threshold).
Processing failures: 0 (sanitizer) / 0 (flagger). Narratives changed: 6,873 (93.2%). Replacements: [REDACTED] (CFPB `XXXX`, not ours) 89,382 in 6,656 narratives; [DATE] 7,650 in 2,288 (31.0%); [PERSON] 2,942 in 1,444 (19.6%); [LOCATION] 2,187 in 1,156 (15.7%); [URL] 136 in 89; [LAST4] 32 in 16; [NUMBER_ID] 13 in 10; [EMAIL] 8 in 8; [ADDRESS] 7; [EMPLOYER] 6 in 5. Median 9 replacements per narrative (p95 44); 903 narratives (12.2%) have >10% placeholder words (mostly CFPB's own tokens).
Sensitive flags (never sent externally; 1,349 = 18.29% of eligible): card 436 (16.0%), checking 637 (20.2%), money transfer 222 (17.2%), prepaid 54 (26.0%). By category: financial_account_details 400, government_id 369, credentials_authentication 271, health_medical 260, minors 239, immigration_legal_case 46, self_harm_safety 7; 1,131 narratives have one category, 195 two, 23 three or more. Rule false-positive rate unknown.
Residual scan on sanitized text: only 5-digit ZIP-like strings remain (19 matches in 11 narratives); every other pattern 0 (this scan is circular: it uses the same regex family as the sanitizer, so it cannot find what regexes cannot see).
Unexpected behaviour (all attributed by counts-only diagnostics): (1) all 8 [EMAIL] replacements come from the loose rule `word at domain.tld` (the raw data has 0 standard or obfuscated emails): false positives. (2) NER (not the regexes) destroys signal: Venmo lost in 34 of 42 narratives, Zelle 11 of 19, Citi 42 of 250, Cash App 23 of 465, Visa 8 of 94, Mastercard 7 of 51; fraud 6 of 1,788, scam 2 of 350, chargeback 2 of 180. (3) 10 narratives (0.14%) are not idempotent: a second pass finds new people (6) and places (4); regex-only passes are always idempotent, so the first NER pass misses some entities.
PROPOSED fixes (not applied; D-27): remove the `word at domain.tld` email rule; skip NER spans that contain a critical keyword; add a small curated payment-brand allowlist (Zelle, Venmo, Cash App, Citi, Visa, Mastercard, ...) beyond the Company column (needs approval because the Company-only rule was an explicit requirement); run NER up to two passes until stable. Optional: a local audit of ~20 flagged narratives to estimate flag precision.

## 9h. M3 Step 2 re-run after D-27 (same 7,376 eligible narratives; counts only; before-fix copy kept as `outputs/m3_step2_sanitizer_aggregate_v1_before_fixes.json`)
Processing failures 0; narratives changed 6,844 (92.8%, was 6,873). [EMAIL] 8 -> 0 (the 8 false positives are now caught as [URL]: 136/89 -> 144/97). [PERSON] 2,942/1,444 -> 1,970/1,151; [LOCATION] 2,187/1,156 -> 1,704/990 (fewer redactions mostly because brand names are no longer tagged). Unchanged: [DATE] 7,650/2,288; [REDACTED] 89,382/6,656; [LAST4] 32/16; [NUMBER_ID] 13/10; [ADDRESS] 7; [EMPLOYER] 6.
NER skips (first pass): brand allowlist 1,394, company list 587, critical term 69. Passes: 5,600 narratives needed one pass, 1,776 needed two. Idempotence violations 10 -> 0. Sensitive flags unchanged: 1,349 (18.29%); local-only routing 1,349.
Signal survival (raw narratives -> kept): fraud 1,788 -> 1,788 (was -6), scam 350 -> 349 (was -2), chargeback 180 -> 180 (was -2), unauthorized/refund/attorney/lawsuit/dispute/stolen/police/cfpb 100%. Brands: Zelle 19 -> 19 (was -11), Venmo 42 -> 39 (was -34), Cash App 465 -> 464 (was -23), Citi 250 -> 249 (was -42), Visa 94 -> 89 (was -8), Mastercard 51 -> 49 (was -7); not in the allowlist: Discover 54 -> 49, Bank of America 453 -> 450, Chase 514 -> 512.
Attribution of what is still lost (counts only): mostly NER spans that extend beyond the exact brand text (Visa 5, Mastercard 2, Discover 5, Bank of America 3, Chase 2, Venmo 2, Cash App 1) and the URL rule on strings like a brand domain (Venmo 1, Citi 1, scam 1). 'Discover' is also an ordinary verb. Residual scan unchanged: only 5-digit ZIP-like strings (19 matches in 11 narratives); the scan is circular. Runtime 428 s.

### 9i. Sensitive-flag audit results (D-28; user-reviewed, run by the user 2026-11-26)
User ran `part_b/flag_audit_summary.py` and reported its counts: 29/29 verdict rows correct, 0 wrong, 0 unclear (20 narratives, seed 7001).

| Category | Correct / reviewed |
|---|---|
| credentials_authentication | 5/5 |
| financial_account_details | 4/4 |
| government_id | 5/5 |
| health_medical | 3/3 |
| immigration_legal_case | 4/4 |
| minors | 5/5 |
| self_harm_safety | 3/3 |

Question answered per row: "does the narrative really contain that kind of sensitive content?"
**What this supports:** the review surfaced no obvious false-positive pattern, so no flagger change is made on this evidence.
**What it does NOT support (tiny, flagged-only, exploratory audit):** a precision figure (about 3-5 rows per category; rarest-category stratified, not a random sample of the 1,349 flagged; rows share narratives, so they are not independent, and no interval is quoted);
anything about **recall** (unflagged narratives were not reviewed, and a missed flag is the error that would send sensitive text externally); or unbiased judgement (single reviewer, not blind: each item showed the fired categories and highlighted the matches).
It also does not show that the 18.29% local-only routing rate is appropriate.

### 9j. D-29 steps 1-3 (implemented 2026-11-26, user-approved including local access)
- `part_b/exclusions.py`: D-17 `norm` imported from the dedup code (one definition) + SHA-256; owner-only atomic file (0600, folder 0700) holding hash, source tag, date; loading fails closed on a missing, empty or malformed file.
- `part_b/export_audit_hashes.py`: checks the D-16 archive hash, rebuilds the seeded selection in memory (`flag_audit.build_audit`, refactored out of `main()`), and saves only if the rebuilt items file is byte-identical and the 20 hashes are distinct and each match one eligible record. Library error details are suppressed.
- `tests/test_exclusions.py`: 23 synthetic tests; full suite 205 passed.
- Real run: PASS; 20 records verified, 20 rows added, 20 unique hashes; eligible 7,376 -> 7,356 (20 excluded). Both audit files unchanged (content, size, mtime, ctime, mode).
- Limits: nothing consumes the exclusions yet (`make_slice.py` does not exist); exact match after D-17 only, so near-copies of reviewed records can still be sampled; the loader cannot detect an incomplete but well-formed file (e.g. a missing review iteration);
  all 20 exclusions are flagged records chosen with rare-category coverage, so the remaining pool is slightly less sensitive-rich (flagged 1,349 -> 1,329, about 18.29% -> 18.07%, derived); hashes of public text are linkable, so the file stays local;
  ~~`flag_audit.main()` can still overwrite the audit files if re-run, and its write path was not executed after the refactor.~~ (superseded by the safeguard below)
- **User acceptance (2026-11-26):** D-29 implementation and test results accepted, subject to one more safeguard. **Safeguard:** `flag_audit.main()` refuses to run if either output exists (checked before reading the archive; no override flag), creates files in exclusive mode (0600), and on failure removes only files that run created.
  `tests/test_flag_audit_no_overwrite.py`: 9 synthetic tests in temporary folders (existing outputs and filled verdicts untouched, file appearing mid-run, broken symlink, normal generation); full suite 214 passed. The write path is now tested with synthetic content; it was not run on real data, and the real audit files and exclusion file were not accessed.

### 9k. Step 3 tooling (implemented 2026-11-26; synthetic data only)
- Files: `part_b/eligibility.py` (D-17/D-18 population, `sanitize_configured`, fingerprint), `review_batches.py` (records, verification, batch rules, `check_signoff`), `make_review_batch.py`, `summarize_review.py` (preview by default; `--record` is final), `review_guide.md`, `review_batches.json` (empty, to be tracked), `exclusions.load_by_source`; tests `tests/test_review_batches.py` (73).
- Details added during implementation: NER cannot be silently skipped (`sanitize()` skips it when no model is passed); control characters stripped from review text; the guide's hash is frozen per batch; a review folder unknown to the records blocks; a recorded outcome cannot be changed; only the latest batch may be non-failed.
- Results: full suite 287 passed. One-off synthetic end-to-end run with the real sanitizer and local spaCy model passed. Deliberate-fault check: 10 of 11 broken safeguards were caught at first; the miss (output produced without NER) got a test and is now caught. This covers 11 chosen faults, not all.
- NOT done: no real archive, exclusion file or audit file accessed; `load_eligible` and the 111-term check have never run on real data (they fail closed); no real batch; no manual review.
- Limits: a cosmetic edit to the sanitizer or flagger satisfies the changed-code rule (file hash only); a batch removed consistently from both records, the exclusions and its folder is undetectable until the tracked log is committed; the records are not tamper-proof; an interrupted batch blocks with no repair command (by design).
- OPEN: after a PASSED batch, a later code change invalidates sign-off but the approved rule also blocks a new batch; this needs a user decision if it happens (currently fails closed).
- Risk before batch 1: documented sanitizer gaps (4-digit fragments after "card"/"account", lowercase names without a cue, "XXXX 1234") would count as direct leaks under the guide; their frequency on real text is unmeasured.

### 9l. M3 Run A (2026-11-26)
- **Sanitizer rule:** 4 digits directly after card/account wording (also after a single `XXXX`/`****` mask); amounts and year-like values (unless 'number'/'ending'/'#') kept. The first version had a bug: its split-protection guard left digits in synthetic text like "card 4821 3 days ago". The deliberate-fault check exposed it (a fault went uncaught); probing found 8 more missed wordings; both fixed with tests. The first real-data re-run was stopped and restarted after the fix.
- **Step 2 re-run on real data** (`outputs/m3_step2_sanitizer_aggregate_v3_card4.json`, local): 7,376 eligible, 111 protected terms, 0 failures, 0 idempotence violations, 1,349 flagged; every replacement total, critical-term and brand survival count is IDENTICAL to the D-27 run. A counts-only check found the new rule matches **nothing** in the eligible narratives (0 extra replacements; [LAST4] stays 32 in 16 narratives). It guards a synthetic-identified gap but closed no observed leak; it was recommended without first measuring frequency. A looser pattern found 8 occurrences of 4 digits within 20 characters after card/account wording that the rule does not match (not examined).
- **Tools:** `make_slice.py` (decision + sampling), `freeze_plan.py` (versioned hash freeze + blank label pack); `make_review_batch.py` refuses once a decision or sample exists; `eligibility.py` now returns Complaint IDs for the local manifest (changed before batch 1, so it is inside the batch fingerprint).
- **Drafts, written without reading any narrative:** `taxonomy.json` (7 categories incl. `other`), `labeling_guide.md`, `evaluation_plan.md`. The eval-plan draft proposes the 20 pilot records as the labeled DEVELOPMENT set (so prompt iteration is not tuned on the 60); that is 20 extra labels in M4, to be accepted at Run C.
- **Tests:** 347 passed; deliberate-fault check on 11 new safeguards: 10 caught at first, 11/11 after the fix.
- **Batch 1:** generated (`load_eligible` thereby verified on real data); 30 records from an unflagged, unreviewed pool of 6,027 (checking 14, card 9, money transfer 6, prepaid 1); records verify; 50 hashes excluded; owner-only files. AI did not open the review text.

### 9m. Review batch 1 outcome and M3 closure (2026-11-27)
- Recorded: batch 1 **FAILED** (30/30 items failing). direct_leak y=0; indirect_concern y=2; visible_sensitive y=30 (all `financial_account_details`). The two indirect concerns fail the batch by themselves.
- **The visible_sensitive answers are UNRELIABLE and support no conclusion:** they sit uneasily with 0 direct leaks (partial account numbers would count as both); rows 11-30 were first entered as `n` with that category filled and changed to `y` while format errors were being fixed (AI's instructions may have contributed). AI raised this; the author did not confirm either reading and closed the review. AI changed no answer (the author removed a duplicated row and made all edits).
- Decision: **sanitizer not signed off.** No further batches. No real complaint text goes to any external provider.
- Sample: eligible 7,376, 50 reviewed excluded; pilot 20 (3 flagged draws replaced); main 400 (checking 171, card 148, money transfer 70, prepaid 11; 67 flagged); label order 60 (26/22/10/2) + 20 reserve. Plan frozen as `part_b/m3_freeze_v1.json`; local label pack created.

### 9n. M5 and M6 progress (2026-11-27)
- Built: `triage.py`, `llm_client.py` (local only), `prompts.py`, `safety_rules.py`, `run_triage.py`, `evaluate_triage.py`, `reproduce_slice.py`, 20 synthetic development cases, 9 attack cases, tests (suite 394).
- Synthetic prompt results (20 cases): v1 11/20 category, v2 14/20, v3 15/20 (final, by the rule set before scoring; one-case margin). Human-review recall 7/7 for all (model alone); over-escalation 12/13, 9/13, 9/13. All versions: 0/3 fraud cases in the fraud category; v3's targeted fix failed.
- Attack tests v3: 6/9. Failed: direct override (model obeyed; rules still escalated), injection without trigger words (not escalated: most serious), unclear text (wrong category, escalated). No rule or prompt was changed afterwards.
- First evaluation run INVALID: the local server stopped at 14:45:57 (cause unknown, after an HTTP 500); 45 of 60 became fallbacks. AI first misread its progress as speed. Added: batch stops after 3 consecutive server failures; scoring refuses such results. Re-run started.
- The Ollama desktop app started at 14:21 and the first AI-started server exited about then; the pipeline uses a separate server with cloud features off.
- Valid evaluation run: 60/60 (50 model, 10 flagged), 0 retries/errors. Main run: 400/400 (333 model, 67 flagged), 0 retries/errors, 19 min on mains power; latency median 3.6 s, mean 3.9 s (12.5 s mean in the evaluation run on battery under load). The author's Mac was on battery at 9-15% for part of the session.
- Clean-copy check (tracked + untracked non-ignored files only, fresh venv from `requirements.txt`): install ok; 400 passed, 3 skipped (need `creditcard.csv`); `reproduce_slice` rebuilt the sample from the public archive alone and matched the recorded manifest hash. Temporary copy deleted. Not a fresh `git clone` (nothing committed).
- `part_b/label_cli.py`: local one-record-at-a-time labeling tool (AI declined to display records in chat). Suite 403.

### 9o. M6 final results and final checks (2026-11-27)
- 30 labels (26 model-handled, 4 flagged; 1 ambiguous). Human `requires_human` yes: 11.
- **`requires_human` does not discriminate:** final 30/30 and 400/400 escalated; model alone 26/26 and 333/333. Recall 11/11 equals always-escalate (Wilson lower 95% 0.74, post hoc). Rules+flags without model: recall 7/11, 16/30 escalated.
- Category 10/26 (0.38, CI 0.23-0.58) = majority baseline 10/26; macro-F1 0.33 vs 0.09 (post hoc). Urgency exact 21/26 vs 15/26 always-medium (post hoc).
- Summary faithfulness: not done (sheet created locally, 0 of 10 rated).
- Checks: 403 tests pass; freeze v1 verifies; rescoring reproduces the metrics (only the faithfulness field changed from "not done" to "0 of 10" once the sheet existed); live uncached synthetic record processed end to end; SCOPE and Part A unchanged; no data/secret files visible to git. Scan of 98 commit-visible files: 0 record hashes, 0 Complaint IDs; 3 exact 8-word overlaps with the eligible narratives, all generic phrases in invented test text (4 narratives); shorter copying would not be detected.

### 9p. Fresh-clone test of `a1ab783` (2026-11-27)
`git clone` from GitHub, new Python 3.12 venv from `requirements.txt`: install ok; without data 400 passed, 3 skipped; `reproduce_slice` PASS (manifest hash); with `creditcard.csv` 403 passed; `final_test --split val` verified the frozen config and left `outputs/m2_dryrun_val.json` unchanged (identical). Zip and CSV were copied or read from the local machine, not re-downloaded. Not run: Ollama model runs, other Part A scripts, the test split; same macOS machine. Temporary clone deleted.

### 9q. Summary faithfulness (2026-11-27/28)
The author rated all 10 sampled summaries locally: faithful 1, minor omission 8, unsupported 1 (supersedes "not done" in 9o and the >=20 samples design note in section 5). 95% Wilson for unsupported about 0.02-0.40 (post hoc). Fuller rating meanings were written by AI after the other scores were seen; one rater, not blind to aggregate results. One typo in the rating sheet was corrected by the author. AI did not read the summaries or complaints. Labels unchanged; no prompt or rule change.

### 9r. Presentation and dashboard (2026-11-28)
Post-milestone questions. **What could invalidate this?** The dashboard's fraud page uses validation rows, which informed the choice of Rule B, so it looks better than new data would; "what moved the estimate" explains the logistic score, not the cause of fraud, and most fields are disguised; demo complaints are invented and few; production durations and team size are estimates with no PayGuard input. **What would a sceptic say?** A screen can make a weak model look finished; the fraud-scenario list is general knowledge, not analysis; the README says little about method and relies on the technical notes; the code base is still large for a prototype.

### 9s. Fresh-clone test (2026-11-28)
Run on a fresh clone with the same code as the current commit (later changes were to documents only). New Python 3.12 venv: install ok; 409 passed, 5 skipped without data; sample rebuild PASS; 414 passed with `creditcard.csv`; app started the README way and listened on 127.0.0.1 only; no tracked file changed; repository reachable without login. Part A scripts and local model runs not repeated. Same machine; data files copied locally. Temporary clone deleted.
GitHub display check (signed out, dark theme): diagrams and images rendered, but forced white fill hid the dashed "next stage" boxes, zoom controls covered them, charts were too small to read, and one README sentence was unclear. The README is about four laptop screens there, **longer than the two screens intended**; the earlier local estimate was wrong. Display and wording fixes were made and checked in light and dark Mermaid themes. Later the README was cut by about 30% (2 A4 pages in a local render; estimated about 3 laptop screens on GitHub, still above the 2-screen aim). That cut had also dropped the fraud scoring service and fraud monitoring; both were restored, with a stage 1 funding request and a done-and-next table. Content was put ahead of the 2-screen aim.

## 10. Open questions for the user
- (M3, 2026-11-26) see the revised M3 proposal: first-download approval, which exports, who reads narratives (Claude vs sanitized only), commit labels or not, small-stratum rule, LLM-provider terms for sanitized text.
- Which LLM provider (Claude API, other hosted, local)? Is there an API key budget?
- Confirm memo topic (Part B)?

## 11. Cut list (intentional)
Hyperparameter search · ensembling · deep learning · second LLM-provider comparison · real streaming/feature store · UI · large label set (50–60 labels ⇒ wide CIs; stated in README).

---

## 12. Working protocol (summary; full rules in CLAUDE.md)
Proposal → user approval → execute → answer the two review questions → stop → next proposal.
This spec is a guide, not a script: deviations are allowed and must be logged in §9.

## 13. Milestone review log
Short record of the two post-milestone questions. M0-M2 full answers were given in chat. Under D-32, M3-M8 are recorded here; D-32 in the gates table means the delegated strategy replaced per-milestone proposals.

| Milestone | What could invalidate this result? | What would a skeptical reviewer say? |
|---|---|---|
| M0 | Pins from one macOS arm64 machine; pandas 3.x is new; Gemini reliability untested | Pins unfiltered (transitive); no fresh-clone proof yet (M8) |
| M1 | 4 FPs decide the 90%-precision threshold; recall tuned on same val data; only 55 val frauds; 2-day window; dedupe choice; drift in fraud rate | Threshold 0.999995 is knife-edge; baseline never tuned; CI ignores split choice; scores uncalibrated |
| M2b (test, single evaluation) | Test has 52 frauds (EUR 6,169 total); PR-AUC fell from validation (LR 0.837->0.700, XGB 0.846->0.757), so validation was optimistic; Rule B's validation advantage did not carry over (XGB c=5: A 2,855 vs B 2,897; c=1: A 1,075 vs B 1,815); cost CIs very wide; both models' missed-fraud EUR at Rule B c=5 identical (2,372), consistent with the same large frauds being missed (not verified); hypothetical costs | XGBoost not shown better than logistic (CI spans 0) and has worse precision at c=5; one fixed time split; test used for reporting only but design decisions (Rule B) were validation-informed; XGB over-predicts (ratio 1.34) | M2a (v3: Rules A and B) | Amount-band over-prediction >EUR 10 may be prevalence shift + noise, not amount-specific (bands hold 1-31 frauds); both rules rest on hypothetical c; | Rule B assumes one constant loss per missed fraud (train mean EUR 120) while fraud sizes are very skewed (val median EUR 8); depends entirely on the hypothetical c; low thresholds (c=1 -> p>0.0083) sit where calibration is weakest (XGB bin [0.001,0.01): predicted 0.25% vs observed 0.04%); rule choice was informed by validation results; original: Cost rule rests on amount-conditional calibration that was only checked in aggregate; fraud value is concentrated (val fraud median EUR 8, total EUR 8,396, ~all in 24 caught frauds), so costs are noise-dominated; prevalence shift train->val (0.165%->0.129%) biases p up; no test yet; hypothetical costs | PR-AUC gain is within noise; rule worse than simple top-k references (in-sample, so the gap is overstated); XGBoost costs MORE than logistic under the rule; OOF fold 4 has only 28 frauds; untuned XGBoost; p*Amount assumes full prevention |
| M3 | Redaction failed review and is not signed off; the visible-sensitive answers are unreliable; taxonomy never checked on real records; exclusions catch exact matches only | A single failed batch with one reviewer; the milestone closed by decision, not by passing |
| M4 | One labeler, 30 records, no consistency check; no `low` urgency used; labels made on redacted text under time pressure | Too small to rank anything; rare categories have 1-3 cases |
| M5 | Escalates 400/400 real records, cause not investigated; only one 3B model; speed measured one request at a time; flagged routing was designed for an external API | The pipeline is robust but its decisions are not useful; schema validity says nothing about correctness |
| M6 | N=30; bootstrap recall interval is degenerate; some baselines added after seeing scores; prompts tuned on AI-written cases by the same author; 8-word leak scan misses shorter copying | Category ties the majority baseline; 100% recall is just always-escalate; synthetic cases failed to predict real behaviour; faithfulness unmeasured |
| M7 | Server prices and review minutes are assumptions; capacity from a laptop; monitoring thresholds are untested; page count from one renderer | Much of the production design is proposal, not evidence; an agent-time saving has not been shown |
| M8 | Clean-copy test is not a fresh clone; macOS only; rehearsal not done | Reproducing real-data results needs the public archive, Ollama and local labels that are not committed |

**Reproducibility note:** `part_a/final_test.py` (written after the config freeze, hence not in the config's `code_sha256`; 109 lines) has SHA-256 `1fe5342d1ef6228ad2f1ee95085e88f8fb27328ea06dac5e53b74968b1a2af90`. It was dry-run on validation and executed once on test; it refuses to run on test again.

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
| M3 Part B slice & taxonomy | ☑ | ☑ | ☑ (closed without sign-off) | ☑ | ☑ |
| M4 Part B hand labeling | D-32 | D-32 | ☑ | ☑ | ☑ |
| M5 Part B pipeline | D-32 | D-32 | ☑ | ☑ | ☑ |
| M6 Part B evaluation & adversarial | D-32 | D-32 | ☑ | ☑ | ☑ |
| M7 Part C memo | D-32 | D-32 | ☑ | ☑ | ☑ |
| M8 Polish & rehearsal | D-32 | D-32 | ◐ | ☑ | ☑ |

### 14.2 Goals achieved? (maps to SCOPE §8 grading criteria)
**Judgment**
- [x] Every metric choice is justified in writing (A2)
- [x] Every cut is listed with a reason in the README (§11)
- [x] Limits and optimistic numbers are stated plainly (A7, B8)
- [ ] Decision log is complete and consistent with the code

**Evaluation rigor**
- [x] Part A: no leakage (time split, fit-on-train-only, leakage test passes)
- [x] Part A: variance/CI reported; test set used once
- [x] Part B: hand labels made before viewing model output
- [x] Part B: "correct" defined per field; `requires_human` recall reported
- [x] Part B: injection and sensitive-case tests run and reported
- [x] Part B: scale-measurement plan written

**Code quality**
- [x] Runs from a fresh clone + fresh venv (D1)
- [x] Small test suite passes
- [x] Seeds fixed; slice reproducible (hash matches)
- [x] No secrets or data committed
- [ ] Code is simple enough to explain line by line

**Communication**
- [x] README: setup, approach, results, what was cut and why
- [x] Memo ≤ 2 pages, concrete, diagram included
- [ ] AI_USAGE.md specific and truthful; authorship table final

**Results (least weighted)**
- [x] Part A: baseline vs stronger model compared with reasoning
- [x] Part B: scores reported honestly, including failures

### 14.3 Final submission checklist
- [ ] All SCOPE §7 deliverables present (code, README, memo, AI_USAGE; optional recording)
- [x] SCOPE.md unchanged since creation (unless user requested edits)
- [ ] SCOPE §3–§5 "Required" items each verified against this spec (§2 all ☑)
- [x] Repo pushed to GitHub; link works for reviewers (public, checked without login)
- [ ] Live-session rehearsal done: walkthrough of every file + 3 live modifications (e.g. swap metric, change threshold, add a category)
- [ ] Can explain every line and every decision without notes
