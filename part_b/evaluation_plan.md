# Part B evaluation plan (frozen before any model output exists)

## Sets
| Set | Size | Use |
|---|---|---|
| Synthetic development cases | about 20, invented (AI-written, with expected labels) | The ONLY set used to compare prompt versions. Scores on it are not accuracy claims: the author of the prompts and of the cases is the same. |
| Pilot | 20 real (unflagged) | Smoke run of the pipeline on real text: operational counts only. Not labeled, not read. |
| Evaluation | the first N items of the frozen labeling order, N >= 30 (up to 60), labeled by the author before seeing any model output; N is final before scoring | Final measurement, for ONE final prompt. If the prompt changes after these scores are seen, both results are reported and the later one is marked tuned on the evaluation set. |
| Main sample | 400 | Operational measures only (routing, failures, latency, tokens, output distribution). No accuracy claims: it is unlabeled. |

Model: local only (no complaint text goes to an external provider: sanitizer sign-off was not achieved). Input to the model is sanitized text.
Flagged records get no model call: `requires_human = true`, routed to a person (D-23, kept although the model is local). They stay in every set.

## What "correct" means, per field
| Field | Correct / measure | Scored on |
|---|---|---|
| category | exact match with the human label. Accuracy and macro-F1 (categories present in the human labels), 95% bootstrap intervals (1,000 resamples, seed 42), confusion matrix, per-category counts. Compared with always predicting the most common human category. | model-handled evaluation records (flagged and fallback records counted separately) |
| urgency | exact match and within one level; count of human `high` predicted `low` | same |
| requires_human (**primary: recall**) | final system output against the human label: recall, precision, escalation rate, confusion counts, bootstrap interval for recall | (a) all evaluation records end to end; (b) model-handled records only; (c) model alone, before safety rules |
| flag workload | records escalated only because they were flagged, among those labeled `n` | all evaluation records |
| summary | faithful / minor omission / unsupported or wrong claim, against the sanitized text | up to 10 model-handled evaluation records (random, seed 42), rated by the author AFTER labeling; if not rated it is reported as not done |
| confidence_note | not scored |  |

Baselines for requires_human: **always escalate** (recall 100% by construction) and **safety rules plus flags without a model**.
Fallback records count as category errors unless the human label is `other`, and are reported separately.

## Adversarial and safety tests
Synthetic, written separately from the sample, never mixed into accuracy figures: prompt injection in complaint text, invented categories, malformed output, legal threats, fraud allegations, self-harm language. Pass/fail per case.
Safety keyword rules are written without looking at evaluation records.

## Dropped from the earlier plan (time limit; stated as limitations)
Pilot check of the taxonomy, labeled pilot development set, relabeling consistency check, 20-record extension, visible-sensitive vs flag table, 20-summary rating (reduced to 10).

## Limits to state with every result
- About 30-60 records: intervals are wide; rare categories may have 0-3 records and their per-category scores mean little.
- One labeler; no consistency check. The taxonomy was written without data and never checked on real records.
- One month of one public, publication-biased US dataset; not PayGuard's customers or market.
- Human labels and the model both see sanitized text only.
- A small local model; results say nothing about larger or hosted models.

## Not claimed
Production accuracy, safety to auto-close complaints, anonymity of sanitized text, or generalization to PayGuard data.
