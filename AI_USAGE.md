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

### 2026-11-26 — Session 1, M3 proposal prep (no implementation)
**AI did:** recorded `final_test.py` SHA-256 in SPECS and README (no rerun); researched Part B data availability: a research
subagent read CFPB pages (its report is unverified model output), and AI directly read the first ~300 KB of the official
`complaints.csv.zip` (scratchpad only) and confirmed the current CSV has no narrative column; searched Hugging Face for archives
with narratives. Drafted the M3 proposal. No Part B code, data download or LLM call yet. **Author:** will decide D-11.

**Update (M3 revision):** author redirected Part B to the official CFPB FOIA Narratives Archive and set data-protection rules.
AI (via a research subagent, then re-verified directly) read the archive page, confirmed 21 export links and read file sizes from HTTP
HEAD requests only; read exact current CFPB product names from the already-held 300 KB live-metadata sample (no narratives).
Nothing from the archive was downloaded. Updated SPECS (D-11 to D-13, M3 block) and CLAUDE.md (data-protection rules).

**Update (M3 Stage 3a):** with author approval AI downloaded ONLY `CCDB_Export_21_August_2026.zip` (gitignored in `data/raw/`),
verified zip integrity, wrote `part_b/inspect_archive.py` (aggregate-only, run with `python -I`; never prints narrative text) and ran it;
cross-checked emptiness with a second method. Finding: narrative column exists but is empty (1 of 667,140). No narrative text was read
or displayed; no labeling, pilot, sampling, LLM call, or Part A change. Results in `outputs/m3a_archive_inspection.json` (aggregates, gitignored).

**Update (M3 Stage 3b):** AI wrote `part_b/probe_exports.py` (HTTP Range + central directory + prefix inflate; aggregate-only, `python -I`),
validated it against the already-downloaded August file, then probed 3 MB prefixes of four official exports (~14 MB transferred in memory;
nothing but aggregate JSON written: `outputs/m3b_method_validation.json`, `outputs/m3b_probe_results.json`). A first run returned HTTP 403 because
of a custom User-Agent header; AI removed the header and used the library default. A research subagent read official CFPB pages about the
Aug 14 date (report treated as unverified model output). No narrative text was displayed; no labeling, sampling, LLM calls, or Part A changes.

**Update (M3 Stage 3c):** AI extended `part_b/probe_exports.py` (integrity fields, column check, fill-by-week), re-validated it, and probed 3 MB
prefixes of the six 2026 exports (~18 MB transferred in memory; outputs `outputs/m3b_method_validation_rerun.json`, `outputs/m3c_probe_results_2026.json`,
gitignored aggregates). No complete export, no narrative text read or displayed, no sampling/labeling/LLM calls, no Part A changes. SPECS section 9c holds the comparison.

**Update (M3 Stage 3d):** with author approval AI downloaded the complete June 2026 export (only that file; `data/raw/`, gitignored), verified size, SHA-256 and a full CRC test,
wrote `part_b/inspect_full.py` (aggregate-only, in-memory, `python -I`) and ran it (`outputs/m3d_full_inspection_jun2026.json`). No narrative text was printed, saved or sent
anywhere; no sampling, labeling, pilot, LLM calls, Part A changes, or git commits. Findings in SPECS 9d; README got a short provenance note.

**Update (M3 Stage 3e proposal):** AI wrote `part_b/inspect_dedup_length.py` (aggregate-only, in memory, `python -I`; outputs counts only, no text, hashes or IDs saved)
and ran it on the June 2026 export to quantify duplicate and length impacts for the proposal (`outputs/m3e_dedup_length_aggregates.json`). Recorded D-16 as accepted and drafted
D-17 to D-21 in SPECS. Proposal only: no sanitizer, sample, pilot, labeling, LLM call, new download, Part A change, or commit.

**Update (M3 Stage 3e decisions):** author decided D-17 (SHA-256 dedup), D-18 (30-1,500 words), spaCy local model approval, sensitive-content routing without
external calls but kept in evaluation, balanced pilot, labeling sanitized text, local review of 30 sanitized narratives, and ignoring `outputs/m3*.json`. AI switched
`part_b/inspect_dedup_length.py` and `part_b/inspect_full.py` from SHA-1 to SHA-256 and re-ran both (aggregates byte-identical), added the `.gitignore` rule, and updated
SPECS (D-17 to D-25, new M3 block) and CLAUDE.md. No sanitizer, sample, narrative reading, LLM call, install, or commit.

**Update (M3 Step 1):** author approved the 8-step plan and refinements (D-26). AI installed spaCy 3.8.18 and `en_core_web_sm` 3.8.0 (hash recorded), wrote `part_b/sanitizer.py`,
`part_b/sensitive_flags.py`, `tests/test_sanitizer.py` and `tests/test_sensitive_flags.py` (synthetic text only), found and fixed gaps by adversarial synthetic probing, refactored one
hard-to-explain helper, updated `pyproject.toml`/`requirements.txt`, SPECS (D-22, D-26, section 9f), CLAUDE.md and README. No real narrative was processed, read or displayed; no sample,
LLM call or commit. AI-drafted share of these files is ~100%; the author must be able to explain every regex before the live session.

<!-- Claude: append new session entries below this line, newest last. Keep entries specific. -->




