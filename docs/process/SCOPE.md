# SCOPE.md — PayGuard Take-Home (FROZEN)

> **FROZEN FILE.** This is the fixed contract for the project. Claude must NOT edit,
> reformat, "fix", or append to this file unless the user explicitly asks for a change
> to SCOPE.md in that message. If something here conflicts with another file, this file wins.
> Source: Stixor wiki, "Take Home Assignment: PayGuard"
> (https://wiki.stixor.com/s/66440feb-4908-4a62-8a0b-b012c1beca34). Wording below is a
> paraphrase, not a verbatim copy.

## 1. Context
- Effort: 6–8 hours. Deadline: 3 calendar days from receipt.
- Stixor data scientists act as solution engineers. The task simulates a compressed week of client work.
- A polished product is NOT expected. Clear thinking, working code, and honest judgment are.
- Deliberately cutting scope and explaining why is a strength.
- After submission, passing candidates get a 60-minute technical session (code walkthrough,
  live modification exercise, concepts discussion). It carries as much weight as the submission.

## 2. Scenario
PayGuard is a fictional digital payments company in an emerging market with two problems:
1. Rising fraud losses: is ML fraud detection viable, and what would production need?
2. A support team overwhelmed by free-text complaints: can LLMs triage them (route to a team,
   write a summary) without hallucinating or misrouting sensitive cases?

Deliverable: feasibility prototypes for both, plus a short production-rollout memo.

## 3. Part A — Fraud detection prototype (~3 h)
**Data:** Credit Card Fraud Detection (ULB), `creditcard.csv`
(https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud). Fraud is about 0.17% of rows.

**Required**
- A sound train/evaluation method, with attention to what could invalidate results.
- Written, justified choice of metric(s). Accuracy alone is a red flag.
- At least one baseline and one stronger model; the comparison and reasoning matter.
- Short discussion (README or notebook) of the operating score threshold and the cost of
  false positives vs. false negatives.
- Short note on real-time inference: how it affects features and modelling.

**Not wanted:** extensive hyperparameter tuning, ensembling for leaderboard gains, deep
learning for its own sake (only if justified).

## 4. Part B — LLM complaint triage prototype (~3 h)
**Data:** CFPB Consumer Complaint Database
(https://www.consumerfinance.gov/data-research/consumer-complaints/). Use a filtered slice of
about 300–500 complaints with narratives, any product category. Document the exact slice so it
can be reproduced.

**Output:** pipeline turning a raw narrative into a structured triage record:
| Field | Spec |
|---|---|
| `category` | routing destination from a taxonomy the candidate defines (5–8 categories) |
| `urgency` | `low` \| `medium` \| `high` |
| `summary` | 1–2 sentences |
| `requires_human` | true/false |
| `confidence_note` | when and why the triage might be wrong |

**LLM provider:** any, including free-tier or local models.

**Required**
- Robust LLM-as-component handling: structured output enforcement, failure/retry handling,
  malformed-response handling.
- An evaluation approach (the heart of Part B): hand-label a small sample, define "correct",
  measure it, and state what to measure at scale.
- Awareness of failure modes: hallucinated categories, prompt injection via complaint text,
  sensitive cases (fraud allegations, legal threats) that must not be auto-closed.
- Cost and latency awareness: rough per-complaint cost and implications at 50,000 complaints/month.

**Not wanted:** fine-tuning (out of scope), a chatbot UI (batch script or notebook is right).

## 5. Part C — Production design memo (~1–2 h)
A 1–2 page memo to PayGuard's CTO on taking ONE of the two prototypes (candidate's choice) to
production. Must cover:
- System architecture (a simple diagram is welcome)
- Post-launch monitoring: what fails silently and how to catch it
- Data: privacy, residency, retention (the regulator requires customer data to stay in-country)
- A realistic phased rollout with a human-in-the-loop stage
- What is needed from PayGuard's team

Tone: technical executive, precise, concrete, no filler.

## 6. AI tool policy
- AI assistants are encouraged.
- Disclose in `AI_USAGE.md`: tools used, what for, and roughly what share of code they produced.
  **Undisclosed AI use discovered later is disqualifying.**
- The candidate must be able to explain and modify every line in the review session.

## 7. Deliverables (one GitHub repository)
1. Code for Parts A and B, runnable from a clean environment (requirements.txt or pyproject.toml,
   seed data or download instructions).
2. `README.md`: setup, approach, results, and what was cut and why.
3. `memo.md` or `memo.pdf` (Part C).
4. `AI_USAGE.md`.
5. Optional: screen recording of 5 minutes or less.

## 8. Evaluation criteria (priority order)
1. Judgment: framing, metrics, scope, honesty about limits
2. Evaluation rigor, especially for the LLM part
3. Code quality: clear and structured, not enterprise ceremony
4. Communication: memo and README client-ready
5. Results: scores matter least if the method is sound

## 9. Tech stack
The brief names no required language or libraries. Only requirement: a GitHub repo with
dependency file and an LLM provider of the candidate's choice.

## 10. Clarifications
Questions go by email to Stixor (address on the wiki page; not captured here).
