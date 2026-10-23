# Phase 2.1 — durable Python ingest foundation

Status: implemented and tested in isolated Docker/PostgreSQL environments; not deployed
to the live fleet. Parent phase: **Phase 2 — Python ingest**. See [verification](VERIFICATION.md).

## Outcome and scope

Captured emails can be discovered, queued, claimed, retried and recovered without losing
work or accepting stale results. Source and processing state can be backed up and restored
together. Prove these properties with a fake processor before introducing a model.

“Ingest” here means consuming emails already captured in PostgreSQL. The existing
`imap-receiver` continues to own IMAP access, source persistence and unread-flag behaviour.

Included: Python service skeleton, schema/migrations, restricted roles, explicit activation,
scheduled discovery, attempts, leases, retries, fake outcomes, operator inspection,
combined backups and foundation acceptance tests.

Deferred: model calls and financial validation (2.2), human corrections and messaging
(2.3), full integrated acceptance and gradual live rollout (2.4), Actual writes (Phase 3).
Foundation crash/restore tests happen now; 2.4 repeats them with the complete pipeline.

## 2.1.1 — create the runnable service and isolated test environment

Build the Python package under `processing/`, with `pyproject.toml`, pinned
dependencies, Dockerfile, safe `.env.example`, CLI, database connection module and health
command. Match the existing receiver's file-mounted secret approach. Use PostgreSQL 17
for integration testing. Add a disposable Compose test stack with synthetic receiver rows
and no production volumes, credentials or network endpoints.

Start with psycopg and the test runner; do not add a model SDK, web API, Redis or Celery.
Provide one-shot commands for deterministic tests and long-running command modes for
discovery, worker and recovery. Keep worker concurrency at one by default, but exercise
multiple worker processes in tests. Configure bounded database connections and query times.

For later deployment, prefer joining the receiver's private local network when colocated.
If the node is remote, record private connectivity, firewall and TLS requirements before
deployment. No production port exposure or deployment is needed to complete local tests.

**Gate:** package/container builds; CLI and configuration checks run; the test database is
isolated; missing secrets fail safely; logs contain no passwords or email bodies.

## 2.1.2 — add the minimum durable schema and permissions

Create a separate `processing` schema with ordered, checksum-verified transactional
migrations and an explicit migration owner. Runtime startup checks compatibility but does
not perform privileged migrations automatically.

Implement only the foundation subset of the full architecture:

| Table | Required purpose |
|---|---|
| schema_migrations | Version/checksum history |
| pipeline_versions | Immutable processor/configuration identity and fake/real mode |
| processing_runs | Activation/sample scope, pipeline version and enabled state |
| run_mailbox_boundaries | Mailbox, committed UIDVALIDITY and last UID at activation |
| run_email_selections | Explicit source IDs for sample/test runs |
| email_jobs | Source/version uniqueness, state, due time, attempt allowance and lease |
| job_attempts | Append-only attempt identity, token, times, outcome and safe error code |
| job_results | One authoritative result per job, winning attempt, result kind and bounded payload |
| operator_actions | Activation, pause and bounded manual retry audit trail |

`job_results` is the minimal completion envelope added for this stage. Fake results use
`fake_success` or `fake_review_required` and cannot represent financially ready candidates.
Later stages add extraction/candidate/review tables and link them to this envelope.
Do not create speculative finance or messaging tables just to satisfy future stages.

Enforce `UNIQUE(email_id, pipeline_version)`, unique attempt numbers per job, unique result
per job, valid states, positive attempt allowances and coherent lease fields. Ensure a
result's winning attempt belongs to its job. Keep source FKs restrictive; no cascading
deletion of evidence. Index due jobs, expired leases and job attempts.

Use separate migration/admin, runtime and read-only inspection roles. Runtime reads only
the source identity/status/hash columns needed now; do not grant email bodies until 2.2.
Activation reads mailbox checkpoint columns. Runtime cannot update receiver tables or
perform DDL. Operator commands use an appropriately restricted operator role rather than
giving the worker activation/retry administration rights.

**Gate:** empty install and repeat migration succeed; checksum/schema drift is rejected;
constraints reject invalid records; allowed operations work and forbidden operations fail.

## 2.1.3 — extend backups before activating processing

Extend `imap-receiver/src/backup.py` and its tests to support a versioned combined archive
of `imap_receiver` and `processing` from one exported snapshot. Include both migration
ledgers, jobs, attempts, results, boundaries and audit rows. Preserve the current receiver
fingerprint contract because receiver migrations use it for drift detection.

Add a processing verifier and manifest version with schema definitions, row counts and
deterministic digests. Preserve verification of old receiver-only archives, clearly marking
their limited scope. Unknown layouts or incomplete archives must fail verification.
Validate source hashes and cross-schema references after disposable restore.

Reprovision roles/grants separately and test runtime access on the restored database;
schema archives do not recover cluster-level role passwords. Document protected off-host
copying, retention and secret recovery as production prerequisites. Do not mark production
recovery verified based only on a local disposable restore.

**Gate:** combined backup/restore works with empty and populated processing state, existing
receiver backup/migration tests still pass, and corrupt/incomplete archives are rejected.

## 2.1.4 — record activation and discover jobs

Implement explicit activation for selected initialized mailboxes and a pipeline version.
Record committed UIDVALIDITY/last-UID boundaries in a consistent read. Future eligibility
means matching mailbox/UIDVALIDITY and UID greater than that boundary. Receiver capture
saves emails and checkpoints atomically, so an in-flight capture remains discoverable
after it commits. Do not use email Date, `MAX(UUID)` or a permanent timestamp scan cursor.

Provide an explicit stored-email selection mode for synthetic/sample runs. It must not
alter the live boundary or fetch historical IMAP mail. Changed UIDVALIDITY pauses the
affected scope for explicit reconciliation; uninitialized mailboxes cannot be activated.

Reconcile missing jobs in bounded batches using conflict-safe insertion. Repeat complete
sweeps so late commits cannot be missed. Overlapping runs of the same version still yield
one job per source. Include parse-failed/oversized source records; the fake processor can
return a labelled synthetic review-required result without inspecting banking content.

**Gate:** repeated and concurrent scans add no duplicates; restart catches up; capture
spanning activation is included; prior captured rows are excluded unless explicitly selected.

## 2.1.5 — implement claims and atomic completion

Use job states `queued`, `leased`, `retry_wait`, `completed` and `dead`.
In a short transaction, lock a due job with `FOR UPDATE SKIP LOCKED`, verify allowance,
increment its attempt number, set a fresh token and expiry, and insert the attempt.
Commit before invoking the fake processor.

Completion locks the job and verifies current token/state and unexpired lease using
database wall time after lock acquisition. Insert the result, finish the attempt and
mark the job completed in one transaction. Ownership failure rolls back every result
write. Heartbeat and retry updates use the same ownership check; expired leases cannot
be revived even if another worker has not yet claimed the job.

Define a small processor interface: bounded source metadata and attempt context in;
a bounded outcome or typed failure out. It has no authority to write job state directly.
Persist fake mode in the pipeline identity and reject fake results from future import
eligibility. A later real processor uses a distinct version and explicit activation.

**Gate:** two workers cannot complete the same job; stale workers cannot save outcomes;
completion is all-or-nothing; repeated execution cannot produce duplicate authoritative
results. Lost commit acknowledgement is resolved by inspecting durable state.

## 2.1.6 — implement retry, recovery and operator controls

The recovery command locks expired jobs, marks their attempts abandoned, and sends them
to `retry_wait` or `dead` according to remaining allowance. Serialize this with completion.
Transient failures retry; permanent fake failures become dead with a safe reason.
Invalid runtime configuration pauses dispatch and reports an operational failure.

Initial configurable defaults: discovery every 60 seconds, recovery every 30 seconds,
100-row discovery batches, one active processor call, 120-second attempt deadline,
180-second lease, five claims including abandoned attempts, exponential full-jitter
backoff capped at 15 minutes with a 30-second base. Tests use shorter explicit settings
and synchronization barriers instead of waiting minutes or relying on timing luck.

Provide inspection of backlog, job history, expired claims and exhausted jobs; pause/resume
dispatch; and an audited retry command granting a bounded additional allowance with an
operator reason. Never erase attempts or reset completed jobs for a routine retry.
Stopping a process stops new claims and allows bounded active work to finish; unfinished
work recovers through lease expiry. On database loss, never claim success locally.

**Gate:** retries respect due times and allowance; recovery works with no processor running;
exhausted work remains inspectable; operator retries preserve history; shutdown is recoverable.

## 2.1.7 — prove crash recovery with the fake processor

Keep scenario controls confined to test configuration/synthetic fixtures; production email
content must never select crash hooks. Support success, review-required, transient failure
for the first N attempts, permanent failure, delay and process termination. Use subprocesses
for real worker kills and database integration tests for transaction behaviour.

| Scenario | Required result |
|---|---|
| Kill after claim, before processing | Attempt expires; next claim recovers it |
| Kill after processing, before save | Processing may repeat; one result wins |
| Kill during result transaction | Full rollback or full commit, never partial completion |
| Drop acknowledgement after commit | Inspection sees completion; no duplicate result |
| Old worker returns after expiry/reclaim | Completion, retry and heartbeat rejected |
| Two recovery processes race | One transition; no duplicate attempt accounting |
| Repeated transient failure | Backoff then success or bounded exhaustion |
| Restart discovery/worker/database | Persisted jobs resume without in-memory queue state |
| Duplicate source scans | Exactly one job per email/version |
| Processor unavailable | Capture continues; backlog remains durable |
| Restore queued/leased/retry/completed/dead jobs | State preserved; old workers fenced; leases recovered safely |
| Runtime permission attempt | Source updates, credential reads and DDL denied |

After restore, stop/revoke access for old workers before enabling the replacement,
invalidate restored leases through an audited operation, and reconcile missing jobs.
Run synthetic capture concurrently with worker failures and verify source persistence,
checkpoint progress and unchanged unread flags. A shared database outage affects capture
too; verify its recovery rather than claiming capture can continue without PostgreSQL.

**Gate:** the complete foundation suite passes with reproducible evidence. No model,
messaging or Actual service is needed.

## Deliverables and completion checklist

- [x] Runnable `processing` package/container and isolated PostgreSQL test stack.
- [x] Foundation migrations, privileges and compatibility checks.
- [x] Activation, sample selection and repeat-safe reconciliation.
- [x] Claim/complete/retry/recovery commands with durable attempts and fake results.
- [x] Inspection, pause and audited operator retry commands.
- [x] Combined backup format, backward-compatible verification and disposable restore proof.
- [x] Automated concurrency/crash/permission tests and receiver regression results.
- [x] Operator instructions, configuration defaults and recorded test evidence.

Implement in the order above. Steps 2.1.1–2.1.3 establish the safe storage foundation;
2.1.4–2.1.6 implement the job lifecycle; 2.1.7 proves it. Record actual test commands,
versions and results in the verification document. Live deployment prerequisites remain separate.

Phase 2.1 is complete when fake processing survives crashes and restores while preserving
one authoritative result per job and leaving capture unchanged. Handoff to 2.2 is the
tested processor interface, versioned outcome envelope and durable job infrastructure.
Model endpoint details and anonymized financial samples are needed for 2.2, not to start 2.1.
