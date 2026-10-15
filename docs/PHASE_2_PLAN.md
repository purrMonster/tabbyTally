# Phase 2 — durable email processing and transaction preview

Date: 15 October 2026. Status: proposed implementation sequence, not shipped features.
Phase 1 is complete for the single live inbox. This phase ends with validated transaction
candidates and a durable ambiguity queue, before any Actual Budget writes.

## Outcome and boundaries

Turn each eligible captured email into a traceable result: ready candidate, needs review,
non-transaction, duplicate candidate, or processing failure. PostgreSQL owns durable state;
n8n orchestrates and the local model extracts. Keep the generic receiver independent of
banking logic, model endpoints, and n8n webhooks. No new bank accounts are created in
Actual automatically. A later Actual bridge handles financial writes with idempotency.

Retain the user's decisions: HDFC, Axis and ICICI; savings and credit-card alerts;
overseas purchases on Indian cards; loans as payment expenses for v1; own-account
transfers and card repayments require linking; valid events eventually auto-import;
ambiguous events require review. No statement reconciliation or historic inbox import
is introduced in this phase. Majority INR does not authorize silently converting foreign
amounts or assuming an unknown currency. No second live inbox is required.

## Step 1 — verify interfaces and deployment

Record deployed n8n version, its PostgreSQL trigger capability, and reachable private
addresses. The fleet is multiple nodes on one subnet, with Traefik per node. Docker's
postgres service name is local to its Compose network; a remote n8n node cannot use it.
Plan a private PostgreSQL TCP endpoint, source-restricted firewall access, credentials,
and TLS appropriate to the fleet. Do not route PostgreSQL through an ordinary HTTP
Traefik router. Verify database connectivity with a harmless query, then verify model
endpoint, authentication, request format, model alias and structured-output support.
The existing receiver Compose does not publish a PostgreSQL port; opening access is a
separate explicit deployment step. Keep actual endpoints and credentials out of Git.

Confirm the local model service name (the conversation called it llm-swap/llama-swap)
and its actual API before generating workflow nodes. Do not assume an OpenAI-compatible
endpoint or JSON-schema support without checking. Model selection follows sample-based
evaluation rather than prescribing a model before inspecting available hardware/emails.

Deliver: redacted connection contract and a minimal n8n connectivity workflow. User
inputs needed at this stage: n8n version/address, model API/address/alias, and anonymized
representative mail samples. Do not request passwords in chat.

## Step 2 — downstream schema and privileges

Create a separate processing schema with its own migration history. Do not mix bank
interpretation state into immutable captured source rows. Proposed tables:

| Table | Responsibility and key fields |
|---|---|
| processing_runs | Explicit activation boundary/run ID, pipeline version, selected source IDs for controlled tests |
| email_jobs | ID, source email FK, pipeline version, state, attempts, next attempt, lease token/expiry, last safe error; unique(source email, pipeline version) |
| job_attempts | Attempt number, start/end, safe outcome, workflow/model/prompt versions and timing |
| extraction_results | Job/attempt FK, validated structured model output, model/prompt/input versions, preserved provenance |
| transaction_candidates | One or more events per email, normalized facts, validation issues, account mapping state, source evidence |
| review_items | Candidate/reason/status, revision, human correction and resolution history |
| account_mappings | Explicit bank/product/masked-account identifiers to configured logical accounts; Actual IDs added after bridge discovery |

Design constraints, indexes, retention, and limited payload access before implementation.
Attempted extraction is separate from transaction readiness. The job states are queued,
leased, retry_wait, completed and dead; completed means its extraction outcome was
persisted, not that a budget was updated. Candidate states include ready, needs_review,
ignored and duplicate_suspected. A source can produce zero or several candidates.

Use a dedicated processing login: SELECT only the needed receiver columns, limited
processing operations or vetted functions, no receiver updates, no schema ownership,
no role creation. n8n runtime credentials never gain administrator DDL rights.
Update backup scope and verification to include processing schema/history before storing
important state there. Current backup covers only imap_receiver and will not do this
without changes. Test empty install, repeat migrations, permissions, and restore.

## Step 3 — durable job discovery and optional notifications

Start with a scheduled reconciliation query and an activation cutoff recorded explicitly.
Queue only eligible captured emails after that boundary, with a unique source/version
constraint. Select existing stored samples explicitly for tests; do not automatically
reprocess historical IMAP mail or every existing database row on rollout. Use an
anti-join/unique insert, not MAX(UUID) or an increasing-primary-key assumption. UUIDs
are identifiers, not a reliable ordering/commit cursor. captured_at alone also does not
solve late-commit races; reconciliation must discover missing eligible jobs.

Optionally add NOTIFY from downstream job creation for faster worker wake-ups. Keep it
out of the receiver capture transaction: a full notification queue can fail a notifying
transaction, so even this optional dependency belongs downstream. Payload is an ID only,
never email content. Notifications accelerate discovery but are not the job store;
disconnected listeners need the reconciliation path to recover missed work. Keep a
periodic sweep even when event triggering works. If table-change triggers are used,
install them on processing tables and own them via migrations. Current n8n documentation
provides a Listen to Channel mode; verify the installed version can listen without needing
to create/drop triggers under its runtime login; otherwise retain polling initially.
Do not make capture depend on a downstream availability check or HTTP request.

Acceptance: one email creates one job for the selected version; repeated scheduling and
notifications add no duplicates; n8n downtime causes backlog, not missed emails. Model
or scheduler failure must not interrupt IMAP capture.

## Step 4 — atomic claiming, retries and recovery

Claim a small batch in one transaction using row locks with SKIP LOCKED, immediately
record a random lease token and expiry, then release the transaction. Call the model
outside SQL locks. Start with one worker and one concurrent model request; measure before
increasing either. Use conditional updates with the active token for completion, retry,
and heartbeat. An expired worker must not overwrite the result of a later claim.

Set bounded model/request deadlines and a lease longer than that deadline; renew safely
if needed. Persist result/candidates and completed status atomically. Recover expired
leases, back off temporary failures with bounded jitter, and move exhausted jobs into a
dead state with explicit operator retry. Keep failed attempts for audit. Manual replay
creates a versioned run and never silently overwrites approved results. Delivery is
at least once; unique constraints and conditional state changes make effects idempotent.

Acceptance: kill a worker before/after the model call and before/after saving. Work is
recoverable, stale completions are refused, and only one authoritative result wins.

## Step 5 — extraction input and output contract

Create a versioned normalizer that prefers plain text, safely reduces HTML when needed,
removes irrelevant boilerplate while retaining transaction evidence, and enforces size
limits. Never fetch remote email resources or execute embedded HTML. Treat all mail
content as untrusted data, including instructions aimed at the model. Preserve raw source
in the receiver and associate normalized input with its hash/version.

Skip/review capture failures and oversized mail instead of inventing missing content.
Attachment/PDF interpretation is deferred; attachment-only evidence is review-required.
Use a representative private sample set across the three banks and event types, including
non-transactions and tricky cases. Store only synthetic/redacted fixtures in Git.

Output contract: classification, transactions array, event kind (purchase, credit, refund,
transfer, repayment, cash withdrawal, loan payment, etc.), bank/product, masked account
identifier, amount as decimal text, explicit currency, direction, transaction date/time,
merchant/payee, bank reference when present, source evidence and unresolved fields.
Represent purchase/original currency and billed/account currency separately. Represent
transaction amount separately from balance, available credit and outstanding due.
Unknown means null/unknown, never a fabricated default. Model confidence alone is not
an import gate. Store model alias/version, prompt version, parser/schema version and
attempt linkage for every result. Bound invalid-JSON repairs; do not retry forever.

## Step 6 — deterministic validation and event handling

Validate output structure and evidence in application code. Parse money with decimal
arithmetic, then currency-aware minor units; never binary floating point or universal
paise assumptions. Validate dates/timezones, event direction, account identity, and
critical ambiguity. Do not mistake receipt time for a transaction date when evidence
conflicts. Unknown/multiple account matches always require review.

Classify OTPs, statements, promotions, payment reminders, declined attempts and balance-only
messages without creating financial candidates. Distinguish card authorizations from
settled activity; don't claim posting status unsupported by an alert. Detect repeated
transaction notices using references and evidence, while keeping legitimate same-amount
purchases distinct. Database source deduplication is not financial-event deduplication.

For overseas card purchases, an original foreign amount is insufficient to invent the
final INR charge. Preserve both amounts when present; otherwise mark unresolved billing
for review/later evidence. Loan repayments are expenses in v1. Own-account transfers
and credit-card repayments are correlated or flagged, not treated as two independent
expenses. Actual's eventual rules remain the intended category mechanism; Phase 2 must
not pretend the missing bridge/rules have already run.

Acceptance: each decision has explicit rule IDs/reasons and provenance. Build a regression
matrix from reviewed samples before declaring any bank/event type auto-import eligible.
Measure exact critical-field matches and false-ready decisions, not only valid JSON rate.

## Step 7 — durable review and learning from corrections

Persist reasons and proposed facts before notifying. Define a versioned review API contract
for the user's messaging app: review ID/revision, reason, safe summary, actions to correct,
approve, ignore or defer, authenticated callback, and stable action ID. The app can be
adapted but is not assumed ready. Persist review state independently of delivery, retry
notifications with idempotency, and reject repeated/stale callbacks. Store who/when/what
changed. No outbound messages are sent until the integration is explicitly authorized.
A local query/review export is an acceptable interim interface.

Corrections become reviewed examples and candidate parsing/mapping rules. Promote a
change only after regression tests across prior examples pass; record versions and allow
rollback. Do not silently fine-tune a model or generalize one correction to every bank.
A resolved review changes the specific candidate first, with broader changes explicit.

## Step 8 — n8n workflow assembly and validation

Workflow A: scheduled/event wake-up -> reconcile eligible jobs -> claim bounded work ->
normalize -> call local model -> validate -> atomically save outcome/review -> acknowledge.
Workflow B: sweep expired leases and due retries -> reclaim -> dispatch, with rate limits.
Workflow C (when approved): pending notification -> messaging API -> delivery result;
authenticated review callback -> validate revision/action -> persist decision.

Use SQL query parameters and stored secrets, sanitized workflow exports and safe errors.
Do not retain entire raw bank messages/model responses in routine n8n execution logs;
configure execution data retention deliberately and retain necessary evidence in protected
processing storage. PostgreSQL state determines progress, not n8n execution history.
Keep node types/options compatible with the installed version before exporting workflows.

## Step 9 — end-to-end acceptance and Phase 3 handoff

Test new valid/ambiguous/non-transaction emails; duplicate wake-ups and repeated alerts;
invalid JSON, unsupported currency, missing account, partial/oversized input; model/n8n/DB
outage; worker crash, lease expiry and stale completion; duplicate/stale review actions;
and backup/restore of both receiver and downstream state. Confirm original mail stays
unread and Phase 1 capture continues during downstream outages. No Actual credentials
or budget writes are needed for this acceptance.

Phase 2 is done when each selected email has one durable, auditable outcome, validated
candidates have complete evidence, ambiguous cases remain recoverable/reviewable, retries
survive restarts, and test evidence/workflow exports/runbook are current. Sample coverage
and unresolved cases must be stated honestly. The detailed acceptance threshold depends
on supplied samples; a handful of synthetic cases is not proof of bank-wide accuracy.

Phase 3 builds the Actual HTTP bridge using the official API client, discovers/matches
accounts, creates idempotent import jobs, handles transfer pairs and uncertain writes,
and applies Actual rules. There is currently no wrapper to call. Start with preview and
then controlled writes before enabling the user's requested automatic valid imports.

## Suggested delivery order

1. Processing schema, activation boundary and backup coverage.
2. Durable reconciliation/claim/retry functions plus failure tests, without a model.
3. Verify deployment endpoints and deliver a minimal n8n worker.
4. Gather sample mail and implement normalization/extraction contract/evaluation.
5. Deterministic validation, account mapping and duplicate/transfer checks.
6. Persistent review with a local inspection path, then messaging integration when ready.
7. End-to-end outage/replay tests, operator documentation and Phase 3 handoff.

## Technical references

- n8n Postgres Trigger: https://docs.n8n.io/integrations/builtin/trigger-nodes/n8n-nodes-base.postgrestrigger/
- n8n query parameters: https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.postgres/
- PostgreSQL 17 NOTIFY: https://www.postgresql.org/docs/17/sql-notify.html
- PostgreSQL 17 SELECT/locking: https://www.postgresql.org/docs/17/sql-select.html

These references support the trigger/SQL mechanics; the job schema, lifecycle, review
contract and delivery order above are project design proposals, not deployed features.
