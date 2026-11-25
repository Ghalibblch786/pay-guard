# AI_USAGE.md

Disclosure of AI assistance for the PayGuard take-home, as required by the assignment.
Maintained continuously by Claude Code and reviewed by the author before submission.

## Tools
| Tool | Version/model | Used for |
|---|---|---|
| Claude Code (CLI/VS Code extension) | Claude Sonnet 5.5 (`claude-sonnet-5-5`) | Reading the assignment brief, planning, drafting project docs, and (as work proceeds) code, tests, and write-ups |

Other tools: none so far. (Add any additional assistant, e.g. completion plugins or other chat
models, as soon as it is used.)

## Principles followed
- Author makes the decisions (metrics, split, taxonomy, rollout stance); AI drafts and implements in small steps.
- Every line is read, run and understood by the author before it stays in the repo.
- AI output is verified (run, tested, compared to expectations), not trusted blindly.
- Where the author overrode or corrected the AI, it is noted below.

## Authorship estimate by file (update as files appear)
Share = rough fraction of the file's content first drafted by AI. "Reviewed" = author has read
and can explain it.

| File / area | AI-drafted share | Author work | Reviewed |
|---|---|---|---|
| SCOPE.md | ~100% (paraphrase of wiki brief) | Provided the brief link; will verify wording against the wiki | ☐ |
| SPECS.md | ~90% | Requested structure; decisions to be confirmed | ☐ |
| CLAUDE.md | ~90% | Requested; rules to be confirmed | ☐ |
| AI_USAGE.md | ~90% | Reviews entries for accuracy | ☐ |
| Part A code (`part_a/*.py`, `tests/`) | ~95% AI-written; author specified design constraints, reviewed results | Specified split, leakage, duplicate, calibration and rule requirements; made all decisions | ☐ |
| Part B code | — | — | — |
| README.md | — | — | — |
| memo.md | — | — | — |

Overall estimate of repository content produced by AI: **to be computed at submission** from the table above.

## Session log
### 2026-11-25 — Session 1 (planning)
**AI did**
- Fetched and summarised the assignment wiki page (via a subagent, so SCOPE.md is a paraphrase, not verbatim).
- Wrote an approach guide covering mindset, per-part focus areas, and a milestone plan.
- Created `SCOPE.md`, `SPECS.md`, `CLAUDE.md`, `AI_USAGE.md` in an empty repo directory. No code yet.

**Author did / decided**
- Chose the workflow: frozen scope file + living spec + auto-updated disclosure log.
- Pending decisions: LLM provider (D-02), memo topic confirmation (D-01), gradient-boosting library (D-03).

**Corrections / overrides:** none yet.

**To verify:** compare SCOPE.md against the original wiki page and fix any paraphrase errors (requires an explicit request to edit SCOPE.md).

**Update (same session):** author specified the working protocol (propose → approve → execute → two review questions).
AI added it to `CLAUDE.md`, and added the review log and progress checklist to `SPECS.md` (§12–§14). No code yet.

### 2026-11-25 — Session 1, M0 (setup)
**AI did:** created folder skeleton, `pyproject.toml`, `.gitignore`, `.env.example`, `config.py`
(SEED, paths), `tests/test_smoke.py`; created `.venv` (Python 3.12.16, uv) and installed deps;
generated pinned `requirements.txt` via `uv pip freeze`; ran the smoke tests (1 pass, 1 fail:
LightGBM cannot load `libomp.dylib`); updated SPECS decision log.
**Author decided:** Gemini free tier for Part B, LightGBM, memo on Part B (deferred to the brief), Python 3.12 + uv.
**Corrections / overrides:** none.

**Update:** author switched the stronger model from LightGBM to XGBoost. AI swapped the dependency in `pyproject.toml`,
smoke test, `requirements.txt`, SPECS and CLAUDE.md. XGBoost fails the same way (missing `libomp`); awaiting author's go-ahead for `brew install libomp`.

**M0 closed:** with author approval AI ran `brew install libomp`, reran smoke tests (2 passed), verified XGBoost
train+predict on random toy data, and created `README.md` (setup + macOS note). Author approved each step.

### 2026-11-25 — Session 1, M1 (Part A baseline)
**AI did:** wrote `part_a/data.py` (load, dedupe, time-value split), `part_a/evaluate.py` (PR-AUC + bootstrap CI,
threshold for 90% precision, confusion matrix, calibration bins), `part_a/train.py` (scaler + class-weighted LogReg
pipeline), `tests/test_split.py`; ran duplicate inspection and baseline on validation; wrote README Part A section;
fixed a degenerate synthetic test and added an empty-split guard. Initial estimate of ~75 val frauds was wrong (actual 55).
**Author decided/refined:** scale all 30 features, inspect duplicates before dropping, tie-safe split, threshold on val
at >=90% precision, document calibration; downloaded the dataset manually.
**Corrections:** none from author; AI corrected its own fraud-count estimate.

### 2026-11-25 — Session 1, M2 Stage 2a (validation only)
**AI did:** wrote `part_a/stage2a.py` (XGBoost with fixed params, expanding-window OOF Platt calibration, cost model,
paired bootstrap, seed robustness, provisional freeze: `part_a/frozen/` config, hash, models), `tests/test_m2.py`, added
`split_cuts` / `time_chunks` to `data.py`; ran it on train+validation; ran a read-only validation diagnostic of the cost rule.
Test set not accessed. **Author decided:** base c=5 EUR hypothetical (1 and 25 sensitivity), primary seed 42 with seeds
43/44 for robustness only, no validation-fitted fallback calibrator, stop before Stage 2b. **Overrides:** none yet.

**Update (M2 Stage 2a, rule change):** author reviewed validation results and chose Option B (amount-agnostic rule).
AI archived the v1 config as superseded, replaced the rule in `stage2a.py`, regenerated the frozen config, verified that all
other components (data, features, split, models and their hashes, seeds, calibration, costs) are identical to v1, and
documented the deviation in SPECS (D-09) and README. Test set not accessed.

**Update (config v3):** author asked whether Rule A could be retained and chose option 1 (retain both rules, roles pre-declared).
AI answered that Rule B is not theoretically preferable, ran a validation-only calibration-by-Amount-band diagnostic
(saved as `part_a/diag_amount_bands.py`), archived v2, regenerated the frozen config as v3, verified hashes of v1/v2/v3,
and found and corrected one inaccurate sentence in its own draft (v1 file was written by the run that first produced
validation results, not before). README and SPECS updated. Test set not accessed.

### 2026-11-26 — Session 1, M2 Stage 2b (single test evaluation)
**AI did:** wrote `part_a/final_test.py` (verifies config/model/dataset/code hashes, loads frozen models and Platt coefficients,
evaluates both models and both rules, bootstrap CIs, refuses a second test run); dry-ran it on validation to confirm it reproduces
Stage 2a numbers exactly; then ran it once on test (`outputs/m2_test_results.json`, sha256 f54b10a5...b985). Note: `final_test.py`
was added after the freeze, so it is not in the config's code hashes. **Author:** authorized Stage 2b after reviewing config v3.
Nothing was tuned, recalibrated or changed after seeing test results.

### 2026-11-26 — Session 1, M2 closure
**AI did:** rewrote the README Part A section (results exactly as reported, CIs, Rule A/B roles, Rule B's non-generalization,
cost-model assumptions vs. actual business savings, PR-AUC vs cost explanation, A6 real-time note, A7 limitations, frozen-artifact
hashes); updated SPECS statuses and checklists. No code, model, threshold, calibration or test-set changes; frozen files re-hashed
and unchanged. **Author:** directed the content requirements and approved closure scope.
**README Part A authorship estimate:** ~90% AI-drafted text; numbers come from the saved result files; author reviews before submission.

<!-- Claude: append new session entries below this line, newest last. Keep entries specific. -->




