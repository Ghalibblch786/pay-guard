# Manual leak review: definitions and pass rule

All examples below are invented. These definitions are fixed before a batch is generated: the summary refuses a batch if this file changed afterwards.

## Reading a batch safely
- In **macOS Terminal** (not VS Code): `LESSHISTFILE=- less data/processed/sanitizer_review/batch_01/items.txt`. Do not add `-R`.
- Do not copy, screenshot, upload, move or edit the file. Do not paste any part of it into a chat. Clear the Terminal window afterwards.
- Record answers in `verdicts.csv` in the same folder with a plain-text editor such as `nano`. It has no notes column; never type narrative text into it.

Answer each of the three questions for every item: `y` (yes), `n` (no) or `u` (unsure). Judge only what you see in the sanitized text.
Placeholders such as `[PERSON]` or `[NUMBER_ID]` are not findings by themselves.

## 1. direct_leak
**Does the text still contain something that, by itself, identifies or reaches a private person or their account?**

| `direct_types` code | Counts |
|---|---|
| name | any part of a private person's name, including a first name alone |
| email, phone, address | including partly written or oddly formatted ones; address means a street or mailing address |
| account_or_card_number | account, card, loan, claim or reference numbers, full or partial (for example "my card 4821") |
| government_id | SSN, licence, passport or tax numbers, full or partial |
| birth_date | a date of birth |
| handle_or_url | a username, payment tag, or link pointing to a person or their account |
| other | any other direct identifier, such as a licence plate |

Not a direct leak on their own: banks and other large companies, agencies, laws, money amounts, transaction dates, job titles.

## 2. indirect_concern
**With no direct identifier needed: could the remaining details, alone or combined, realistically let someone who knows the person, or who searches public sources,
work out which private individual this is?** This covers the writer and anyone they describe.

| Answer | Invented examples |
|---|---|
| y | "I am the only dentist in a town of 300 people." (rare role in a very small group) |
| y | "My bakery, Blue Kettle Pies, lost its account." (a small business that points to its owner) |
| y | "After our house fire was on the local evening news, the bank froze my card." (an event that can be looked up) |
| y | "At 71, I retired last spring as principal of the high school near the old mill." (several details that narrow to one person) |
| n | "A large bank charged me two overdraft fees of $35." |
| n | "I am retired and live on a fixed income." (true of very many people) |
| n | "I sent $500 through a payment app to a seller I met online, who disappeared." (a common story with nothing distinctive) |
| n | "[PERSON] at the [LOCATION] branch told me to wait." |
| u | "I coach at a school here and my store was in the paper." when you cannot tell how many people this could be |

An unusual story is not enough: the question is whether it points to a particular person.

## 3. visible_sensitive
**Does the sanitized text itself show sensitive content about a person, in one of these categories?**

This describes **only what is still visible after sanitizing**. It cannot show what the original text contained or what the flagger should have caught,
and it is **not a measure of flagger recall** or of missed flags.

| `visible_sensitive_category` code | Counts | Does not count on its own |
|---|---|---|
| health_medical | a person's illness, injury, treatment, disability, pregnancy or mental health | a company name containing "health" that says nothing about a person |
| minors | information about a particular child under 18 | "a family account" |
| government_id | a person's identity numbers or identity documents | naming a government agency |
| financial_account_details | account, routing or card numbers (even partial), card expiry or security codes | having an account, balances, fees, transactions |
| credentials_authentication | a person's passwords, PINs, one-time codes, security answers or how they were shared | "I logged in" |
| immigration_legal_case | immigration status, or a person's court case, court order or case number | "I may hire a lawyer", filing this complaint |
| self_harm_safety | self-harm, suicide, abuse, stalking or threats to someone's safety | being upset or stressed |

An item can be a finding under more than one question; mark each one that applies.

## Recording
- `direct_types` and `visible_sensitive_category`: required when the answer is `y`, empty when it is `n`, optional when `u`. Separate several codes with `;`.
- `indirect_concern` has no detail column.

## Pass rule (sign-off)
A batch **passes only if all 30 items are `n` for all three questions.**
- A `y` on any question for any item **fails** the batch.
- A `u` **fails** it too: unsure is treated as yes.
- This applies to `indirect_concern` exactly as to the others. There is **no case-by-case waiver** after results are seen.

If a batch fails, describe the problem by type, with an invented example if needed. A new batch requires a reviewed fix that changes the sanitizer or flagger. There are at most three batches.
If indirect concerns cannot be fixed by general rules, the review stops: sanitized text is not signed off for external use, and what to do next (for example, a local model) is a new, documented decision.

## Check and record
1. Preview (changes nothing): `.venv/bin/python -I part_b/summarize_review.py 1`
2. When you are sure: add `--record`. This is final.
