# Memo: taking LLM complaint triage to production

**To:** CTO, PayGuard · **From:** AI Engineering · **Date:** 27 November 2026

This memo covers **complaint triage**, not fraud detection: it raises more open questions on privacy, data residency and failures that go unnoticed. Real-time fraud scoring is outlined in the [README](README.md#real-time-inference-a6).

## Decision requested
Fund **offline evaluation (phase 0) only**. Do not ship this model, and do not start shadow mode until a candidate beats simple baselines. The engineering pattern runs end to end on public US complaint data; **the model's decisions are not yet useful**.

**What the prototype measured** (3B local model; 30 complaints labeled by one person; 26 reached the model):
- **Escalation does not discriminate.** All 11 cases needing a person were caught only because **everything** was sent to a person: 30/30 labeled, 400/400 in the larger run. With 11 cases, even this recall has a 95% lower bound of just 0.74.
- **Category: 10 of 26 correct**, the same as always guessing the most common category.
- **Urgency: 21 of 26 exact**, against 15 for always guessing "medium". Promising, but a small sample.
- **Keyword rules and flags without a model** caught only 7 of 11 while escalating 16 of 30.
- **Injection:** in all 3 synthetic cases where complaint text instructed the model to downgrade it, the model returned the requested downgrade. Keyword rules still escalated 2; **1 got through** as low priority with no human needed. Summary accuracy was not rated.

## Architecture (everything inside the country)
```
Complaint ─► Intake store (raw text stays here) ─► Safety rules + sensitive flags ─ flagged ─► Human queue
          ─► PII redaction ─► Self-hosted LLM (pinned, no external API) ─► Schema check, max 3 tries ─ invalid ─► Human
          ─► Rules can only ADD "needs a human" ─► Suggestion + summary ─► Agent confirms or corrects
          ─► Decision log (no raw text) ─► Monitoring, audit samples, golden-set tests
```
Nothing is closed or answered automatically. A failure at any step sends the complaint to a person; none is dropped.

## Data: residency, privacy, retention
- **Residency.** The model, redaction, logs and backups run on infrastructure in-country. No complaint text goes to a hosted LLM API. The prototype did this with a local model.
- **Redaction is risk reduction, not anonymization.** The prototype's manual review of 30 redacted complaints **failed** (2 indirect-identification concerns), so redaction was **not signed off**. Treat redacted text as personal data: same access control, residency and retention as the original.
- **Minimise.** Models see redacted text only. Credentials, health, minors, government IDs and self-harm content bypass the model.
- **Retention (proposal for your privacy officer).** Raw text: only in the system of record, under its existing schedule. Redacted prompts and model replies: encrypted, 30 days, then delete. Decision log (IDs, labels, versions, who overrode what): as long as the regulator requires for complaint handling. Deletions must reach caches, audit and golden sets.

## What fails silently, and how we catch it
Valid-looking output is the main risk: the schema check cannot tell that a category or "no human needed" is wrong. Thresholds are starting values to tune in shadow mode.

| Silent failure | Detector | Alert / action |
|---|---|---|
| A case that needs a person is not escalated | Agents review every complaint in shadow and assist phases. Later, a daily random sample of at least 50 non-escalated cases; reopened and regulator-escalated complaints traced back | Any confirmed missed fraud or safety case: incident; stop auto-routing until explained |
| Wrong category | Agent corrections; weekly blind relabel of 100 random cases by a second person | Agreement drops 5 points below the pilot baseline |
| Summary invents or drops facts | 50 summaries a week rated against the source | Any unsupported claim about money or fraud; more than 5% unsupported overall |
| Input drift (new products, scams, languages, code-switching) | Weekly mix of category, language and length against baseline; share of `other` | Any share moves more than 5 points; unsupported language above 1% |
| Redaction misses identifiers | Weekly local review of 100 redacted records | Any direct identifier: incident, fix, retest |
| Model, rules or flags escalate everything, or stop firing | Daily escalation (model alone and final), flag and per-rule rates | Near 0% or 100%, or 10 points from the 4-week average |
| Quiet degradation | Fallback, retry and too-long-input rates; latency; queue age | Fallbacks above 2% a day; escalated item older than its service level |
| Prompt injection, or a model, prompt or rule change | Pinned model; golden and attack suite in CI; rule hit counts | No release if recall falls or an attack newly fails |

## Phased rollout with a human in the loop
| Phase | What happens | Exit gate (all must hold) |
|---|---|---|
| 0. Offline, 3–4 weeks | In-country PayGuard data. Two labelers, agreed guide. Compare larger models, revised prompts and a simple classifier on a held-out set | Labeler agreement acceptable to the support lead; privacy sign-off; the candidate **clearly beats** majority-class category guessing and rules-only escalation, **does not escalate everything**, and passes the attack suite or has an agreed safeguard |
| 1. Shadow, 4 weeks | System runs; agents never see its output | Escalation recall: lower 95% bound at least 0.95, overall and for fraud (with zero misses this needs about 60 true cases per group, more with any miss); no direct identifier in weekly redaction reviews |
| 2. Assist, 6–8 weeks | Agents see suggestions and confirm every case | Faster handling without more reopened complaints; correction rate stable |
| 3. Limited auto-routing | Auto-assign only low-risk categories that met the gate. Every "needs a human" case still goes to a person. No auto-closure or auto-reply | Reviewed monthly; one switch returns to phase 2 |

If the gates are not met, do not ship the model. Keep human review of every complaint; rules may raise priority but must not remove anyone from review.

## Capacity and cost at 50,000 complaints a month
Measured on an 8 GB Apple M2 laptop with a 3B model, one request at a time: 400 records, 333 sent to the model, no retries or fallbacks; about 1,126 input and 104 output tokens per call; mean 3.9 s per call on mains power (12.5 s in an earlier run on battery under load).

| At 50,000 a month (83% reaching the model) | Estimate |
|---|---|
| Model calls / tokens | about 41,600 / 51 million |
| Sequential model time | 45–145 hours a month on the test laptop (peaks and concurrency untested) |
| Infrastructure (**assumption**: two in-country GPU servers, US$0.50–1.50 per hour each, always on) | US$730–2,190 a month; US$0.015–0.044 per complaint |
| Human review at the measured escalation rate (100%); **assumption**: 3-6 minutes each | **2,500-5,000 agent hours a month**, about 16-31 full-time agents at 160 hours. Multiply by your loaded hourly cost |

The prototype therefore **saves no review work** over reading every complaint. Time saved by suggestions or summaries was not measured. Inference capacity is unlikely to be the constraint at this volume; **agent time and model quality are**. A larger model changes latency and hardware, and must be measured again.

## What we need from PayGuard
- **Data and platform:** 6–12 months of complaints with routing and outcomes, in-country; customer languages; a GPU server plus standby, access control, ticketing integration.
- **People and decisions:** a support lead who owns categories and escalation policy; two labelers (about 2 weeks part-time); fraud and compliance reviewers; what may never be automated, human-queue service levels, and who can stop the system.
- **Legal and privacy:** written residency and retention requirements; lawful basis for evaluation use; an incident process.

## What we do not know
Accuracy on PayGuard's customers, products or languages; performance of a larger model; redaction quality in local formats; real escalation volume. Why the model escalates every real complaint (it did not do so on short invented ones) was not investigated. The prototype used one month of public US complaints, a small untuned model and one labeler.
