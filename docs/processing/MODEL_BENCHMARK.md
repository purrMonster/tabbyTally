# Model-only mailbox benchmark — verified 17 October 2026

## Decision and results

Retain **prompt v3, thinking off, temperature 0.7**. The complete 264-email baseline
is verified. Prompt experiments did not establish a reliable overall improvement,
so their changes were reverted rather than promoted. Keep processing review-only.

| Baseline measure | Result |
|---|---:|
| Emails accounted for | 264/264 |
| No readable body; not sent to model | 12 |
| Readable emails evaluated through adapter | 252 |
| Valid structured responses | 248/252 |
| Financial-event detection | 161/163 (98.8%) |
| Negative emails producing a valid transaction | 0/89 |
| Negative emails correctly labelled non_transaction | 84/89 |
| Amount / currency correct | 161/163 each (98.8%) |
| Account identifier correct | 154/162 (95.1%) |
| Direction correct | 160/162 (98.8%) |
| Checked event types correct | 63/67 (94.0%) |
| Date policy satisfied | 68/161 (42.2%) |
| UPI references correct | 91/91 |
| All checked fields correct per financial-event email | 67/163 (41.1%) |
| Active adapter time | 19.79 minutes |
| Median / p95 request time | 6.13 / 7.27 seconds |

The five unresolved negatives comprise two unsupported classifications and three
input-budget refusals. The event-detection failures comprise one missed payment
summary and one internally contradictory card-purchase response. All remain review
cases. No automatic imports were enabled.

**Date-policy accuracy is not calendar-date accuracy.** Many source dates use two-digit
years, while the normalized model input omits the email Date header. The benchmark
requires an unknown date instead of an inferred century. A plausible 2026 date can
therefore fail this check without being a demonstrably wrong calendar date. The low
all-fields score is heavily affected by this policy and must not be presented as a
universal extraction-accuracy percentage.

The useful next changes are to supply explicit, validated date context and resolve
bank date formats deterministically; improve account/transfer typing and evidence
span handling; and constrain classification/event consistency. Re-test these against
the same frozen labels, with clearly versioned label-policy changes where needed.
Obtain a later, untouched mailbox sample before making any generalization claim.

## Method

The user authorized evaluating all 264 supplied emails against the local model.
`benchmark_model.py` sends each complete, bounded normalized email directly to the
model adapter. Production template parsers are bypassed. There are no database,
inbox, unread-flag or Actual Budget writes. Raw emails stay in their source directory;
predictions and reviewed expectations remain in ignored `processing/exports/`.
No raw reasoning is stored. Progress output contains counters, status and elapsed time.

Run configuration: `fast`, llama-swap, thinking disabled, prompt `bank-extraction-v3`,
normalizer `email-text-v2`, temperature 0.7, context 8192, output target 6144,
minimum output 4096, reserve 512, deadline 1200 seconds per call. The model server
applies its own chat template and tokenizer during input-budget preflight. Inputs
that do not fit are counted as failures/abstentions, never omitted from the corpus.
Missing bodies are recorded as input-review cases without a model call.

This is one sequential run, not a load or concurrency benchmark. Latency includes
adapter subprocess startup, profile reads, token preflight, inference and parsing.
It excludes email-file normalization and downstream database validation/persistence.
No deployment settings or model profiles are changed for the benchmark.

## Reference labels and scoring

Source-format inspection established 163 financial-event messages, 89 negative messages
and 12 without readable bodies. Mixed account-update bodies were inspected individually:
payee/biometric changes and standing instructions are negative; actual credits,
repayments, NetBanking payments and RTGS events are financial-event messages.
An initiated RTGS is an event proposal, not proof of settlement or import eligibility.

Reference fields were generated with separate evaluation expressions after inspecting
the source clauses, without importing production templates or using model predictions.
The private expectations file was frozen before inspecting model field mismatches:
SHA-256 `6f51775a569fd08ae40e7a7c6b894e183e9cde4b6dcfd13914ed1496d471060a`.
These are assistant-reviewed, format-assisted labels, not a user-certified ledger.

The reference set checks amounts/currencies for 163 messages, account suffixes and
direction for 162, dates for 161, UPI references for 91, and unambiguous event types
for 67. Completed RTGS names only the beneficiary, so the owned-account field is not
scored for that message. Two-digit years without sufficient input context must remain
unknown. Merchant canonicalization, bank/product labels, ownership, lifecycle and
duplicate-event matching are not comprehensively scored.

Money comparisons use decimal equivalence. Account comparisons allow a masked number
or bare suffix, but reject invented labels such as `ending 1234`. Classification,
event count and field errors are retained even when JSON is valid. Exact evidence
checks require each quoted span to exist uniquely in normalized input; this measures
traceability, not whether the quote semantically proves its field.

This corpus already informed prompt/template development. It is a development-corpus
benchmark, not an unseen holdout or a generalization guarantee. One stochastic run
does not establish repeatability. The review-only production gate remains unchanged.

## Reproduce and resume

With the approved local model configuration in the environment:

```powershell
$env:PYTHONPATH='processing/src'
python processing/tests/benchmark_model.py 'C:/Users/jyotirmoyc/Desktop/Projects/testData/New folder' --output processing/exports/model-benchmark-v3.jsonl
python processing/tests/score_benchmark.py processing/exports/benchmark-expectations.json processing/exports/model-benchmark-v3.jsonl --inventory processing/exports/corpus.json --output processing/exports/benchmark-score.json
python -m unittest discover -s processing/tests -p test_benchmark.py -v
```

Reusing the same output resumes completed source hashes; configuration identity must
match. Use a new output filename for an independent repeat or changed configuration.
Private expectation construction scripts and per-message mismatch details are retained
in `processing/exports/` for local audit. Do not commit those files.

## Completed baseline (v3; 16 October 2026)

The interrupted chat did not stop the local benchmark: all 264 records were saved.
252 readable emails reached the adapter: 248 valid outputs, one contradictory output,
and three input-budget refusals. Twelve messages had no readable body.

- Financial-event detection: 161/163; one missed payment summary and one invalid card
  purchase response. No negative message produced a valid transaction proposal.
- Negatives: 84/89 correctly labelled non_transaction; two test messages labelled
  unsupported; three long promotional emails refused by input-budget preflight.
- Amount and currency: 161/163 each. Account identifiers: 154/162. Direction: 160/162.
- Dates: 68/161. The major failure was inventing full years from two-digit dates.
- Event type: 63/67; incoming UPI transfers were sometimes labelled income.
- UPI references: 91/91. All checked fields matched on 67/163 event messages.
- Evidence: 48/161 returned events had at least one non-unique or absent quoted span.
- Adapter time: 1187.404 seconds (19.79 minutes), median 6.133 s, p95 7.266 s,
  maximum 8.422 s. 483537 reported total tokens. All observed routing was normal/9B.

These denominators include missing/invalid predictions as failures. The all-fields
score covers only the reference fields defined above, not every schema property.

## Prompt experiments (17 October 2026)

v4 rewrote the priorities but overcorrected date handling: the model withheld known
four-digit dates. The run was stopped and is excluded from final comparisons. It also
had a 51.312-second first request versus roughly 6–8-second subsequent requests,
consistent with the user's suggested model-loading delay; loading telemetry was not
verified. Startup and subsequent-request latency are now reported separately, while
startup stays included in totals.

v5 adds explicit positive date examples for named-month and numeric formats, stricter
account syntax, transfer-versus-income guidance, payment-summary recognition and unique
verbatim evidence requirements. A 35-message targeted set covered prior failures,
previously correct card alerts, loan payments, OTPs and all mixed account updates.
At temperature 0.7 it produced 32 valid outputs and three contradictory classifications;
20/22 financial-event messages matched all checked fields. This is tuning evidence.

A configurable MODEL_TEMPERATURE was added (finite range 0–2; library fallback remains
0.7), included in pipeline identity. Temperature zero is being compared with the same
v5 prompt; it does not guarantee identical outputs across model/server changes.
The v5/temperature-zero full-corpus run reuses its first 35 targeted results and then
processes the remaining files, so its order differs from the alphabetical v3 baseline.
Performance totals sum active call time and exclude the pause between those segments.

61 containerized regression tests passed after adding temperature validation. A prior
host test attempt was blocked by Windows sandbox temporary-file permissions; it was
rerun in the normal isolated Docker environment. No production deployment was changed.

### Resume after usage limits

The v5 temperature-zero experiment was stopped after it produced valid purchase
proposals for two OTP emails. It is rejected, regardless of its improved date scores.
v6 restores the exact v3 prompt from the previously built local image and prepends
only positive/negative date-format examples. Temperature stays at the baseline 0.7.
The next gate includes all 89 readable negative messages plus 22 financial-event cases
(111 messages total), before processing the remaining corpus. Baseline and rejected
experiment results remain private for audit; no production activation occurred.

The first attempt to start v6 did not execute: automatic approval review could not
complete because of the account usage limit. The user requested resumption after reset.

### Final v6 acceptance comparison

After resumption, all 111 acceptance cases completed: all 89 readable negatives and
22 selected financial-event messages. v6 produced no false transaction proposals in
the negative cohort, but did not improve overall field extraction on the paired cases:

| Same 111-case subset | Baseline v3 | Candidate v6 |
|---|---:|---:|
| Financial events detected | 20/22 | 20/22 |
| All checked fields correct | 15/22 | 13/22 |
| Date policy correct | 14/20 | 15/20 |
| Account identifiers correct | 19/21 | 18/21 |
| UPI references correct | 2/2 | 1/2 |
| Input-budget refusals | 3 | 4 |

v6 was rejected. No full-corpus v6 run was needed after failing the paired acceptance
gate. v3 was restored byte-for-byte from the pre-experiment local image; prompt hash
`edf55e14c43183d130abdff83782002cbf6838e7196899b9c749811703c5b1ff` matches the complete
baseline run. Experiments are single stochastic runs and cannot prove tiny differences
statistically, but they do not provide evidence for promoting the candidates.

The retained code changes are the private resumable benchmark, aggregate scorer,
scoring tests, configurable bounded temperature and run identity guard. The example
continues with thinking disabled and temperature 0.7. 61 isolated regression tests
passed for the latest adapter changes; the restored prompt matches the tested baseline.
