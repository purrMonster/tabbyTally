# Extraction, validation and review contracts

Status: implementation contracts with live integration gates tracked in RUNBOOK.md.
Phase 2 produces candidates, never budget writes. As of 18 October, approved exact
purchase templates can produce ready budgeting candidates without asserting bank
settlement. Email-date and sole-bank-account fallbacks are explicit user-approved
policies with provenance; see RUNBOOK.md sections 21–22. Local review/corrections and
signed action API are implemented. The disabled meowGram consumer follows the
[durable-send-v1 contract](MEOWGRAM.md). Provider and authenticated human-action
bridge are implemented and locally verified on the meowGram integration branch;
live deployment remains pending.

## Input preparation and provenance

Prefer useful plain text; fall back to sanitized HTML text. Never execute HTML, follow
links, fetch images or load external resources. Preserve the original receiver row.
Store normalized text in protected processing storage with its hash, normalizer version,
source ID/hash and an evidence-offset convention. Offsets refer to the stored normalized
text, not to raw MIME. Preserve sufficient context to distinguish amounts and accounts.

Set explicit byte, character, token and response limits before enabling the model adapter.
Choose them from the verified model context capacity and reserve space for instructions
and output. If relevant content cannot fit, produce `input_incomplete` review; truncation
must not silently qualify a candidate. Capture parse failures, oversized messages and
attachment-only evidence require review. Attachment/PDF extraction is deferred.

Email text is untrusted data. The model receives no tools, secrets or write authority.
Embedded instructions must not change the extraction schema or validation policy.

Record pipeline/code version, attempt ID, source and input hashes, normalizer version,
prompt version/hash, schema version, model endpoint configuration identity, requested
alias, resolved model version when available, sampling settings and response timing.
If the provider cannot report immutable model identity, record that limitation; an alias
alone is not a reproducible model version. Never store API credentials in provenance.

## Structured extraction

Require a strict, versioned object with classification, events array, unresolved fields
and evidence. Reject extra fields, wrong types, invalid enums, overlong values and
excessive event counts. Parse JSON without evaluating generated code. Missing facts use
null plus a reason; do not fill them from model confidence or majority-currency assumptions.

| Field | Contract |
|---|---|
| classification | transaction, non_transaction, ambiguous or unsupported |
| event_type | purchase, refund, income, transfer, card_repayment, cash_withdrawal, loan_payment, fee, authorization or unknown |
| bank / product | Explicit source identity or unknown |
| account_identifier | Masked identifier and identifier type, with evidence; no invented account ID |
| transaction_amount | Decimal text and explicit currency; not a balance or payment due |
| original_amount / billed_amount | Separate decimal-text/currency objects; either may be unknown |
| direction | debit, credit or unknown relative to the identified account |
| transaction_date | Source date/time, precision and known timezone; unknown parts stay unknown |
| merchant / counterparty | Source-supported text or null |
| reference | Source-supported bank reference or null, with reference type if known |
| lifecycle | authorized, posted, reversed or unknown; no inferred settlement |
| evidence | Quoted spans and offsets for each critical field |
| unresolved_fields | Field names and explicit reason codes |

Zero, one or multiple events per email are valid. Keep balance, available credit and dues
as separately labelled context only if needed for validation; never substitute them for
an event amount. Persist bounded malformed-response diagnostics in protected storage,
not routine logs. One optional repair shares the original deadline and cannot invent
facts. If output still fails, complete with a review item rather than loop indefinitely.

## Deterministic eligibility

Application code validates the schema, verifies evidence spans, resolves accounts and
applies versioned financial rules. Evidence matching is necessary but not sufficient:
the role of an amount and account still needs supported classification rules. Candidates
become `ready` only when all required checks pass for a supported format/event policy.
Record rule IDs, reasons, rule version and mapping version on every decision.

| Check | Required behaviour |
|---|---|
| Money | Parse exact decimals; use currency-aware minor units and reject unsupported precision/range; never binary floats |
| Currency | Require explicit evidence or an approved deterministic mapping rule; never infer INR from popularity |
| Dates | Validate calendar values, source precision and ambiguity; preserve date-only facts; never silently replace transaction date with receipt date |
| Account | Resolve bank, product and identifier against enabled mappings; suffix collisions or multiple matches require review |
| Direction/type | Require consistent event semantics; distinguish expenses from own-account movements |
| Evidence | Critical facts must be supported by retained source context or explicit audited human correction |
| Duplicates | Separate source duplication from financial-event duplication; use scoped references and corroborating facts |
| Format coverage | Unsupported formats/event lifecycles remain review-only until regression-tested |

Use `ready`, `needs_review`, `ignored` and `duplicate_suspected` as candidate dispositions.
Emails with no financial event have a durable message-level ignored outcome and reason.
Do not create dummy transactions for OTPs or operational failures.

Specific handling:

- OTPs, promotions, declined attempts, reminders, statements and balance-only messages
  create no expense candidates. Mixed messages containing a real transaction still need
  event-level evaluation; a keyword alone must not discard the transaction.
- Keep foreign original and billed amounts separately. An original USD purchase with no
  final INR amount remains unresolved for an INR account. Never calculate a guessed charge.
- Preserve authorization status; an authorization is not evidence of a posted debit.
  Unsupported authorization/reversal matching requires review.
- Identify both sides of own-account transfers and card repayments. Correlate only with
  sufficient account, reference, amount/currency and time evidence. Ambiguous or missing
  counterparts stay reviewable and cannot become two independent expenses.
- Treat loan payments as expenses for v1, without inventing principal/interest splits.
- Repeated notices with a strong shared event identity may link to an existing candidate.
  Same date/amount/merchant alone only suggests a duplicate. Check concurrent arrivals
  under transactional serialization for strong identities; do not rely on a pre-insert
  lookup alone. New pipeline versions must also check prior authoritative candidates.

“Ready” means eligible for the later handoff under current policy. It does not mean
imported, posted, statement-reconciled or confirmed by Actual rules.

## Review and correction

Persist source/candidate IDs, proposed facts, reason codes, evidence, revision and available
actions before delivering a notification. Allow job/source-level review where no valid
candidate exists. Provide local inspection and correction before messaging integration.

Proposed callback contract: authenticated actor, provider/action ID, review ID, expected
revision, action (`correct`, `approve`, `ignore`, `defer`) and bounded correction fields.
Use the messaging provider's verified signature/identity mechanism, or a separately
authenticated API; a review ID or guess-resistant URL alone is not authorization.
Validate signature timestamp/nonce where supported, authorize the actor, and rate-limit.

Within one transaction:

1. Check the action receipt. The same action ID and request digest returns the committed
   result; the same ID with a different payload is rejected.
2. Lock the review/candidate and compare the expected revision and open state. Reject
   stale or competing actions without mutation.
3. Apply a correction to that candidate, preserve prior facts and rerun validation.
   Approval cannot override missing required financial facts merely by changing status.
4. Append the decision and actor/time audit record, increment the revision, and persist
   any notification intent and callback receipt with the resulting response.

Acknowledgement loss is safe because replay returns the stored result. Corrected facts
retain human provenance; original extraction and evidence remain immutable. Reopening or
superseding a resolved candidate is an explicit audited operation. Stale notifications
cannot resolve newer revisions.

Notification delivery uses stable outbox IDs, independent leases/backoff and provider
idempotency keys where supported. Without provider idempotency, a crash after sending can
cause a duplicate notification; document this limitation and keep callbacks repeat-safe.
Default summaries omit raw email text, full identifiers and unnecessary financial details.

A correction affects one candidate first. Promote examples or reusable rules through an
explicit proposal, regression evaluation and versioned release. Account mapping changes
are also explicit; no blanket rule or silent fine-tuning follows one correction.

## Phase 3 handoff contract

Expose an inspectable candidate ID/revision, source/event identity, logical account,
validated amounts/currencies/direction/date, event/lifecycle type, evidence references,
validation/mapping versions, review history and transfer/duplicate links. Only a selected
authoritative eligible revision may be queued for import. Phase 3 adds Actual account
binding, import idempotency and uncertain-write reconciliation; none is implemented here.
