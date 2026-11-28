# AI_USAGE.md

Disclosure of AI assistance for the PayGuard take-home, as required by the assignment.
Maintained continuously by Claude Code and reviewed by the author before submission.

## Tools
| Tool | Version/model | Used for |
|---|---|---|
| Claude Code (CLI/VS Code extension) | Claude Sonnet 5.5 (`claude-sonnet-5-5`) | Reading the assignment brief, planning, drafting project docs, and (as work proceeds) code, tests, and write-ups |

Claude Code also used web search and a web-fetch subagent (to read LLM providers' terms; no project data sent). Not a coding assistant, but part of the product: the local model `llama3.2:3b` (via Ollama) produces the Part B triage outputs. On 2026-11-27 the author confirmed that they had used no other AI tool. On 2026-11-28 the author also used Claude in a separate chat to help write task instructions.

## How the work was actually done
- Through M2 and most of M3, work went in proposal-and-approval steps. On 2026-11-27 the author moved to a faster strategy (SPECS D-32): AI took routine implementation decisions, including model, prompt-selection rule, reduced evaluation plan and the memo's recommendation.
- The author set the data-protection rules, chose to keep complaint text local, recorded the flag-audit and redaction-review verdicts, and made the hand labels. AI did not label or suggest labels.
- AI output was checked by running tests and scripts. **The author has not yet reviewed or rehearsed much of the code and text, in particular the Part B pipeline, evaluation code, README Part B and the memo** (see the Reviewed column).
- Author overrides and AI errors are noted in the session log.

## Authorship estimate by file (update as files appear)
Share = rough fraction of the file's content first drafted by AI. "Reviewed" = author has read
and can explain it.

| File / area | AI-drafted share | Author work | Reviewed |
|---|---|---|---|
| docs/process/SCOPE.md | ~100% (paraphrase of wiki brief) | Provided the brief link; will verify wording against the wiki | ☐ |
| docs/process/SPECS.md | ~90% | Requested structure; decisions to be confirmed | ☐ |
| CLAUDE.md | ~90% | Requested; rules to be confirmed | ☐ |
| AI_USAGE.md | ~90% | Reviews entries for accuracy | ☐ |
| Part A code (`part_a/*.py`, `tests/`) | ~95% AI-written; author specified design constraints, reviewed results | Specified split, leakage, duplicate, calibration and rule requirements; made all decisions | ☐ |
| Part B code (`part_b/`, Part B tests; includes the D-29 exclusion code) | ~95% AI-written; author set safeguards and requirements | Set data-protection rules, approved designs and fixes, ran the flag-audit summary and recorded all 29 audit verdicts | ☐ |
| README.md | ~100% AI-drafted (rewritten 2026-11-28) | Approved the plan; to be reviewed | ☐ |
| docs/technical_notes.md | ~100% AI-drafted; its first-person review statements describe the author's own work | Statements about the author's reviews were confirmed on 2026-11-27 in their earlier README form | ☐ |
| app/ (dashboard), .streamlit/, tests/test_app.py | ~100% AI-written, including the invented demo complaints | Approved the plan | ☐ |
| memo.md | ~100% AI-drafted, including the recommendation | Set scope and constraints; hand labels behind its Part B results; agreed with the recommendation (2026-11-27) | ☐ |

**Overall (rough judgment, not measured from line history):** about 95% of the code and tests, and about 90% or more of the documentation text, was first drafted by AI. The author's direct contributions are requirements, safeguards, decisions, review verdicts and hand labels.

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

**Update (M3 Step 2):** author approved the aggregate-only run with safeguards. AI wrote `part_b/run_sanitizer_aggregate.py` (reproduces the 7,376 eligible narratives, builds the protected list from the Company column only,
asserts no narrative-like strings in the output) and `part_b/diagnose_step2.py` (counts-only attribution), ran both locally in memory (no text, IDs or hashes printed or saved; no network or LLM), and recorded results in SPECS
section 9g. A first attempt to wait for the diagnostic used a wrapper whose completion notice fired early; AI checked the process and waited on the real PID. AI did NOT change the sanitizer after seeing results: fixes are proposed (D-27).
No sample, Part A change, or commit.

**Update (M3 D-27 fixes, Step 2 re-run, flag audit):** author approved the four fixes and the optional audit. AI edited `part_b/sanitizer.py` (removed the email rule and the hard-coded protected list; added the
critical-term guard, exact brand allowlist, two-pass NER with skip statistics), wrote 13 new tests (deterministic stub NER; suite 182 passing), extended and re-ran `part_b/run_sanitizer_aggregate.py` (counts only; before-fix copy kept),
wrote `part_b/flag_audit.py`, `part_b/flag_audit_summary.py` and `tests/test_flag_audit.py`, and generated the local audit files (never displayed). A first counting choice (skips counted on every pass) double counted; AI changed it to
first pass only. No narrative text, IDs or hashes printed, saved in tracked files or transmitted; no LLM or external service; no sample; no commit.

**Update (audit hold):** author asked for no changes and no Step 3 until the audit is complete. AI verified (file size, timestamp, permissions, gitignore, 29 blank verdict rows; no narrative text read) that the audit files are unchanged,
confirmed the local recording instructions, and drafted the exclusion-hash proposal (SPECS D-29, not implemented). `part_a/final_test.py` was attached by the author as context and was not modified. No code, data or Part A change.

**Update (D-29 approval):** author approved D-29 Variant A with safeguards (SHA-256 only, local gitignored storage, exact D-17 normalization, fail-closed, aggregate-only reporting, synthetic tests) and told AI NOT to implement it yet.
AI only updated SPECS and this log. No code, data, audit-file, sampling or Part A change; no narrative text, IDs or hashes touched.

**Update (flag audit results):** the author reviewed the 20 local audit items, recorded all 29 verdicts and ran `part_b/flag_audit_summary.py` themselves, then pasted the counts: 29 correct, 0 wrong, 0 unclear. The verdicts are entirely the author's; AI saw only the aggregate output
and never read the items file. AI read the `part_b/flag_audit.py` source to confirm the verdict question, recorded the counts and their limits in SPECS 9i (not a precision estimate, no recall information, single non-blind reviewer) and updated the current-milestone line. No code, data, audit-file, sampling or Part A change; D-29 not implemented; Step 3 not started.

**Update (audit documentation):** the author sent the same aggregate counts again and asked for documentation only. AI added an audit paragraph with its limitations to README (first-person wording drafted by AI, since the author did the review), corrected the stale README status line that said the sanitizer was not built, and added "tiny, flagged-only" to SPECS 9i. No narratives, IDs or hashes accessed; no code, Part A or sampling change; no commit.

**Update (D-29 steps 1-3):** the author approved the implementation, including local script access to the export (narratives, Complaint IDs) and the audit items file. AI wrote `part_b/exclusions.py`, `part_b/export_audit_hashes.py` and `tests/test_exclusions.py` (23 synthetic tests; suite 205 passed), refactored `part_b/flag_audit.py` to move report building into `build_audit()`,
ran the export once (PASS: byte-identical; 20 hashes saved; eligible 7,376 -> 7,356), confirmed both audit files unchanged, and updated SPECS (9j) and README. No narratives, IDs or record hashes were displayed or transmitted; no LLM or external service; no Part A change; no sample; no commit. The author has not yet reviewed this code.

**Update (overwrite safeguard):** the author accepted the D-29 implementation and test results, subject to a safeguard they required: `flag_audit.py` must not overwrite audit files (AI had recommended it as outside the earlier approval). AI changed `flag_audit.main()`, wrote `tests/test_flag_audit_no_overwrite.py` (9 synthetic tests; suite 214 passed) and updated SPECS and this log.
The completed audit files, exclusion file and Part A were not accessed or modified; no Step 3; no commit. The author has not yet reviewed this change.

**Update (Step 3 proposal):** the author accepted the audit-file overwrite safeguard (214 tests passing) and asked for a Step 3 proposal only. AI read SPECS and listed function names in `part_b/sanitizer.py`, drafted the proposal in chat (not approved), and updated the SPECS status and this log. Nothing implemented or run; audit files, exclusion hashes, data and Part A not accessed; no commit.

**Update (Step 3 tooling, synthetic only):** the author approved the Step 3 design with two clarifications (rename/define the missed-sensitive question as visible remaining content, not flagger recall; define `indirect_concern` with examples and a sign-off rule) and authorized implementation with synthetic data only. AI wrote `part_b/eligibility.py`, `review_batches.py`, `make_review_batch.py`, `summarize_review.py`, `review_guide.md` (definitions, invented examples and the strict y/u-fails rule are AI-drafted and await the author's review), `review_batches.json`, added `load_by_source` to `exclusions.py`, wrote `tests/test_review_batches.py` (73 tests; suite 287 passed), ran a synthetic end-to-end check and a deliberate-fault check in the scratchpad, and updated SPECS and README.
One AI test expectation was wrong on first run (corrected; code unchanged by it); the fault check exposed one untested safeguard (test added). No real archive, exclusion hashes or audit files accessed; no real batch; no manual review; no LLM or external service; Part A unchanged; no commit. The author has not yet reviewed this code.

**Update (proposal to finish M3):** the author asked for a plan to complete the remaining M3 steps with as few approvals as possible. AI checked the SPECS checklist (3e-2 was already done) and drafted the proposal in chat; not approved. Only SPECS status and this log changed; no data accessed; nothing run; no commit.

**Update (M3 Run A):** the author approved the completion plan and accepted the review guide and Step 3 tooling, asking to be consulted only when necessary. AI added the card/account digit rule and tests to `part_b/sanitizer.py`, wrote `make_slice.py`, `freeze_plan.py`, `tests/test_slice_and_freeze.py`, added the post-decision guard and Complaint IDs, and drafted `taxonomy.json`, `labeling_guide.md` and `evaluation_plan.md` without reading any narrative (AI-drafted; the author has not yet reviewed them).
AI's first version of the digit rule had a leak bug, found by its deliberate-fault check and fixed (8 further wording misses fixed after synthetic probing); a data run using the faulty code was stopped. On real data AI ran, with approval and counts-only output: the Step 2 re-run, a count of the new rule's matches (none: its earlier recommendation had no measured basis) and generation of review batch 1. Suite 347 passed. No narrative text, Complaint IDs or record hashes displayed or read by AI; completed audit files not accessed; no LLM pipeline or external complaint transmission; Part A unchanged; no commit.

**Update (2026-11-27, revised plan, M3 closure, M5/M6 build):** the author asked to finish within 2-3 hours, stop the sanitizer review, keep complaint text local and let AI take routine decisions. Earlier that day the author did the 30-record review and made every verdict edit; AI ran previews and format checks on the verdict sheet (showing counts, positions and recognized codes), then, under the revised instructions, recorded the batch unchanged (failed) and the no-sign-off decision.
AI drew the samples, froze the plan and made the label pack; installed Ollama and downloaded `llama3.2:3b`; wrote the whole M5/M6 code, the synthetic development and attack cases with their expected answers, prompts v1-v3, the safety rules, tests, `reproduce_slice.py`, the README Part B section and cut list (including first-person text about the author's reviews, to be confirmed), and the `memo.md` draft; changed the dependency list. AI made the routine design choices (model, prompt selection rule, context size, reduced evaluation plan).
AI errors this session: reported run speed from progress lines without checking success (45 of 60 had failed). The author considered Gemini and Groq and chose to stay local after AI's advice; AI used web search and a web-fetch subagent to read the providers' terms (no project data sent). No real complaint text, IDs or record hashes were displayed or sent externally; real narratives went only to the local model. Part A unchanged; no commit. The author has not reviewed the new code; hand labels are the author's own and are pending.

**Update (local labeling tool):** the author asked AI to show the records one by one in chat and record the answers. AI declined to display them (that would send complaint text to an external AI service and expose the evaluation records to the system's developer) and wrote `part_b/label_cli.py` with synthetic tests, to be run by the author in their own terminal. AI did not run it on real records; it suggests no labels.

**Update (full runs and clean-copy check):** AI added server-failure safeguards, ran the evaluation (60) and main (400) records on the local model, printing operational totals only, filled the operations and cost sections of README and memo (server prices are a stated assumption), and ran a clean-copy install, test and sample-rebuild check. AI did not read model outputs on real records or the author's labels (it counted how many rows were labeled).

**Update (2026-11-27, disclosure correction):** AI found and replaced inaccurate statements in this file (that every line had been read and understood by the author, that the author made all decisions, and that no other tools were used).

**Update (2026-11-27, scoring and final documents):** the author hand-labeled 30 evaluation records with the local tool and made every label. AI ran scoring (aggregates only), wrote `part_b/posthoc_checks.py` (checks added after seeing scores, marked as such), filled the evaluation results in README and `memo.md`, changed the memo recommendation to funding offline evaluation only, shortened the memo to 2 pages (page count from a local Chrome render), created the local summary-rating sheet without reading it (not rated), updated SPECS (statuses, D-34, review log) and this log. AI corrected two of its own draft errors before handover (that the model saw flagged records; that there were 2 rather than 3 downgrade-injection cases).
Final checks by AI: 403 tests, freeze verification, rescoring, one live synthetic record, and a local counts-only scan of commit-visible files for record hashes, Complaint IDs and 8-word narrative overlaps (the script read narratives and IDs in memory; AI saw only counts, file names, line numbers and its own synthetic lines). No prompt or rule changed after scoring; Part A and SCOPE unchanged; no commit. The author has not yet reviewed these changes.

**Update (2026-11-27, review against the assignment page):** at the author's request, AI read the assignment wiki page through a web-fetch subagent (only the link was sent) and compared the repository with it using read-only checks, including counts (no text shown) of how varied the 400-run summaries and confidence notes are. Found: no `creditcard.csv` download or Part A run instructions, no recommended operating threshold, current work not pushed. AI had earlier marked A2, A5 and D2 done; corrected in SPECS. No code, README or memo change.

**Update (2026-11-27, three approved README and memo fixes):** the author approved AI's three fixes and suggested operating point. AI wrote the Part A download and run instructions (from reading the scripts; not re-run), the operating-point and error-cost text (marked as chosen after test results), the README results summary and key-file list, and one memo sentence explaining the choice of Part B (reason taken from SPECS D-01). The author approved the threshold; the analysis and wording are AI's. Checks: data file hash, 2-page memo render, links, 403 tests. No Part A code or results changed or rerun.

**Update (2026-11-27, confirmations and commit):** the author confirmed that the README's first-person review statements are accurate, agreed with the memo's recommendation, stated that no other AI tool was used, and approved AI committing, pushing to GitHub and testing a fresh clone, including the Part A validation-only check in that temporary copy. These confirmations do not mean the author has reviewed all the code.

**Note on commit `5a9ee57` (2026-11-27 21:46):** this earlier commit of the Part B work and memo, already on GitHub, carries the author's Git identity and a Claude co-author line. It was not made by AI in the conversation that wrote this note. Statements in earlier entries that nothing was committed refer to the time they were written; AI did not re-check the Git log before saying so after the three fixes. The commit that adds this note contains the three fixes and the confirmations.

**Update (2026-11-27, push and fresh-clone test):** AI re-ran the leak scan and tests, committed the four documents as `a1ab783`, pushed, and tested a fresh clone (results in SPECS 9p), including the author-approved Part A validation-only check, which reproduced the saved file exactly. The test split was not used. These record-keeping edits were made after that commit.

**Update (2026-11-27/28, brief comparison and summary ratings):** at the author's request AI compared the project with the assignment text the author pasted (no files changed then), and helped plan the optional screen recording. The author rated all 10 summaries in their own terminal and fixed one typo; AI wrote the instructions, the fuller rating meanings and invented examples, counted totals only, did not read the summaries or complaint text, and added the results and their limits to README, memo and SPECS.

**Update (2026-11-28, presentation and dashboard):** AI proposed a plan and the author approved it as recommended. AI then: deleted six unused or one-off scripts (including the Part A Amount-band diagnostic and one flag-audit summary test); moved SPECS and SCOPE to `docs/process/` (contents unchanged by the move) and updated the paths in CLAUDE.md; added Streamlit; wrote the dashboard (`app/`), its tests, six invented demo complaints and their saved local-model answers; wrote the chart script; rewrote the README; wrote `docs/technical_notes.md`, including the comparison with real payment data and the fraud-scenario list (general domain knowledge, not found in this data); and changed one memo link. Production durations and team size in the README are AI's planning estimates. No model was trained, no test-set transaction was scored, and no real complaint text was used in the new app (the privacy search read it locally and printed counts only). Checks: 414 tests; a clean copy with a new environment (409 passed, 5 skipped without the fraud data; app started and listened on this computer only). The author has not yet reviewed the new code or text.

**Update (2026-11-28, commit):** the author asked AI to commit and push. AI had first asked them to try the app and to check the planning estimates, fraud scenarios, README wording and this disclosure, saying to reply this way if accurate. The author did not answer those items one by one, so this log does not record them as separately confirmed or the new work as reviewed.

**Update (2026-11-28, clone test and GitHub display check):** AI committed and pushed the work, tested a fresh clone and viewed the public README signed out (SPECS 9s). AI then fixed the diagram colours and labels, chart sizes and one unclear sentence, and corrected its earlier claim that the README fitted about two screens.

**Update (2026-11-28, wording):** at the author's request AI edited wording in this log and in SPECS, then replaced the latest commit on GitHub with a single new one (history rewrite). The AI tool disclosure stays.

**Update (2026-11-28, README trim):** at the author's request AI cut the README from about 1,140 to 840 words: merged the two diagrams, removed the status table and some detail, and made the charts smaller. AI said all removed detail remained in the technical notes or memo; **that was wrong** for the fraud scoring service and fraud monitoring. Not committed at the time of writing.

**Update (2026-11-28, funding request and repair):** at the author's request AI added a stage 1 funding request to the README (what PayGuard provides, pass conditions, team), restored a done-and-next table and added fraud production and monitoring steps. The engineer-weeks figure is arithmetic on AI's own estimates; the fraud monitoring frequencies and the fall-back to existing controls are AI's design proposals. Shown to the author before committing; the author then asked AI to commit and push. This does not record the new proposals as separately confirmed.

**Update (2026-11-28, chart size):** at the author's request AI enlarged both README charts, redrew the complaint chart narrower from the same saved results and shortened one chart title. No figure changed. Shown to the author before committing.

<!-- Claude: append new session entries below this line, newest last. Keep entries specific. -->

**Update (2026-11-27, project overview):** the author asked for a plain-language overview of the project. AI read the project documents and some of the code, listed files and docstrings, ran the test suite (403 passed) and explained the project in chat with text diagrams. No narrative text or labels read. Only this entry changed; no code, results or SPECS change; no commit. The author made no new decisions.





**Update (2026-11-27, commit and push):** at the author's request ("push git"), AI checked the pending files (secret-pattern scan, review of hash-like and long-number matches in selected files, JSON key and long-string check, redaction-marker context, ignore rules), ran the test suite (403 passed), appended this entry, committed the pending work to `main` and pushed it to `origin`. These checks did not repeat the earlier local scan for record hashes, Complaint IDs and narrative overlaps. No project code was changed.
