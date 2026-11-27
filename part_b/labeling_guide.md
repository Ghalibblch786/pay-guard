# Labeling guide

Written without reading any complaint and not checked against real data (SPECS D-32). Label from the sanitized text only. CFPB Product and Issue are hidden.
**Label before seeing any model output.** Start at item 1 and go in order **without skipping**: any prefix of the frozen random order is a valid sample. Target: at least the first 30.
Every record in this dataset is a complaint filed with a regulator: **the act of filing it never counts** as a legal threat or an escalation.

## category (exactly one; codes in `taxonomy.json`)
Choose the category of the **main problem the company has to solve**. If several apply, take the first that matches in this order:

1. `unauthorized_or_fraud`: no consent, theft, account takeover, or deception (including a fake seller or an impersonator), **even if the person is now disputing it** or the bank refused a claim.
2. `account_access_or_closure`: the account or money is frozen, held, closed or unreachable, and that is the main problem.
3. `dispute_or_refund`: non-fraud disagreement about a purchase, charge, refund or its dispute process.
4. `payment_or_transfer_problem`: a movement of money that failed, is delayed, misdirected or wrong.
5. `fees_interest_or_billing`: fees, interest, rewards, statements, terms.
6. `service_conduct`: only when behaviour or communication is itself the core problem.
7. `other`: nothing fits, or it cannot be understood.

## urgency (`low`, `medium`, `high`)
Judge the situation **as the text describes it at the time of writing**. Angry wording does not raise urgency. Use the highest level that applies.
- `high`: any of: fraud or unauthorized activity that may be continuing or whose money is not recovered; the person cannot reach money they need now, or describes hardship (rent, food, medicine, bills unpaid because of it); a stated deadline with serious loss; safety or self-harm risk.
- `medium`: an unresolved problem with a current effect that is not in `high`: money in question, a blocked service with another way round, a wrong charge or report still standing.
- `low`: information, feedback, or a past problem that is already resolved.

## requires_human (`y` or `n`)
**`y` if a person at the company must handle or check this before any automated reply or closure.** Mark `y` if any applies:
- an allegation of fraud, theft, unauthorized activity, scam or identity theft;
- a stated legal threat or legal process **beyond filing this complaint**: a lawyer, a lawsuit, court, or a plan to escalate to another authority;
- an allegation of discrimination or of unlawful conduct stated as such (for example naming a law said to be broken);
- safety, self-harm, abuse or threats;
- a vulnerable person affected (a child, an elderly person being exploited, a serious health crisis) or severe hardship;
- the text is too unclear or contradictory to triage safely.

Otherwise `n`. Decide from the content, **not** from whether you think the software would flag it.

## ambiguous (optional)
Put `y` if a reasonable second labeler could choose differently; otherwise leave it blank. You still must choose the three labels.

## Sheet format (`item,category,urgency,requires_human,ambiguous`)
`category`: a code above. `urgency`: `low`, `medium` or `high`. `requires_human`: `y` or `n`. These three are required for every item you label. Leave unlabeled items completely blank. No notes column.

Example (invented): `1,fees_interest_or_billing,low,n,`
