# Local email corpus evaluation — 16 October 2026

The user approved all 264 supplied `.eml` files, including non-transactional mail.
The files remain outside the repository. Private derived text is under ignored
`processing/exports/`; the Docker build excludes that directory. Do not copy real
messages, account details, OTPs or model reasoning into tracked fixtures or logs.

## Executed offline checks

All 264 files have distinct raw SHA-256 hashes. This does not establish distinct
financial events: different emails can describe the same transaction.

| Check | Result |
|---|---:|
| Emails inspected by normalization and template matching | 264 |
| HDFC card template proposals | 44 |
| ICICI card template proposals | 12 |
| HDFC UPI template proposals | 43 |
| Model/review fallback | 165 |
| Independently selected clear negative cohort | 54 |
| Positive template matches in that negative cohort | 0 |
| No readable body | 12 |
| Model calls in this offline evaluation | 0 |

These are coverage and negative guard results, **not field accuracy or model accuracy**.
The remaining messages have not all received independent field-level gold labels.
The negative cohort is a conservative subject-family selection made after inspecting
formats; it is test-only and never an automatic production ignore rule.

## Changes informed by the corpus

Three narrow parsers require an exact subject and a matching transaction clause.
They preserve source evidence and propose structured facts before model fallback.
Multiple matching clauses or additional debit/credit clauses refuse the shortcut.
Unsupported or malformed formats fall through. No template grants import eligibility.
Two-digit years remain unresolved; settlement remains unknown. Currency conversion
is never invented. Template version is part of immutable pipeline configuration.

HTML input now has a separate 1 MB parser limit, followed by the unchanged 24 KB
visible-text limit. This recovers eight markup-heavy messages previously refused by
the raw 24 KB limit. Oversized visible text is refused, not sliced. Missing bodies
remain review items; a transaction-looking subject alone is insufficient.

Prompt v3 includes the full schema and clarifies balances versus transaction amounts,
OTPs versus purchases without OTP, offers versus paid EMIs, card repayments, unknown
transfer ownership, and notices/statements. Full evidence clauses are requested.

## Negative scenarios

The synthetic regression suite checks OTPs carrying USD amounts, EMI offers carrying
balances, payment dues, biometric changes, future standing instructions and declined
attempts, even when paired with a transaction subject. It also checks that an OTP
security footer does not invalidate a real card purchase and that an available credit
limit is not extracted as the purchase amount.

Do not classify the HDFC “View: Account update” family uniformly: it contains credited
money and repayments alongside biometric changes, payee management and future standing
instructions. Initiated RTGS and completed RTGS are different lifecycle evidence.
Loan repayments remain expenses under the v1 policy; card repayments and own-account
transfers require movement handling. Monthly statements are not individual purchases.

## Reproduce

From the project root, with processing dependencies installed:

```powershell
$env:PYTHONPATH='processing/src'
python processing/tests/evaluate_corpus.py 'C:/Users/jyotirmoyc/Desktop/Projects/testData/New folder'
docker compose -f processing/compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests --attach tests
docker compose -f processing/compose.test.yaml down
```

The corpus command prints only aggregate counters. It does not call the model or
write to the database/inbox. `corpus_inventory.py` is a separate private diagnostic
export; its family summary can contain identifying subject text and should not be
copied into routine logs.

## Remaining acceptance work

Create independently reviewed per-message event/field labels and freeze a holdout
before further tuning. Since the current corpus has already informed these rules,
it is development evidence, not an untouched holdout. Obtain later emails for a
genuine unseen-format check. Compare thinking on/off with identical labelled inputs,
report field errors and false-positive transaction rates separately, and retain
timeouts/abstentions in the denominator. Do not promote formats to auto-import on
the strength of template coverage or syntactic JSON validity.
