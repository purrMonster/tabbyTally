# TabbyTally processing — runbook and verification record

Updated: **16 October 2026**, user timezone **Asia/Calcutta (IST, UTC+05:30)**.
This is the detailed operating and handoff record for `processing/`. Earlier capture
history remains in the [receiver runbook](../../imap-receiver/runbook.md).

This document records decisions, implementation, checks actually performed, operating
instructions, and known limits. It contains no live credentials, private email content
or real source IDs. Commands with uppercase IDs or local configuration paths require
operator-supplied values. Historical test results are not fresh live-service checks.

## 1. Current state and next step

**Phase 2.1 is implemented and tested in isolation. Phase 2.2 has a locally tested,
review-only extraction pilot; real-model and bank-format acceptance remain pending.**
Neither phase has been deployed or activated against the live receiver database.
There are no notifications or Actual Budget writes.

The original Phase 2.1 implementation record below is retained as history. Its fake-only
descriptions, nine-table inventory and original test counts describe that earlier stage.
For current Phase 2.2 behavior, limitations and operations, use
[section 13](#13-phase-22-verification-and-pilot-operation) and the
[verification ledger](VERIFICATION.md).

The later [Roastery integration record](#14-roastery-adapter-integration) supersedes the
initial model-connectivity assumptions in section 13.

| Area | Current evidence |
|---|---|
| Source capture | Existing independent Python receiver; Phase 1 live evidence is recorded in its own runbook |
| Processing application | Implemented in project-root `processing/`, replacing the preliminary `processing-node/` folder |
| Durable foundation | Activation, discovery, claims, attempts, fenced completion, retries, recovery and inspection implemented |
| Processor | Fake scenarios only; source metadata access, no body access |
| Storage | Separate `processing` schema in the same PostgreSQL database as source capture |
| Backup | New optional combined-schema format; existing receiver-only format still supported |
| Processing tests | 20 integration tests passed against isolated PostgreSQL 17.11 |
| Receiver regressions | All 41 tests passed, including database, role and migration opt-ins |
| Packaging | Production Docker image built and CLI help smoke test passed |
| Deployment configuration | Compose syntax validated with a placeholder external network and without secret-file resolution |
| Cleanup | Disposable processing test containers and network removed after verification |
| Live changes in this phase | None: no live schema migration, role provisioning, inbox access or activation |
| Publication | No commit, push or PR performed for this Phase 2.1 work in this conversation |

Next, the user can repeat the isolated tests in section 7. Before any live processing
activation, complete the deployment and backup gates in section 8. Phase 2.2 adds a real
local-model adapter and deterministic validation using the tested foundation.

The original documentation-only update did not rerun tests. The 16 October verification
does execute isolated tests and builds, as recorded in section 13.

### Navigation

- [Decisions and scope](#2-decisions-and-phase-boundaries)
- [Implementation chronology](#3-steps-taken-and-problems-resolved)
- [Files and schema](#4-artifact-and-data-dictionary)
- [Runtime semantics](#5-runtime-semantics-and-invariants)
- [Privileges and configuration](#6-roles-secrets-and-configuration)
- [Repeat the tests](#7-test-procedure-and-verification-ledger)
- [Deployment procedure](#8-controlled-deployment-procedure--not-yet-executed)
- [Daily operation](#9-command-reference-and-routine-operation)
- [Backup and recovery](#10-backup-restore-and-rollback)
- [Troubleshooting and limits](#11-troubleshooting-and-known-limits)
- [Next-session handoff](#12-handoff-and-open-work)

## 2. Decisions and phase boundaries

The earlier Phase 2 plan used n8n for downstream orchestration. The user asked whether
Python would be preferable, then requested an end-to-end Python plan and subsequently
authorized implementation of 2.1. Python was selected because the central requirements
are database transactions, retry semantics, financial validation and regression tests.
Those behaviours can be expressed and tested directly in one application.

This was a project-fit decision, not a claim that n8n cannot implement durable workflows.
n8n is no longer a dependency or a prerequisite for this processing service. PostgreSQL
holds authoritative state. No Redis or Celery queue was added.

The user named the parent phase **Phase 2 — Python ingest** and selected this breakdown:

| Stage | Agreed scope |
|---|---|
| 2.1 | Durable jobs, retries, crash recovery and backups, proven with a fake processor |
| 2.2 | Local-model extraction and deterministic financial validation |
| 2.3 | Review, corrections and messaging callbacks |
| 2.4 | Integrated failure/restore tests and gradual rollout |
| Phase 3 | Actual Budget writes and the required bridge/import recovery |

“Ingest” means consuming captured PostgreSQL emails. It does not replace IMAP capture.
The receiver remains responsible for mailbox credentials, read-only IMAP access, raw
source storage, UID identity and checkpoints. Processing receives no IMAP credentials.

Other decisions to preserve:

1. Use one database with separate schemas initially, allowing source foreign keys and
   one consistent backup snapshot. This also means a database outage affects both services.
2. Start with scheduled reconciliation and one active fake/model request. No notification
   trigger or downstream dependency was inserted into the capture transaction.
3. Use an explicit activation boundary. Do not automatically process all stored history.
4. Use at-least-once execution and one authoritative result per job. Do not promise
   exactly-once processor invocation or infer success from an in-memory queue.
5. A pipeline version identifies immutable configuration. Real extraction will need its
   own version and explicit scope; fake results cannot be promoted into real candidates.
6. Use distinct runtime, operator and inspection privileges. Migration and restore
   administration remain explicit operations with separate credentials.
7. Extend the existing backup system without changing the receiver fingerprint contract
   that receiver migrations already use for drift checks.
8. Implement only foundation tables now. Account mappings, financial candidates, review
   callbacks and notification outboxes are later migrations, not placeholder features.
9. Keep banking content and secrets local. Git fixtures and tests use synthetic data.
10. The preliminary folder was `processing-node/`; the user's implementation instruction
    selected `processing/`. Documentation links were updated and the empty old folder removed.

Financial requirements remain unchanged for later stages: HDFC/Axis/ICICI coverage must
be proven with samples; foreign original amounts must not imply an invented INR charge;
own-account transfers/card repayments need linking; loan payments are expenses for v1;
ambiguous facts need review; model confidence alone cannot authorize an import.

## 3. Steps taken and problems resolved

### 3.1 Planning and repository inspection

Inspected the existing receiver, initial SQL migration, capture transaction, role setup,
Compose network configuration, backup/restore code and tests. The receiver's PostgreSQL
service had no published port. The backup was receiver-only, and its fingerprint function
was reused by receiver migration checks. Those facts shaped the implementation.

Created the Python end-to-end documents, then the detailed Phase 2.1 plan. M0–M7 labels
were retained as an earlier detailed milestone mapping, with the user's 2.1–2.4 stages
now providing the top-level sequence. Documentation remains under `docs/processing/`.

### 3.2 Tooling check

The host `python` command resolved to the WindowsApps launcher and could not run in the
initial check. Docker CLI was installed, but the first sandboxed daemon query returned
permission denied. An approved Docker tool escalation succeeded; the local Linux engine
was then used for isolated builds and tests. No alternative host Python installation was
required. The approval was for the Docker operation, not a production deployment.

### 3.3 Foundation implementation

Added a Python package, SQL migration, database connector, migration runner, role
provisioner, activation/discovery logic, job state transitions, fake processor and CLI.
Added runtime/test Docker images, isolated test Compose, same-host deployment Compose,
safe example configuration and a repository-root Docker build exclusion file.

Implemented schema/database-only health checks, loop reconnection on database operational
errors, graceful stop signalling, bounded SQL operations and safe error-class logging.
Added an explicit restore-lease invalidation command and documented that old workers
must be stopped/fenced outside the command before it is used.

### 3.4 Backup implementation

Added `processing_backup.py` as a separate verifier. Added the `--include-processing`
option and manifest version 2 to the existing backup command. Version-1 receiver-only
verification remains available. Both schemas use one exported snapshot when combined.
The receiver's original structural/data fingerprint function was preserved.

### 3.5 Test-image correction

The first test image installed Debian's Python 3.11 into the PostgreSQL client image.
Package installation correctly rejected it because the new package declares Python
`>=3.12`. The image was changed to copy the Python runtime from
`python:3.14-slim-bookworm` into `postgres:17-bookworm`. This provided Python 3.14 alongside
PostgreSQL 17 client tools and matched the production processing runtime family.

The failed build did not run migrations against a live database. The corrected image
built successfully and subsequent suites ran inside the isolated Compose project.

### 3.6 Verification sequence

The initial suite contained 11 passing integration tests. It was expanded to 17 passing
tests covering additional save/crash windows, restore states, capture continuity and roles.
All 41 receiver regression tests then passed in a newly created disposable database.
Three further checks brought the processing suite to 20 passing tests: connection loss,
crash after fake processing but before save, and bounded fake timeout/backoff behaviour.

Built the final runtime image after permission and secret-handling refinements. The
`tabby-processing --help` smoke test passed. Validated deployment Compose with a placeholder
network and `--no-env-resolution`, checked document links and whitespace, and cleaned up
only the dedicated processing test containers/network. Built images were left available.

No live credentials were needed for these checks. No real model or messaging service was
contacted. Existing local source changes remained uncommitted; no publication was requested.

## 4. Artifact and data dictionary

All paths below are relative to the repository root. The workspace used in this session
was `C:\Users\jyotirmoyc\Desktop\Projects\tabbyTally`; older receiver history contains a
different workspace path and should not be copied as the current location.

| File | Responsibility |
|---|---|
| `processing/pyproject.toml` | Package `tabby-processing` 0.1.0, Python requirement, CLI entry point and psycopg dependency |
| `processing/src/tabby_processing/database.py` | Autocommit connections, dictionary rows, timeouts and exact-byte secret-file reading |
| `processing/src/tabby_processing/migrate.py` | Checksummed transactional migrations, structural drift check and runtime compatibility check |
| `processing/src/tabby_processing/migrations/001_foundation.sql` | Initial processing schema, constraints and indexes |
| `processing/src/tabby_processing/admin.py` | Explicit provisioning of three restricted group roles |
| `processing/src/tabby_processing/discovery.py` | Activation, reconciliation, pause/resume, operator retry, restore lease invalidation and audit |
| `processing/src/tabby_processing/jobs.py` | Claim ownership, completion, heartbeat, failure, backoff and recovery |
| `processing/src/tabby_processing/worker.py` | One fake processing attempt per call |
| `processing/src/tabby_processing/cli.py` | Commands, looping, signals, connection-error handling and safe JSON output |
| `processing/tests/test_foundation.py` | Twenty real-PostgreSQL foundation integration tests |
| `processing/tests/run_receiver.py` | Receiver regression harness using a newly created database |
| `processing/Dockerfile` | Non-root Python 3.14 application image |
| `processing/Dockerfile.test` | Python 3.14 plus PostgreSQL 17 tools for integration/restore testing |
| `processing/compose.test.yaml` | Dedicated disposable database and test container |
| `processing/compose.yaml` | Worker, discovery and recovery services on an existing same-host network |
| `processing/.env.example` | Placeholder libpq/file-secret configuration; not actual deployment values |
| `.dockerignore` | Excludes Git data, secrets, private environments, archives and common private source artifacts from root builds |
| `imap-receiver/src/backup.py` | Existing backup API extended for combined scope |
| `imap-receiver/src/processing_backup.py` | Processing layout and deterministic row verification |

### 4.1 Tables actually implemented

All nine tables are in `processing`; all have an `id` key. There are no candidate or review
tables yet. Most IDs are generated UUIDs; pipeline version IDs are text and migration IDs
are integers. Foreign keys use restrictive default deletion behaviour.

| Table | Fields and integrity responsibilities |
|---|---|
| `schema_migrations` | Integer ID, SQL SHA-256, recorded structural SHA-256 and application timestamp |
| `pipeline_versions` | Text ID, mode constrained to `fake`, JSON object config and creation time |
| `processing_runs` | Version FK, enabled flag, kind `live`/`sample`, creation time |
| `run_mailbox_boundaries` | Run FK, mailbox FK, captured UIDVALIDITY and last UID; unique run/mailbox |
| `run_email_selections` | Run FK and source email FK; unique run/email |
| `email_jobs` | Email/version/run FKs; state, attempt count/limit, due time, lease token/expiry, safe error, creation time; unique email/version |
| `job_attempts` | Job FK, positive attempt number, unique token, start/end, outcome/error; unique job/number and job/attempt ID pair |
| `job_results` | Unique job FK, winning attempt FK, fake result kind, JSON object payload up to 4096 bytes and creation time |
| `operator_actions` | Actor from database `session_user`, action, target, reason and timestamp |

Job constraints keep attempts nonnegative and no greater than the positive attempt limit.
Leased jobs require both lease fields; other states require neither. Attempt finish time
and outcome are either both absent or both present. The result's composite FK ensures its
winning attempt belongs to that job. There can be at most one result row per job.

Indexes support state/due-time lookup and leased-job expiry lookup. Unique constraints
provide the source/version and attempt identities. There is no financial deduplication
index, since no financial events are extracted in this stage.

### 4.2 What “immutable” means in this release

The activation API refuses to reuse a pipeline version with different config. Runtime
roles do not have UPDATE on pipeline versions or existing results. Old attempts are
retained, but their finish/outcome fields are updated as an attempt concludes.

The worker role has direct INSERT/UPDATE privileges on jobs/attempts. Lease fencing and
transition rules are enforced by application transactions, not database transition
functions or row-level security. Treat that credential as a trusted service credential;
the schema does not protect against arbitrary hostile SQL from a compromised worker.
An administrator can also modify records. Do not describe audit/history as tamper-proof.

### 4.3 Migration and runtime compatibility behaviour

The runner loads ordered SQL files packaged with the application, requires contiguous
numeric IDs and computes normalized-text SHA-256 checksums. It serializes migration
inspection/application with advisory transaction lock `734293` and checks existing ledger
IDs/checksums plus the recorded structure before applying pending files. Migration SQL
and new ledger entries commit together. Changed history, an empty existing ledger or
unsupported future history fails closed.

The structure digest covers table columns/types/defaults/nullability, constraints and
indexes. It is not a full cluster security/configuration fingerprint. The combined backup
verifier separately rejects unsupported processing object layouts/functions/triggers.
Future migration authors must extend both checks when introducing new object types.

Unlike the receiver's baseline adoption workflow, processing has no `--adopt-existing`
option. A manually created partial/unversioned processing schema requires investigation;
do not drop it or manufacture ledger entries to bypass a migration error.

`status` takes the same advisory transaction lock and performs history/structure checks,
but does not apply pending files. Runtime `compatible` compares packaged SQL IDs/checksums
to the ledger; it does not repeat the full structural scan on every loop. Therefore a
green `health` is not a substitute for admin drift inspection. Normal runtime startup
never executes migrations or provisions roles.

## 5. Runtime semantics and invariants

### 5.1 Activation

`activate` requires either one or more `--mailbox` values or one or more `--email` values,
never both and never neither. It opens a repeatable-read transaction, creates or checks
the pipeline config, creates a run, records the selection and appends an audit entry.

Mailbox activation requires a stored initialized checkpoint. It records the committed
UIDVALIDITY and last UID. Eligible sources have the same mailbox/generation and a higher
UID. This is a boundary in captured state, not the sender Date header or IMAP receipt time.

Because the receiver writes emails and its checkpoint in the same transaction, a capture
transaction still in progress at activation is outside the committed boundary and becomes
eligible after commit. Already committed sources are excluded unless selected explicitly.
No new IMAP fetch or historic mailbox import occurs during activation.

Sample activation references existing stored email IDs. Source FKs reject unknown IDs.
Repeated source/version scopes do not create repeated jobs, even if different run IDs
were created. Activation itself is audited but is not a repeat-safe request-ID API: a
repeated activation can create another run record. Prefer recording and reusing the run ID.

### 5.2 Discovery

Reconciliation selects eligible rows missing a job, inserts at most 100 by default, and
uses conflict handling for concurrent scanners. It repeatedly starts from the fixed scope;
no permanent UUID or timestamp high-water mark can hide a late commit. The Python function
accepts limits 1–1000, but the current CLI does not expose a batch-size flag.

If current mailbox UIDVALIDITY differs from a boundary, that mailbox branch is excluded.
The returned `uidvalidity_mismatches` counts distinct enabled runs with mismatches, not
emails. It does not persist `enabled=false`, reset receiver checkpoints or disable other
matching mailboxes in the run. Already queued jobs are not automatically cancelled.
The operator must investigate and choose a new scope/version deliberately.

A job retains its originating run. Repeating activation for the same source/version does
not reassign old jobs to a later run. If the original run is paused, resume it rather than
expecting a new overlapping run to release its old jobs.

### 5.3 Claims and completion

```text
queued ────────────────────────> leased ─────────> completed
retry_wait (due) ───────────────> leased ─────────> retry_wait
                                   └────────────> dead
leased (expired) ───────────────> retry_wait or dead
dead ── audited bounded retry ──> queued
```

Claiming uses a short row-locking transaction with `FOR UPDATE SKIP LOCKED`. It selects
an enabled run's due job, verifies remaining allowance, increments attempts, assigns a
fresh token/expiry and creates the attempt. Processing occurs after that transaction ends.

Completion locks the job and checks its current state/token and expiry using database
wall time read after lock acquisition. The result insert, attempt completion and job
completion occur in one transaction. A failed ownership check leaves no authoritative
result. Heartbeat and failure updates use the same fence. An expired token cannot revive
itself just because recovery has not yet run.

`completed` means a durable fake outcome exists. It does not mean a financial transaction
is ready, posted or imported. After an uncertain connection response, inspect the job
and result before deciding whether another execution is needed.

### 5.4 Fake scenarios

| Scenario | Behaviour |
|---|---|
| `success` | Stores `fake_success` for captured metadata; failed/oversized capture instead produces fake review-required |
| `review` | Stores `fake_review_required`; no real review item or notification is created |
| `transient` | Fails through the configured attempt threshold, then succeeds subject to capture status |
| `permanent` | Finishes the attempt as permanent and marks the job dead immediately |
| `delay` | Sleeps for a bounded configured delay; reaching the deadline produces a transient failure |

The worker stores only `{"synthetic": true}` as its result payload. Configured delay is
applied before the scenario branch, so it can be combined with any scenario. Allowed delay
is 0–120 seconds; the activation function accepts a failures setting from 0–100. CLI defaults
include scenario `success`, failures `1`, delay `0`. Reusing a version compares the complete
stored JSON object, including those keys; API and CLI callers should provide identical config.

No crash scenario can be selected by an email or CLI flag. Tests terminate subprocesses
or replace a function inside the disposable test process to open specific crash windows.
The fake worker does not read source bodies or execute instructions from messages.

### 5.5 Retry and shutdown

Temporary failures schedule full-jitter backoff between zero and
`min(900, 30 × 2^(attempt−1))` seconds, with the exponent capped internally. Five claims
are allowed initially; abandoned claims count. Permanent failures or exhausted budgets
become dead. Dead jobs retain evidence/history and require an operator action to retry.

Recovery locks expired leases, marks unfinished attempts abandoned, clears ownership,
and schedules retry or death. Two recovery processes serialize safely on those rows.
Recovery does not require an available processor and runs even for paused runs.

Operator retry applies only to dead jobs and accepts an additional allowance of 1–10.
It sets the new limit to current attempts plus allowance, queues the job immediately and
records a reason. It does not reset attempt count, erase results/history, or requeue a
completed job.

SIGTERM/SIGINT stops further loop iterations. Active work can finish within its current
bounded execution; sleep is not interrupted by the stop event. Compose gives 130 seconds
before forced termination. If killed first, the lease is recovered later. Lease validity
comes from database time; there is no dependency on matching host clocks for ownership.

## 6. Roles, secrets and configuration

### 6.1 Role matrix

`provision` creates NOLOGIN group roles when absent. It does not generate passwords,
create deployment LOGIN users or grant database CONNECT to those users. Existing group
roles with elevated attributes, memberships or ownership are rejected for manual review.
Grants are transactional. Some inherited/public access is checked and rejected.

| Capability | Runtime | Operator | Inspector |
|---|---|---|---|
| Read processing tables | Yes | Yes | Yes |
| Read selected source metadata | Yes | Yes | Yes |
| Read email bodies/raw MIME/account credentials | No | No | No |
| Insert/update jobs and attempts | Yes | Only selected job columns for retry | No |
| Insert results | Yes | No | No |
| Activate pipelines/runs/selections | No | Yes | No |
| Pause/resume runs | No | Yes | No |
| Append operator audit | No | Yes | No |
| Delete history/source rows or perform schema DDL | No | No | No |

Source email SELECT columns: `id`, `mailbox_id`, `uid_validity`, `uid`, `capture_status`,
`raw_sha256`. Mailbox SELECT columns: `id`, `uid_validity`, `last_uid`, `initialized_at`.
No general receiver table SELECT is granted. Admin commands require the separate
migration/role owner or sufficiently privileged administrator.

Provision separate local login users, grant the appropriate group membership, and check
effective inherited permissions and database CONNECT under those actual logins. The
automated permission tests use `SET ROLE`; they do not prove deployment password
authentication, TLS, pg_hba rules or an arbitrary login's membership configuration.

### 6.2 Configuration values and defaults

| Setting | Current implementation |
|---|---|
| Python runtime | Docker Python 3.14; package minimum >=3.12 |
| PostgreSQL | 17-series image; test server reported 17.11 |
| Driver | `psycopg[binary]==3.3.3` |
| Build backend | `setuptools>=77,<83`; image tags/build backend are not immutable digest pins |
| DB address/identity | libpq `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` |
| Password file | `PGPASSWORD_FILE`, read as exact UTF-8 bytes without stripping newline/whitespace |
| TLS | libpq settings such as `PGSSLMODE=verify-full`, `PGSSLROOTCERT` for remote deployment |
| Connection timeout | 10 seconds |
| Statement / lock timeout | 15 seconds / 5 seconds per connection |
| Discovery / worker / recovery loop delay | 60 / 1 / 30 seconds; `--interval` overrides per command |
| Lease / fake-processing deadline | 180 / 120 seconds; work flags can override |
| Initial attempt allowance | 5, stored per job; no activation CLI override |
| Discovery / recovery batch | 100 per invocation; function parameters exist, CLI flags do not |
| Worker concurrency | One attempt at a time per worker process |
| Container resources | 256 MiB and 0.5 CPU per service in deployment Compose |
| Health check | Every 30 seconds, 20-second timeout, 3 retries |
| Restart / stop grace | `unless-stopped` / 130 seconds |

Each loop iteration opens/closes a connection; processing does not use a persistent
connection pool. Three service processes plus health probes can connect independently.
Loop intervals are delays after an iteration, not precise wall-clock schedules.

The fake deadline bounds its simulated sleep; it is not a general hard deadline around
all database operations and arbitrary future model code. The real adapter in 2.2 must
enforce network and whole-attempt limits explicitly. Heartbeat exists as a library
operation but is not periodically invoked by the current fake worker.

### 6.3 Secret and network handling

`processing/.env.example` uses placeholders; notably its database name is not a discovered
live database. The prior receiver runbook recorded a different database name. Copy the
actual intended deployment values locally instead of assuming the example is correct.

Store the worker secret in `processing/secrets/processing_db_password.txt`; mount path
is `/run/secrets/processing_db_password`. Keep `.env`, secrets and private backup files
outside Git. These mounted files are local plaintext storage, not an encrypted vault.

The supplied Compose uses an externally existing Docker network specified by
`RECEIVER_NETWORK`. An external same-host Docker bridge is not a cross-host fleet network.
A remote node needs a separate private database endpoint, firewall/pg_hba policy and TLS
deployment. An ordinary HTTP Traefik router cannot supply PostgreSQL connectivity.

The processing image contains no PostgreSQL client backup tools or automatic migration
entrypoint. The receiver maintenance image remains the backup tool boundary.

## 7. Test procedure and verification ledger

### 7.1 Repeat the complete isolated checks

Open PowerShell with Docker Desktop's Linux engine running. No production `.env`, model
endpoint or mailbox secret is required. Initial builds may download public images/packages.

```powershell
Set-Location 'C:\Users\jyotirmoyc\Desktop\Projects\tabbyTally'

docker compose -f processing/compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests --attach tests
if ($LASTEXITCODE -ne 0) { throw 'Processing suite failed; inspect output before continuing.' }

docker compose -f processing/compose.test.yaml run --rm --entrypoint python tests /app/processing/tests/run_receiver.py
if ($LASTEXITCODE -ne 0) { throw 'Receiver regression suite failed; inspect output.' }

docker compose -f processing/compose.test.yaml down
```

Expected processing footer: `Ran 20 tests`, `OK`, exit code 0. Expected receiver footer:
`Ran 41 tests`, `OK`, exit code 0. The receiver command may start the disposable DB again
because the first command stops its services on test-container exit.

If a test fails, record the test name and safe error class. Do not treat container startup
alone as success. Inspect test-only logs, then run the same `down` command when finished.
Do not substitute a production Compose file or database environment for this test stack.

The test project name is `tabbytally-processing-test`. PostgreSQL has no published host
port or production mount. It stores data in tmpfs and uses a deliberately disposable test
password from the test file. Individual tests create randomly named databases and clean
them up. This stack is not suitable for keeping real state across container restarts.

### 7.2 Optional build/CLI checks

```powershell
docker build -f processing/Dockerfile -t tabbytally-processing .
if ($LASTEXITCODE -ne 0) { throw 'Runtime image build failed.' }
docker run --rm tabbytally-processing --help
```

The help output should list migrate/status/provision/health/inspect, activation,
pause/resume/retry/history, discovery/work/recovery and restore-lease invalidation.
This command does not connect to PostgreSQL.

Compose configuration can be checked separately with a placeholder network:

```powershell
$env:RECEIVER_NETWORK = 'test-network-placeholder'
docker compose -f processing/compose.yaml config --no-env-resolution --quiet
```

That checks syntax/interpolation only. It neither creates the network nor proves that a
real `.env`, mounted secret or database login works. Replace the placeholder before real
deployment and do not leave it as the intended network configuration.

### 7.3 Processing tests and what each establishes

| Test | Observed result / scope |
|---|---|
| `test_migrations_and_drift` | Repeat migration and compatibility work; an added column causes drift rejection |
| `test_checksum_rejected` | Tampered history is rejected by migration and runtime compatibility checks |
| `test_discovery_activation_late_commit` | Pre-boundary source excluded; uncommitted capture discovered after commit; repeat adds zero; generation mismatch reported |
| `test_concurrent_discovery_and_claim` | Concurrent scans/claims produce one active owner |
| `test_completion_atomic_and_stale` | Invalid result rolls back; expired completion/heartbeat/failure rejected; replacement attempt wins once |
| `test_retries_exhaustion_operator_pause` | Pause prevents claim; resume works; five failures exhaust; audited retry allows another attempt |
| `test_fake_processor` | Transient first attempt then fake review-required outcome for oversized fixture |
| `test_permissions` | Runtime can process metadata; source writes, body/credential reads, DDL, run updates and history deletion denied |
| `test_process_crash_and_recovery` | Subprocess killed after claim; expired work recovers and completes |
| `test_commit_acknowledgement_lost` | Completion remains authoritative when inspected through a new connection |
| `test_combined_backup_restore` | Populated combined archive restored, fingerprints matched and disposable database removed |
| `test_capture_continues_with_failed_processing` | Synthetic capture persists source/checkpoint and unread state; subsequent permanent processing failure changes no source row |
| `test_crash_during_save_rolls_back` | Killed process with an open outer save transaction leaves no partial result; later recovery succeeds |
| `test_concurrent_recovery_and_post_reclaim_fence` | Racing recoverers make one transition; old token operations rejected after new claim |
| `test_restore_all_states_and_runtime_permissions` | Five job states survive restore; roles reprovision; restored lease invalidation/recovery and stale-token rejection work |
| `test_empty_backup_and_corruption` | Empty combined state restores; tampered archive rejected |
| `test_operator_and_inspector_roles` | Operator activation/pause works; inspector can read audit and cannot resume |
| `test_connection_loss_preserves_claim` | Backend connection termination does not create local-only success; reconnect/recovery completes |
| `test_crash_after_fake_processing_before_save` | Process killed at completion boundary leaves recoverable work and one eventual result |
| `test_backoff_and_bounded_fake_timeout` | Retry delays bounded; simulated work timeout retries; future-due job not claimed |

### 7.4 Receiver regressions and interpretation limits

The regression harness creates a separate database, applies receiver migrations,
provisions its runtime role with a temporary synthetic secret, and enables
`RUN_DB_TESTS`, `RUN_ROLE_TESTS` and `RUN_MIGRATION_TESTS`. All 41 tests passed. This
includes the eight existing backup tests, parsing/capture/permissions, health/supervision,
setup and receiver migration checks. The harness drops its database afterward.

Limits of the recorded evidence:

- The lost-ack test commits then reconnects; it does not drop a real network packet at
  the exact commit acknowledgement boundary.
- The database-outage test terminates a connection. No postmaster restart, host-loss,
  power-loss or physical disk corruption exercise was performed.
- Capture uses a synthetic IMAP implementation. Its test is not a concurrent live-inbox
  soak test or a second verification of Purelymail credentials.
- Role tests use `SET ROLE`; real LOGIN authentication and remote TLS remain deployment checks.
- Restore tests use the test image's PostgreSQL tools and Python 3.14. The modified
  receiver maintenance image's distinct Debian Python/psycopg runtime was not rebuilt
  and re-exercised for this Phase 2.1 session; do that before live backup rollout.
- Twenty passing tests establish the covered foundation behaviours, not arbitrary load,
  multi-node performance, future model correctness or production disaster recovery.

## 8. Controlled deployment procedure — not yet executed

These are future operator steps, not a record that deployment occurred. Use the
[processing README](../../processing/README.md) alongside this procedure.

1. **Confirm the destination.** Inspect the intended receiver database, schema version,
   database/network names and maintenance access. Keep one live inbox; a second is not
   a prerequisite. Choose same-host placement or prepare an explicit remote topology.
2. **Back up the existing receiver.** Use the already established maintenance procedure
   before adding a new schema. Verify restore without restoring over live state.
3. **Build the application.** Run the image build from the repository root. The supplied
   Docker build context is the repository root, not `processing/` alone.
4. **Prepare local configuration.** Copy the example into a private `processing/.env`;
   set the real database name/host/user and mounted password path. Set the actual
   `RECEIVER_NETWORK` for Compose interpolation. Do not print secret values.
5. **Apply processing schema as administrator.** Invoke `tabby-processing migrate`, then
   `status`, from a temporary container or installed package on the private network using
   a separately configured administrative connection. Runtime services must not receive
   that connection. No processing-specific Compose admin service is supplied.
6. **Provision group roles and local LOGIN identities.** Run `provision` as the appropriate
   administrator. Create credential-backed login roles locally with only the intended group
   membership. Validate CONNECT, inheritance and negative permissions under each login.
7. **Rebuild backup support.** Rebuild the receiver's maintenance image with the new source.
   Create a combined archive with `--include-processing --verify`. Confirm manifest version
   2 and a successful verification record. Update any real schedule to use that option.
8. **Start with explicit sample scope.** Use the operator connection to activate selected
   stored email IDs under a fake version. Run discovery, work and recovery once; inspect
   the returned IDs, attempts and fake outcomes before enabling loops.
9. **Activate a live-source boundary only deliberately.** Record run/version and selected
   initialized mailbox IDs. Future captured emails may now receive fake results; this
   still does not enable banking interpretation or imports.
10. **Start the three restricted services.** Use the runtime login for worker, discovery
    and recovery. Inspect container status, backlog and failed attempts. Keep admin and
    operator credentials out of those services.
11. **Record deployment evidence.** Record versions, configuration without secrets, boundary
    IDs locally, positive/negative login checks, combined backup verification and receiver
    health. Do not mark live deployment complete based on this document alone.

From the repository root, after local configuration exists:

```powershell
docker compose --env-file processing/.env -f processing/compose.yaml up -d --build
docker compose --env-file processing/.env -f processing/compose.yaml ps
docker compose --env-file processing/.env -f processing/compose.yaml logs --tail 100 worker discovery recovery
```

The Compose `env_file` supplies container variables; `--env-file` also supplies variables
needed to interpolate Compose itself. The runtime services cannot activate or migrate.
Do not run administrator commands through `exec worker` expecting its restricted login
to become an administrator.

## 9. Command reference and routine operation

The examples below assume the CLI is installed/in a container with the appropriate
database credentials. They are command templates, not commands already executed live.

| Command | Role / effect |
|---|---|
| `migrate` | Admin; apply pending processing SQL and ledger in a transaction |
| `status` | Admin-oriented schema inspection; checks history and structural fingerprint without applying pending migrations |
| `provision` | Admin; create/check restricted group roles and apply grants |
| `activate --version V --email ID --reason TEXT` | Operator; explicit stored-email sample run; repeat `--email` for more IDs |
| `activate --version V --mailbox ID --reason TEXT` | Operator; record future captured-source boundary; repeat `--mailbox` as needed |
| `discover [--loop --interval N]` | Runtime; create missing eligible jobs |
| `work [--loop --interval N] [--lease-seconds N --deadline N]` | Runtime; claim and process one attempt per iteration |
| `recover [--loop --interval N]` | Runtime; recover expired leases |
| `inspect` | Inspector or broader; job counts and oldest creation time per state |
| `history JOB_UUID` | Inspector or broader; job row and ordered attempts |
| `pause RUN_UUID --reason TEXT` | Operator; disable future discovery/claiming from that run |
| `resume RUN_UUID --reason TEXT` | Operator; re-enable the run |
| `retry JOB_UUID --allowance N --reason TEXT` | Operator; grant 1–10 additional attempts to a dead job |
| `health` | Inspector or broader; schema compatibility and DB readiness only |
| `invalidate-restored-leases --old-workers-fenced --reason TEXT` | Admin; expire all current leases with an audit entry |

Audit reasons must be nonempty and no longer than 500 characters. Use reasons useful for
operations without embedding private message content. Audit actor is the authenticated
session user, not necessarily the group selected by `SET ROLE`.

An example sample run:

```text
tabby-processing activate --version fake-sample-v1 --email EMAIL_UUID --scenario transient --failures 1 --reason "foundation sample"
tabby-processing discover
tabby-processing work
tabby-processing inspect
tabby-processing history JOB_UUID
```

The first attempt retries. Wait for its recorded due time before expecting the next work
command to claim it. `--failures 1` does not mean “fail once on every invocation”; the
scenario compares against the persistent claim count. An oversized/parse-failed source
eventually produces fake review-required even after transient failures end.

Pause prevents new dispatch, but it neither cancels a processor already running nor
provides an instantaneous drain barrier against an already-started claim transaction.
For maintenance requiring no writes, stop services and verify active work is gone.

Example read-only SQL for an inspector, through an already authenticated private session:

```sql
SELECT state, count(*) AS jobs, min(created_at) AS oldest
FROM processing.email_jobs GROUP BY state ORDER BY state;

SELECT id, attempts, attempt_limit, due_at, last_error
FROM processing.email_jobs WHERE state IN ('retry_wait', 'dead')
ORDER BY due_at LIMIT 50;

SELECT id, lease_expires_at
FROM processing.email_jobs
WHERE state = 'leased' AND lease_expires_at <= clock_timestamp();

SELECT job_id, kind, created_at FROM processing.job_results
ORDER BY created_at DESC LIMIT 20;
```

These queries expose processing IDs/status, not raw email content. `history` includes lease
tokens, so keep its output in trusted operational channels. There is no standalone command
to list open reviews, approve a candidate or import to Actual in this release.

### 9.1 Interpreting CLI output

| Output shape | Meaning |
|---|---|
| `{"applied": 1, "available": 1}` | Current installed/packaged migration count; not a claim that this invocation changed one migration |
| `{"provisioned": true}` | Group-role provisioning transaction succeeded; LOGIN users/secrets still separate |
| `{"run_id": "..."}` | Activation committed; save the run ID locally |
| `{"inserted": N, "uidvalidity_mismatches": M}` | Reconciliation counts; inspect mismatch scopes if nonzero |
| `{"claimed": false}` | No eligible due job was claimed |
| `{"claimed": true, "job_id": "..."}` | An attempt was claimed and handled; it may have completed, retried or become dead |
| `{"job_id": "...", "outcome": "lost_lease"}` | Ownership was lost; this worker did not authoritatively finish it |
| `{"recovered": N}` | N expired leases transitioned during this recovery pass |
| `{"updated": true}` | Requested operator mutation committed |
| `{"invalidated": N}` | N restored leases expired by the administrator's explicit operation |
| `{"database_ready": true, "processor": "fake"}` | Connection and packaged-ledger compatibility succeeded |
| `{"event": "processing_error", "error_class": "..."}` | Safe exception classification; no SQL/credential details printed |

The examples show output shapes, not actual current IDs or state. Use `history` and the
stored result for outcome truth rather than treating `claimed: true` as processing success.
Non-loop successful commands return zero; handled operational/configuration failures
return nonzero unless a loop is retrying an operational connection failure. Argument
parser errors are separate CLI usage failures. These JSON events do not constitute a
persisted event-log stream; durable history lives in PostgreSQL.

## 10. Backup, restore and rollback

### 10.1 Create and verify

From `imap-receiver/`, after rebuilding the maintenance image:

```powershell
docker compose --profile maintenance build backup
docker compose --profile maintenance run --rm backup create --include-processing --verify
docker compose --profile maintenance run --rm backup verify ARCHIVE_BASENAME
```

The create command opens a repeatable-read/read-only transaction, computes source and
processing fingerprints, exports the snapshot and passes it to a custom-format `pg_dump`
of both schemas while the snapshot transaction remains open. It writes an archive digest
and manifest after the archive completes. Interrupted partial files are not verified backups.

| Format | Scope |
|---|---|
| Manifest version 1 | `imap_receiver schema`; old receiver-only archives |
| Manifest version 2 | `imap_receiver + processing`; both schemas and migration histories |

The archive filename still begins `receiver_` even for combined backups. Inspect manifest
scope/version, not the filename alone. `create` without `--include-processing` still
creates a valid receiver-only archive; it does not auto-detect processing or warn that
processing state is omitted. Updating the actual backup command/schedule is mandatory.

Verification checks archive identity/hash, creates a fresh random `imap_restorecheck_...`
database, revokes PUBLIC connect, restores without original ownership/grants in one
transaction, compares fingerprints and cleans up the generated database. It will not
restore into an operator-supplied live target. A verification report is written only after
matching data and successful cleanup.

The processing verifier expects exactly the nine supported tables and checks their
columns, defaults, constraints, indexes and complete ordered row digests. Unknown layouts,
processing functions and non-internal triggers are rejected rather than silently ignored.
Later schema changes must update verifier coverage. Receiver raw-source hashes are also
checked. Foreign keys are restored and enforce source/attempt references.

Archives contain private raw emails and state; compression does not encrypt them. Neither
format backs up LOGIN passwords, cluster roles, pg_hba, Docker configuration, mounted
secrets or external message delivery. Protect archive/manifest/report access and arrange
off-host copies, retention and recovery objectives separately.

### 10.2 Recover a replacement deployment

1. Stop old processing services and fence their credentials/network access. Stop any
   competing receiver authority as appropriate to the recovery plan. A restored database
   must not coexist with another active processing authority for the same sources.
2. Restore a trusted combined archive into an isolated replacement database, preserving
   source and processing state from the same snapshot. Check digests and schema history.
3. Recreate role/login configuration and secrets separately. Run permission tests under
   intended credentials. Confirm application/schema compatibility before dispatch.
4. Record that old workers are fenced, then run the admin operation below. It expires
   restored leases atomically and records the operator reason.
5. Run recovery with the runtime connection. Old attempts become abandoned; exhausted
   jobs remain dead; completed jobs/results stay completed.
6. Reconcile missing eligible jobs. Resume workers only after checking source boundaries,
   remaining allowance, due times and receiver checkpoint recovery.
7. Coordinate receiver catch-up. Mail removed from IMAP since the archive is not magically
   recovered; use retained sources or a separate recovery source if required.
8. Create/verify a fresh combined archive and record replacement deployment evidence.

```text
tabby-processing invalidate-restored-leases --old-workers-fenced --reason "verified replacement restore"
tabby-processing recover
tabby-processing discover
```

`--old-workers-fenced` is a required assertion by the operator. The tool does not terminate
external workers, revoke logins or inspect another host. No user-facing callback system
exists yet; 2.3 will add callback replay/epoch handling to this recovery procedure.

### 10.3 Roll back a processing release

Pause/stop dispatch, retain all source/jobs/history, and deploy a schema-compatible prior
application. Runtime checksum compatibility will reject a mismatched ledger. Prefer a
forward fix for incompatible schema changes; there is no automatic down-migration command.

Do not overwrite the live database with an old archive merely to revert application code:
that can discard newer captures. Do not change old pipeline configs or delete successful
results to simulate a retry. Scope any replacement version explicitly. Receiver operation
is independent unless shared database access/resources are affected.

## 11. Troubleshooting and known limits

| Symptom | Interpretation and next check |
|---|---|
| Docker daemon permission/connection error | Check Desktop Linux engine availability and execution permissions; this is not a job failure |
| Host `python` cannot run | Use supplied Docker commands; host Python was not required for verification |
| Python version rejected at build | Use current Dockerfile.test; the initial Debian 3.11 test recipe was replaced |
| `RECEIVER_NETWORK` interpolation error | Set the real same-host network; placeholder syntax validation did not create one |
| Missing `.env` or secret file | Provision local deployment files; test Compose intentionally does not need them |
| `processing_error` / `OperationalError` | Check private DB reachability and service status; loops retry connection errors |
| `ValueError` during migrate/status | Inspect checksum/history, schema drift, unknown layout or configuration in a trusted admin session |
| `InsufficientPrivilege` | Confirm command is being run with the intended admin/operator/runtime role; do not give worker admin rights |
| `inserted: 0` | May mean no eligible new mail, existing jobs, paused run or wrong scope; inspect boundaries/status |
| Nonzero `uidvalidity_mismatches` | Investigate mailbox generation and explicit scope; do not reset capture history automatically |
| `claimed: false` | No enabled due job with allowance; check run state, due time, existing lease and exhaustion |
| Expired leased jobs remain | Recovery loop may be stopped or unable to connect; inspect it and run recovery once |
| `lost_lease` outcome | Worker no longer owns the job; inspect replacement attempt rather than force-completing the old token |
| Job is dead | Inspect attempts/error, correct cause and grant a bounded audited retry if appropriate |
| Fake review-required result | Source capture failure or fake review scenario; no actual review UI exists yet |
| Container healthy but backlog grows | Health is compatibility/connectivity only; inspect loops, due jobs and attempt progress |
| Backup lacks processing | Require version-2 manifest and `--include-processing`; a version-1 success is insufficient |
| Backup rejects unknown layout | Update the versioned verifier with the migration; do not disable verification |
| Restore cleanup failed | Inspect the exact generated disposable DB name; never issue broad database cleanup |

Additional implementation limits relevant before unattended deployment:

- No persisted worker-progress heartbeat, automatic backlog alerts, notification channel,
  retention sweeper or dead-job dashboard exists. CLI/SQL inspection supplies visibility.
- Non-operational configuration/programming errors exit the process. Docker's restart
  policy may restart it repeatedly; that is not a persisted pipeline quarantine state.
- SQL/query parameters are not printed by application errors, but PostgreSQL server
  logging is separate. Review statement/error detail logging before financial content
  arrives in 2.2. Do not paste database logs with private row details into public reports.
- Provisioning validates specific role hazards and source privileges; it is not a full
  audit of arbitrary cluster-wide grants, custom functions, LOGIN memberships or PUBLIC
  permissions in every schema. Test the actual deployment identities.
- Source/version uniqueness does not deduplicate financial events across different emails.
- Fake deadline, schema-readiness health and manual role provisioning are deliberate
  foundation limits. They must not be described as a production model/review platform.
- Docker image tags and build-backend range may resolve differently on future builds.
  Record actual versions for each acceptance/deployment; only the driver version is fixed
  exactly in this package declaration.

## 12. Handoff and open work

For the next session, start here rather than replaying historical n8n setup requests.
Keep the existing user decisions, `processing/` location and 2.1–2.4 phase names.

Immediate operating choices still to complete on the intended deployment:

- Confirm same-host versus remote placement and actual database/network identity.
- Provision local login secrets and verify authentication/effective privileges.
- Rebuild/retest the receiver backup maintenance runtime and enable combined backup scope.
- Choose backup schedule, protected off-host storage, retention, recovery objectives and
  a full host-loss rehearsal. These were not completed by disposable restore tests.
- Decide the explicit sample/live-source activation boundary; do not infer authorization
  to process history from this document or the presence of old source rows.

Phase 2.2 needs the verified local-model API type, private endpoint, authentication method,
alias/resolved model identity, output capabilities and representative anonymized samples.
It adds normalization/evidence preservation, strict extraction contracts, account mappings,
deterministic financial checks and genuine transaction candidates. No n8n details are
required to start that work.

Phase 2.3 adds candidate-specific review/corrections and authenticated repeat-safe callbacks,
plus a durable notification outbox. Messaging delivery needs the user's selected app and
authorization. Phase 2.4 repeats failure/restore testing across the full system and rolls
out gradually. Actual writes remain Phase 3 and require the separate bridge/import ledger.

Related references:

- [Processing README and quick commands](../../processing/README.md)
- [Phase 2.1 implementation plan](PHASE_2_1_PLAN.md)
- [Compact verification record](VERIFICATION.md)
- [End-to-end plan](PLAN.md)
- [Architecture](ARCHITECTURE.md)
- [Future extraction/review contracts](CONTRACTS.md)
- [Full-pipeline operations/acceptance plan](OPERATIONS.md)
- [Receiver history and live Phase 1 evidence](../../imap-receiver/runbook.md)

## 13. Phase 2.2 verification and pilot operation

### Status and deployment decisions

Verification resumed on **16 October 2026 (Asia/Calcutta)** after a usage-limit interruption.
The foundation is locally verified. Phase 2.2 is a **review-only pilot**, not accepted for
automatic transaction eligibility. Every extracted candidate receives
`format_not_regression_approved`; no model score or response can remove this gate.
`extracted` means that proposed events were saved, not that they are ready for import.

The user identified Roastery as the model host: Docker on Windows, RTX 3080 with 10 GB
VRAM, 32 GB RAM, llama-swap and HTTP Basic authentication. The endpoint stays in local
configuration. The exact API route, deployed backend version, model alias, model hash,
schema enforcement and non-thinking settings have not been verified against that host.
The recommended evaluation candidate is Qwen3.5-9B Q4_K_M, with Qwen3.5-4B and
Qwen2.5-7B-Instruct as comparisons. This is a proposed evaluation choice, not a recorded
deployment or a measured winner. No model was downloaded or called on Roastery.

### Implemented path and evidence

1. Migration `002_extraction.sql` adds logical accounts, account mappings, extraction
   results and transaction candidates. There are now thirteen processing tables including
   the migration ledger. Existing fake pipeline versions remain usable; extraction uses
   a separate immutable version/configuration.
2. Normalization prefers a nonempty plain body, otherwise extracts HTML text without
   loading external resources. Scripts/styles/templates are omitted. The subject is
   included. Input is limited to 24,000 UTF-8 bytes; oversized/incomplete input is reviewed,
   never silently truncated and qualified. Source rows remain unchanged.
3. The adapter sends bounded OpenAI-compatible chat requests in a subprocess with a total
   deadline. It requests JSON Schema output and non-thinking mode, but actual enforcement
   must be confirmed on the chosen backend. HTTP is allowed only on loopback for tests;
   remote endpoints require HTTPS. Redirects are rejected. Basic/bearer credentials come
   from local files, never database job payloads. Secret file whitespace is preserved.
4. The parser rejects extra/missing keys, wrong types, malformed JSON, duplicate keys,
   nonfinite values, contradictory classifications, invalid Unicode and oversized results.
   Exact evidence quotes resolve to normalized-text offsets; absent/repeated quotes are
   review reasons. Structurally valid model output remains untrusted.
5. Validation uses Decimal and explicit currency minor units, checks dates, amount
   evidence, account mappings, lifecycle and direction, and flags balance/due ambiguity.
   Foreign amounts are retained without calculating INR. Transfers/card repayments require
   counterpart linking; loan payments receive expense treatment. Missing facts stay unknown.
6. Extraction results, candidate rows, attempt completion and job completion commit in one
   fenced transaction. An expired/replaced worker cannot save its result. Scoped repeated
   account/reference identities are serialized with advisory locks and marked
   `duplicate_suspected`; nothing is automatically discarded as a duplicate.
7. Model-only nontransaction classifications become review items. Only one narrow,
   whole-normalized-message synthetic OTP rule currently ignores a message without the
   model. Because subjects are included, a subject-bearing OTP generally does not match
   this rule. Broad OTP/promotion/decline/reminder rules are deliberately not approved.
8. Transient model errors retry through the durable job machinery. HTTP authentication
   and other permanent configuration errors mark that job dead and stop the current
   dispatch invocation. A Docker restart policy may restart it; pause the affected run
   when investigating. Attempt history now retains the sanitized model error code.
9. Combined backups include all extraction/account/candidate state. Restores are tested
   with populated extraction results, not just empty new tables. Raw output and normalized
   email evidence live in PostgreSQL and its backups; these are sensitive records.

### Findings fixed during verification

- Amount evidence previously used substring matching: `25.50` could match `125.50`.
  Numeric boundaries now reject that mismatch, with a regression test.
- Unknown lifecycle previously lacked a specific review reason. Any lifecycle other than
  `posted` now receives `unsupported_lifecycle`.
- Escaped lone Unicode surrogates could survive JSON decoding and fail at persistence.
  Contract strings reject invalid Unicode; the adapter rejects literal NUL/surrogate output
  as a reviewable protocol error before database writes.
- Failed model attempts previously retained only generic processor error codes. They now
  retain bounded machine-readable model codes without response content or secrets.

### Tests and what they establish

Run the commands in section 7 or the processing README. The new files are
`processing/tests/test_extraction.py` and `processing/tests/test_model.py`.
The final counts and executed packaging checks are in [VERIFICATION.md](VERIFICATION.md).

Synthetic tests cover normalization and size bounds; strict JSON; exact money precision;
amount-substring rejection; balances; missing/ambiguous accounts; foreign amounts;
loan/movement treatment; ambiguous dates/evidence; atomic persistence; duplicate suspicion;
source immutability; malformed-output review; stale-worker rejection; save rollback;
outage retries; narrow OTP handling; populated extraction backup/restore; and combined
runtime/extractor permissions.

Adapter tests run the actual child process against a local HTTP server with synthetic
Basic credentials. They verify request paths/auth/schema settings, model alias listing,
HTTP 429/503 retry classification, 401/302 permanent errors, no redirect following,
malformed/incomplete/oversized responses, NUL/Unicode rejection, total deadline termination,
input limits and configuration identity changes. These tests establish transport behavior;
they do not measure any language model's extraction accuracy.

### Local setup and controlled sample procedure — not executed live

1. Complete private database connectivity and combined-backup prerequisites from section 8.
   Take and verify a pre-upgrade backup, then run `migrate`, `status` and `provision` with
   an administrator connection. Never change a migration already recorded in a live ledger.
2. Give the extraction worker login membership in both `processing_runtime` and
   `processing_extractor`. Keep `processing_operator` separate. The extractor grant adds
   subject/text/HTML/date reads and extraction/candidate inserts; raw MIME and receiver
   credentials remain denied. All processing groups currently have SELECT on processing
   tables, including stored extraction evidence: they are trusted sensitive-data roles.
3. Copy `processing/model.env.example` to ignored `processing/model.env`. Set the verified
   HTTPS base URL (including the API prefix), exact alias, profile and model revision/hash.
   Create local `processing/secrets/model_username.txt` and `model_password.txt` without
   accidental trailing newlines. The example overlay is for Basic authentication; bearer
   authentication requires a matching local secret mount. Do not commit these files.
4. With `RECEIVER_NETWORK` and database settings configured, run the no-email alias check:

   ```powershell
   docker compose --env-file processing/.env -f processing/compose.yaml -f processing/compose.model.yaml run --rm worker model-check
   ```

   Inspect `selected_available`. A successful alias listing does not test structured
   generation, the configured model revision, GPU fit or banking accuracy. `health` checks
   database/schema readiness only and explicitly reports model connectivity unchecked.
5. Using the operator connection, register deliberate mappings, then activate explicit
   synthetic/anonymized source email IDs first. The following CLI examples assume the
   correct role and locally mounted configuration; placeholders are not real source IDs:

   ```text
   tabby-processing map-account --label TEST_CARD --currency INR --bank ExampleBank --product card --identifier 1234 --version mapping-v1 --reason sample-evaluation
   tabby-processing activate --mode extract --version extraction-pilot-v1 --email EMAIL_UUID --reason sample-evaluation
   tabby-processing discover
   tabby-processing work
   tabby-processing candidates
   tabby-processing history JOB_UUID
   ```

   `activate --mode extract` also needs the same model configuration and secret-file mounts
   used by the worker, because it binds the pipeline identity. The runtime worker cannot
   activate scopes or register mappings. Run these operator commands separately with the
   operator login; do not give the long-running worker that role.
6. Compare saved proposed facts and exact source evidence against manual labels. An empty
   `candidates` list does not mean there are no review items: malformed/nontransaction
   cases are in `extraction_results` and `job_results`. Inspect these through a trusted
   database session. Avoid pasting sensitive evidence into terminal logs or chat.
7. Changing the endpoint/profile/model/prompt/schema configuration requires a new pipeline
   version. An alias alone is mutable; record and verify the model file hash separately.
   Reprocessing under a new version deliberately creates new jobs, with duplicate suspicion
   retained across versions. Do not remove the review gate until format-specific tests pass.

### Remaining Phase 2.2 acceptance gaps

- Actual model connectivity, Basic auth, API route, aliases, backend schema support,
  non-thinking support, memory usage and latency remain unverified.
- No representative anonymized bank-format corpus has been supplied or evaluated. All
  current fixtures are synthetic; no candidate can become `ready` through this processor.
- Amount-role and evidence checks are conservative heuristics, not approved bank parsers.
  Date validation currently uses the worker's local date and accepts only unambiguous ISO
  dates; settlement timezone and per-bank date formats need explicit acceptance rules.
- Input budgeting counts serialized request bytes plus output/template reserve. This is
  deliberately conservative and can review emails well below the 24 KB normalization cap;
  it is not an exact backend tokenizer/context calculation.
- Own-account counterpart linking is pending. Duplicate detection only suspects matching
  scoped references; it cannot reliably identify reference-free or differently referenced
  duplicates. Missing/ambiguous accounts remain review cases.
- `map-account` creates a new logical account each time; mapping reuse/deactivation and
  candidate corrections need further operator tooling. Repeat registration can create
  ambiguity and is not an idempotent callback.
- Review decisions, messaging callbacks, notification delivery and the outbox belong to
  Phase 2.3. Actual writes remain Phase 3. No live activation, credentials access, model
  download, fleet deployment, commit or push occurred during this verification.

## 14. Roastery adapter integration

On 16 October 2026 the user supplied the fleet llama-swap design and authorized testing
and integration changes. Read-only inspection included its README, consumer guide,
`config.yaml` and `models.lock`. No files in the fleet repository were changed.

### Confirmed configuration and live access

- The intended LAN API is OpenAI-compatible `/v1`, with Authelia Basic authentication.
  The user confirmed that service credentials have not yet been provisioned.
- An HTTPS `/v1/models` probe outside the sandbox failed to connect on port 443. No HTTP
  status was received, so this is not an authentication failure. Authenticated LAN access
  remains blocked by route availability and missing credentials.
- Local loopback `/health` returned `OK`; `/v1/models` listed `fast` and `assistant`.
  `/api/profiles` reported `gaming`, mapping `fast` to `qwen3.5-4b-cpu`.
- Configuration maps `fast` to Qwen3.5-9B Q6_K in `normal`. The earlier Q4_K_M recommendation
  was a proposed download; this integration uses the existing alias instead. No model
  file was downloaded. No profile was switched and no service was restarted.
- Live requests used only the three synthetic texts in `processing/tests/probe_model.py`,
  through the actual Python adapter and its subprocess. No database connection or captured
  bank email was used. Host loopback success does not establish container/LAN reachability.

### Code and configuration changes

- Added `MODEL_BACKEND=llama-swap`. It reads `/api/profiles` at the service root before and
  after each extraction, retaining active profile and resolved model beside the server's
  reported model. The read path does not change profiles. Failure to read routing follows
  normal model-error handling rather than silently losing provenance.
- Stable routing observations do not exclude an intervening switch. `weights_verified`
  remains false; the response's model filename is not a verified hash. `MODEL_REVISION`
  is a supplied annotation, and `MODEL_PROFILE` is the client configuration label.
- Added `MODEL_SOCKET_TIMEOUT_SECONDS`, default 330, bounded to 1–600. The child-process
  deadline still limits total elapsed time across all profile/generation requests.
- The model Compose overlay sets deadline 360 seconds, lease 420 seconds and shutdown
  grace 390 seconds. Fake-only base settings are unchanged. A timeout does not prove the
  remote model stopped generating; retries may repeat inference but cannot bypass fenced
  database persistence.
- The llama-swap backend caps configured context at 8,192 to support game-mode fallback.
  One worker request runs at a time. Do not scale workers against this single-slot backend
  without explicitly assessing queueing and timeout behavior.
- Added live synthetic probe tooling and regression tests for stable/changed routing,
  context ceilings and cold-start timeout configuration. Basic-auth behavior remains
  covered by a synthetic HTTP server; it has not been verified through Authelia.
- Initial live testing exposed contradictory classification and a foreign purchase
  classified as unsupported. The parser rejected the contradiction. Prompt version
  `bank-extraction-v2` explicitly defines transaction/event consistency and preserves a
  known foreign transaction even when its billed amount is unknown. Pipeline identity
  includes this changed prompt hash, so existing extraction versions must not be reused.

### Interpretation of live results

The initial v1 run failed immediately on a contradictory classification. A complete v1
rerun passed purchase/reminder checks but failed the foreign-purchase classification.
All responses in that complete run conformed structurally to the requested schema and
returned no reasoning content. Schema-shaped responses demonstrate compatibility for
these requests, not exhaustive schema enforcement or trustworthy financial decisions.

See [VERIFICATION.md](VERIFICATION.md) for the final v2 outcomes. The test checks selected
fields and JSON contract consistency; it is not a labelled bank-format regression corpus.
The watcher subsequently selected normal on its own, allowing a normal-profile 9B run;
generation was tested but actual GPU offload was not independently measured.
The unconditional review gate remains enabled regardless of these smoke-test outcomes.

To repeat locally on the Roastery Windows host, with a working Python interpreter:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'processing/src')
$env:MODEL_BASE_URL='http://127.0.0.1:9292/v1'
$env:MODEL_AUTH='none'
$env:MODEL_ALIAS='fast'
$env:MODEL_PROFILE='roastery-synthetic-probe'
$env:MODEL_BACKEND='llama-swap'
python processing/tests/probe_model.py
```

For a LAN test, set the verified HTTPS base and Basic-auth secret paths instead. Do not
copy the loopback settings into a processing container: its loopback is its own namespace.
The probe exits nonzero if any case fails and reports cases separately without printing
credentials or raw response bodies. Test each profile when naturally available; leave
profile changes to the game-mode watcher. A separate controlled deployment must establish
the authenticated HTTPS route before any live email activation.

## 15. Corpus, negative cases and automated-run budgets (16 October 2026)

The user confirmed all 264 supplied emails should be used, including non-transactional
mail. See [the corpus evaluation record](CORPUS_EVALUATION.md) for counts, commands,
negative cohorts, privacy boundaries and remaining acceptance work.

Implemented versions: `email-text-v2`, `bank-extraction-v3`, `bank-templates-v1`.
Template version is now required in extraction pipeline configuration. Existing
activated extraction configurations must not be reused: create a new pipeline version
using the current CLI configuration. No SQL migration or production activation was
performed for this change. Fake processing configuration is unchanged.

Three narrow, evidence-preserving templates run before model fallback. Their output
passes the same strict facts schema and deterministic validation as model output.
Every candidate remains review-only. Template metadata records its rule and version;
model metadata is only recorded when the model actually runs. Missing bodies,
unsupported formats and ambiguous facts must not become silently accepted transactions.

The model worker overlay permits 1,200 seconds per job, a 1,320-second claim lease,
and 1,230 seconds for graceful shutdown. Socket timeout defaults to 1,140 seconds.
The lease margin covers the bounded subprocess plus persistence overhead; expired
claims remain recoverable using the existing fenced recovery mechanism. These longer
limits mean recovery after a crash may take 22 minutes plus polling and backoff.

The configured output target is 6,144 tokens, with a minimum of 4,096 and total context
8,192. The adapter applies the active upstream chat template and tokenizes it before
calling generation. Actual output allowance is the smaller of the target and
`context - measured_input - 512`. If this falls below the minimum, the input is sent
for review rather than truncated. A profile change observed during preflight is a
retryable failure. Generic servers retain conservative byte accounting; their context
must cover the explicit schema prompt as well as output. The generic adapter tests
use 16,384 context, while llama-swap tests enforce the 8,192 profile ceiling.

Thinking tokens and final JSON share the output budget. No separate final-answer
reservation is guaranteed. Token exhaustion creates a review result with bounded
usage/budget metadata; reasoning content is not persisted. Thinking remains a measured
experiment, not proof of correctness. Earlier 4,096-token thinking probes exhausted
output on all three synthetic cases. Consult VERIFICATION.md for the latest run.

Verification: 57 processing tests passed after the changes, including actual isolated
PostgreSQL backup/restore, durable retries and stale-worker fencing, schema and financial
validation, negative template cases, HTML limits, tokenizer failure, profile changes,
adaptive output allocation and safe truncation metadata. Corpus evaluation scanned all
264 files with zero template matches among the 54 selected negative cases. This is
not an end-to-end model accuracy score. No Actual writes, inbox changes, production
migration, service-account provisioning or live pipeline activation occurred.

Final budget decision: keep `MODEL_THINKING=false` in the example. On the same three
synthetic cases, thinking enabled exhausted 6144 output tokens three times; disabled
passed all selected-field checks in roughly 8.1, 5.8 and 0.9 seconds. This supports the
current default, not automatic acceptance of real emails. Full labelled corpus/model
acceptance and authenticated deployment remain outstanding.

## 16. Completed real-mail model verification (17 October 2026)

See [MODEL_BENCHMARK.md](MODEL_BENCHMARK.md) for full methodology, denominators,
paired prompt experiments, performance and limitations. The original model-only run
completed all 264 files despite the chat usage interruption. 12 had no readable body;
252 reached the adapter, producing 248 valid outputs, three input-budget refusals and
one contradictory output. There were no valid false transaction proposals among the
89 readable negative messages. Financial events and their amounts/currencies were
correctly returned for 161 of 163 messages. Median request time was 6.13 seconds,
p95 7.27 seconds, active adapter time 19.79 minutes.

Do not equate those numbers with import readiness. Accounts, types and evidence still
have errors. Date-policy compliance was 68/161 because two-digit years were expanded
without an explicit century in normalized input. The email Date header is currently
not part of that input. Passing trusted date context and deterministic date resolution
is preferable to assuming every inferred date is a known fact. All-fields compliance
was 67/163 and includes this strict date policy; it is not a universal accuracy score.

Prompt v4 withheld known dates and was stopped. The v5 rewrite plus temperature-zero
experiment produced false purchases from OTPs and was rejected. v6 restored the
baseline with only additional date examples and was tested on 111 cases (all readable
negatives plus 22 financial-event cases). It reduced paired all-fields matches from
15/22 to 13/22 and was rejected. Prompt v3 was restored with the exact baseline hash.
No candidate prompt was deployed or activated in a production pipeline.

Current verified settings remain thinking=false and MODEL_TEMPERATURE=0.7, with the
previous 6144 target / 4096 minimum output budget. Temperature now has an explicit
finite 0–2 setting, included in configuration identity; changing it requires a new
pipeline version under the existing immutability rules. First-request time is reported
separately from subsequent median time, while remaining included in totals. A slow
51-second first request in a rejected experiment is consistent with model loading,
but loading telemetry was not independently verified.

The resumable benchmark writes private per-message results under processing/exports
and prints only progress counters. --ids accepts a private list of source hashes for
regression gates. Resumption checks configuration identity; response metadata also
rejects an identity change during a run. Invalid output is retained only in the ignored
private diagnostic file, never routine logs. Keep private expectations and raw emails
out of Git and image build contexts. No source message, unread flag, production DB or
Actual Budget data was changed. 61 isolated regression tests passed for the adapter
and benchmark changes; disposable test containers were removed.

## 17. Confirmed account and foreign-settlement policy (17 October 2026)

The user supplied nine owned accounts, cards and loans, including two closed
products. The private register is `processing/exports/account-confirmations.json`;
it is excluded from Git and container build contexts. This is recorded configuration,
not a production database registration. Preserve leading zeroes in card suffixes.
Closed products remain relevant to historical evidence; do not silently reactivate
them or discard historical payments.

All three HDFC cards share one billing account, with Millennia the primary card.
Keep individual card identifiers for source matching and one shared billing group
for reconciliation. Do not infer that the cards replace one another. Confirmed
own-account transfers and card repayments are movements; third-party payments and
loan repayments are expenses under the user's policy. A beneficiary the user does
not believe is theirs remains provisionally external, rather than confirmed owned.
This register does not yet implement all of those ownership/linking decisions in
the validator: generic transfers still require counterpart review.

The user confirmed that card payments always settle in INR, including purchases
made in USD. A separate email with the final INR charge usually does not arrive.
Card currencies in the private register are therefore INR. Non-card base currencies
remain unconfirmed. Never interpret a foreign purchase currency as the card's
settlement currency or calculate a final billed amount from a market exchange rate.

For foreign purchases:

1. Preserve the amount and currency reported by the alert, with its source evidence.
2. Leave the final billed INR amount unknown until evidence is available. A foreign
   value in `transaction_amount` alone is enough to require settlement review; the
   extractor need not duplicate it in `original_amount`.
3. Retain `foreign_billing_unresolved` when billed money is absent, in another
   currency, or lacks source evidence. Keep the candidate in review. Missing INR
   evidence is a business-data gap, not a transient model failure to retry forever.
4. Resolve from the relevant statement transaction line or an explicit user
   correction, preserving provenance. Statement ingestion and authenticated review
   correction are not implemented by this change. Do not substitute a whole
   statement balance, payment due, or card repayment for an individual purchase.
5. Link the settlement evidence to the existing candidate rather than creating a
   second expense. Shared billing groups must retain the original card identity.

Validation is now `financial-rules-v2`; a changed rule identity requires a new
pipeline version under the existing immutable configuration rules. The universal
review gate remains in place. Regression coverage includes a USD-only alert, an
invented unsupported INR amount, an evidenced INR amount, and a billed amount still
in USD. Even evidenced settlement does not by itself approve an import.

Verification: all 65 isolated regression tests passed after these changes, including
PostgreSQL persistence, crash recovery and backup/restore tests. Disposable test
containers and their network were removed. No live account mappings were registered
and no new live-model benchmark was run for this deterministic validation change.

### Agreed reconciliation scope

The follow-up decision is to use statement emails during the reconciliation step,
with manual correction for unmatched purchases. Bank/card transaction APIs and
exchange-rate services are out of scope for this work.

`financial-rules-v3` makes the pending action explicit in the candidate's persisted
validation JSON. An unresolved foreign charge has `selected_amount: null` and
`reconciliation.status: awaiting_statement_or_manual_correction`, with the required
account currency and allowed resolution sources (`statement_transaction` and
`manual_correction`). Original amounts remain unchanged in the extraction facts and
minor-unit values. This prevents consumers from treating the original foreign amount
as a usable INR amount. The job completes into review instead of repeatedly asking
the model to recover an INR amount absent from the email.

This implements the handoff state only. Future statement reconciliation must match
an individual statement line to the existing candidate, retain evidence and audit
history, reject ambiguous matches and make repeated reconciliation idempotent.
Manual correction is the fallback for those unmatched cases. Neither statement
parsing nor a correction UI/callback is added in this change. No automatic import is
enabled, and existing pipeline versions must not be silently changed to these rules.

The isolated suite was rerun for this handoff change: 65 tests passed, including the
new reconciliation metadata and null selected-amount assertions. Test containers
and their network were removed. These results validate handling, not 100% extraction
accuracy across future emails.

## 18. Known-template date context (17 October 2026)

`bank-templates-v3` and `financial-rules-v4` now pass the captured email
`message_date` to deterministic date resolution. This does not change the model
prompt or guess locale for arbitrary text. The verified HDFC UPI formats use
DD-MM-YY; other formats retain their explicit template-specific date patterns.

`bank-dates-v1` validates the calendar date and resolves a two-digit year against
the email header's century and adjacent centuries. Exactly one candidate must be
within 31 days before or one day after the header date. The small future allowance
handles midnight/timezone boundaries. Invalid/missing headers and out-of-window
dates stay unresolved; malformed calendar dates reject the template shortcut.
No current-year default or Python two-digit-year pivot is used. The header is
context, not proof of settlement or sender authenticity.

The validator independently reruns the supported template and checks account,
bank, product, amount and date before accepting a normalized date. Validation JSON
records the source quote, reference date, resolved date, template and date-rule
version. The original email remains unchanged. Unrecognized model-only formats
retain conservative date checks and the universal review gate remains enabled.

Offline evaluation of all 264 source files matched the same 151 template messages.
All 151 now have resolved dates, including 91 newly resolved two-digit dates; none
had a date-format validation failure. These are resolution/consistency counts,
not independently certified ledger accuracy or a new model benchmark. Reproduce
coverage with `processing/tests/evaluate_corpus.py <private-email-directory>`.
The remaining 12 of 163 financial messages still require model/fallback handling.

All 67 isolated regression tests passed, including ambiguous day/month, year and
century rollover, leap days, invalid headers, stale dates, missing context and
rejection of a model date that disagrees with the supported template. The offline
negative cohort (54 messages) had zero template false positives. Disposable test
containers were removed; no live pipeline or model configuration was changed.

## 19. Remaining-format coverage and private verification map

The twelve uncovered financial emails comprised one HDFC NACH debit, one Axis
loan-closure debit, one Axis UPI credit, one ICICI card repayment, two HDFC UPI
credits, two HDFC card repayments, two HDFC NetBanking payments, one RTGS initiation
and one RTGS completion. `bank-templates-v4` adds narrow body-and-subject rules.
Initiation remains authorization; completion does not turn a beneficiary suffix
into the sender's account. Five messages have no transaction date and remain
undated rather than borrowing their email date. Ownership and settlement remain
review concerns, and these additions do not enable imports.

All 163 labelled financial messages now match a deterministic template. All 89
labelled non-transaction messages produced zero template matches. This is coverage,
not 100% financial accuracy. Comparison of the twelve new outputs against the
previous frozen expectations matched all checked fields except two HDFC credit
dates: the old labels required null, whereas header-context resolution now yields
dates. Old expectations were preserved rather than silently rewritten.

`processing/tests/export_verification.py` creates a private HTML and JSON report
under `processing/exports/verification`. It includes subject, visible email body,
amount/currency, date, bank, event type, saved model JSON, provenance and separately
labelled current template output. It uses the baseline v3 model results; it is not
a fresh model run. Valid JSON is reserialized from saved parsed facts, since raw
response whitespace was not retained. Refusals and unavailable outputs remain
explicit. HTML escapes email/model content and disables active scripts/resources.

Run: `python processing/tests/export_verification.py <email-directory>
processing/exports/model-benchmark-v3.jsonl
processing/exports/benchmark-expectations.json --output
processing/exports/verification` (on one command line, with processing/src on
PYTHONPATH). Keep outputs private and excluded from Git. A daily chat automation
is scheduled for 09:00 local Asia/Kolkata to continue verification and refresh the
report when useful, notifying only on meaningful changes or required input.

Verification: 69 isolated regression tests passed. The twelve newly covered emails
also passed 36 private fixture checks (recognition, duplicate event refusal, and
OTP-subject refusal). Results are saved in the private report directory. Disposable
test containers and network were removed. No new live model generation was needed
to build the report from the requested saved model outputs.

Scheduler correction: the user clarified that the scheduling request was accidental.
The `daily-ingestion-accuracy-review` chat automation was deleted on 17 October 2026.
There is no recurring daily verification scheduled by this chat.

## 20. Confirmed account register and combined validation

The user confirmed all savings accounts, loans and cards are INR-denominated.
The private register now compiles nine owned products into seven logical accounts;
three HDFC cards share their explicitly confirmed billing group. Card suffixes,
including leading zeroes, remain separate mapping keys. Closed products are retained
for historical identification. Compilation does not silently infer external payee
ownership or provision production accounts.

`accounts.compile_register` validates ownership, currency, product, suffix uniqueness
and billing-group primary selection. `install-account-register --file <private-json>
--reason <audit-reason>` installs the compiled mappings transactionally and is repeat
safe. Conflicting prior mappings or changed logical-account attributes abort the
whole operation; they require an explicit migration instead of silent reassignment.
The command uses an operator connection, never worker credentials. Mapping IDs are
versioned from register content. Test installation was verified against disposable
PostgreSQL; the real register has only been compiled/applied to offline evaluation.

`financial-rules-v5` accepts Rs-to-INR and canonical product normalization only when
the entire proposed event exactly matches independent deterministic reparsing.
Model-only claims do not receive that exception. A confirmed loan-credit template
uses credit direction while retaining loan-payment expense treatment. Outgoing
generic transfers use provisional expense treatment under the user's policy, with
counterparty review required; incoming unidentified transfers remain unresolved.
Card repayments remain movements. These treatments do not approve an import.

`correlations` inspects at most the latest 2000 candidates and reports truncation.
It proposes relationships without changing candidates: exact reference plus matching
money/date and opposite legs on different mapped accounts can suggest an own
transfer; compatible opposite loan/card payment legs suggest repayment pairs.
Amount alone never establishes an own transfer. Exact scoped same-direction
references remain duplicate suspicions. No automatic merging or deletion occurs.
The existing fenced extraction duplicate handling remains in place.

The private output map now includes validation under confirmed mappings and
relationship suggestions; supply `--account-register
processing/exports/account-confirmations.json` to the exporter. The companion
`validation-summary.json` compares the current deterministic results with frozen
expectations and retains every disagreement. Results: 163/163 amount and currency,
162/162 labelled account identifiers and directions, 91/91 labelled references,
67/67 labelled event types. Bank/merchant/type labels are not exhaustive. There are
93 date differences because old null expectations predate header-context resolution;
old labels have not been silently rewritten. Five dates remain genuinely absent,
and one RTGS completion has no source account. 162 of 163 events map to owned
logical accounts. One possible own-transfer pair and one possible loan-payment pair
were found (two directional suggestions each).

All 73 isolated tests passed, including repeat registration, drift rollback, shared
billing and amount-only correlation rejection. The universal format approval and
settlement/lifecycle review gates remain: this is not completed ready-candidate
acceptance. Completing that gate still requires explicit supported-format lifecycle
policy, exhaustive critical-field acceptance labels and approved counterpart
resolution. No live deployment, new model run or Actual write occurred. Phase 2.3
will provide the candidate-specific decision mechanism rather than guessing missing
facts here.

## 21. Discussion decisions and practical fallbacks — 18 October 2026

This section records the user's latest instructions and consolidates discussion
points that were previously scattered across benchmark notes and chat. Later
explicit decisions here supersede earlier descriptions of unknown-date/source
account handling; earlier entries remain as historical verification records.

### Confirmed decisions

- Python replaces n8n for Phase 2. PostgreSQL remains the durable source of state.
  Work proceeds as 2.1 foundation, 2.2 extraction/validation, 2.3 review/corrections,
  then 2.4 integrated failure/restore testing and gradual rollout. Actual writes
  remain Phase 3.
- Use all 264 supplied emails, including non-transactional messages for negative
  testing, rather than selecting only the latest 256. Keep source messages unchanged.
- Accuracy matters more than interactive latency. The run is automated and can
  take longer. Maintain bounded time/token budgets and crash recovery regardless.
  The user suggested that the first slow request was likely model loading; this
  remains plausible, not independently measured loading telemetry.
- Roastery runs Docker on Windows, with an RTX 3080 10 GB, 32 GB RAM and llama-swap.
  Public endpoint authentication is basic auth; service credentials were not yet
  provisioned. Keep credential values local. Refer to integration sections for
  verified host-local access and tested model/prompt settings, not assumptions about
  public/container access.
- Bank formats are generally stable. Prefer verified deterministic templates over
  repeated prompt tuning for known formats; keep a model fallback for unfamiliar
  content. The goal is reliable results, not forcing every message through the model.
- The user requests 100% accuracy. Coverage and passing unit tests are not evidence
  of universal accuracy; report denominators, missing source facts and distinctions
  between actual model results and deterministic processing honestly.
- All nine listed products belong to the user and are INR-denominated. The HDFC
  cards share one billing account with Millennia primary. Preserve individual card
  suffixes. Product labels/statuses are in the private confirmation register.
- Ordinary payments to other people are expenses; confirmed own-account transfers
  and card repayments are movements; loan payments are expenses for v1. The RTGS
  beneficiary is not believed to be owned; do not confuse its suffix with the sender.
- Foreign purchases keep the original currency and amount. All card payments settle
  in INR, and a separate INR email usually does not arrive. Resolve actual INR
  charges through later statement reconciliation, with manual correction as fallback.
  Bank/card APIs and exchange-rate conversion are out of scope for now. Statement
  ingestion is deferred rather than a blocker for email extraction.
- The requested output map includes subject, body, amount, date, bank, transaction
  type and saved model JSON. Keep model outputs distinct from inferred/effective
  candidate facts; never relabel parser results as model results. Current reports use
  saved baseline output, not a newly generated model response.
- The daily 09:00 schedule was accidental. It was deleted; do not recreate it without
  a new explicit request.
- Keep this runbook updated with decisions, discussions, implementation and results,
  including previously missed discussion points. Distinguish agreed policy from
  proposals, completed code from planned work, and private account data from public
  engineering documentation.

### Newly authorized fallback rules and implementation

The user explicitly directed: when the transaction date is absent, use the email
date; when a bank transfer alert omits the source account and that bank has only one
confirmed owned bank account, use that account. This supersedes the previous policy
of leaving those specific cases unknown. No further confirmation is required.

`financial-rules-v6` implements both in validation. The raw extraction/model facts
remain unchanged. Candidate facts contain the effective values; validation stores
`effective_facts` and `fallbacks`, recording the rule, value and email timestamp or
mapping/version used. The source email and model evidence are not rewritten.

Email-date fallback currently applies to the verified undated HDFC repayment,
NetBanking-payment and RTGS-initiation formats. A date explicitly present but
ambiguous/conflicting is not overwritten, and an invalid/missing header cannot
supply a date. Unknown model-only formats still require identifying genuine absence
before applying this exception. Date use does not turn RTGS initiation into completion.

Sole-source inference applies to a verified outgoing bank-account transfer with no
source identifier. It selects only enabled bank-account mappings for the exact bank,
excluding cards, loans, other banks and explicitly inactive/non-owned accounts.
Exactly one account/suffix combination must remain. Multiple possibilities remain
ambiguous; an explicitly supplied account identifier is never overridden. Production
operator mappings represent confirmed ownership; the richer private register also
retains ownership/status attributes. The absent RTGS source now resolves from the
user-confirmed HDFC savings account, not from its beneficiary identifier.

The earlier proposed lifecycle/readiness changes are not automatically completed by
these fallbacks. Review gates and counterpart handling remain separate; they must
not be reported as finished merely because all dates/accounts are now populated.

Verification on 18 October: all 75 isolated regression tests passed. Corpus evaluation
applied five `email_date_fallback` decisions and one `sole_owned_bank_account`
decision; all 163 financial events now have an effective date and mapped account.
All 89 labelled non-transaction messages still produce no template financial event.
The private output map was regenerated with separate original and effective facts.
Tests cover missing/bad headers, bank/card distinction, other banks, disabled mappings,
multiple possible accounts and unchanged original extracted facts. Test containers
were removed. No live deployment, mailbox changes or Actual Budget writes occurred.

## 22. Remaining Phase 2 implementation — 18 October 2026

The user requested completion of the remaining Phase 2 work and selected **meowGram**
for review notifications/corrections. No daily automation is reinstated. The local
meowGram repository was inspected read-only: its server currently registers message
sync/WebSocket routes; bot authentication code exists, but a bot message-posting
route and review-action bridge were not found in the inspected checkout. A question
is pending about whether another branch already supplies that contract. Do not
invent a provider endpoint or claim delivery has been tested. No meowGram files,
Authelia configuration or live services were changed.

### Readiness policy

`financial-rules-v7` removes the blanket review gate for exact independently reparsed
purchase rules: HDFC card debit, RuPay UPI purchase, without-OTP purchase, noticed-card
purchase, NetBanking payment, and ICICI purchase alert. These require valid money,
source evidence, one account mapping and date checks (including approved fallbacks).
Known purchase confirmations can be budget-ready without claiming bank settlement:
`budgeting_status=confirmed_purchase_alert` records that interpretation; source
`lifecycle=unknown` remains unchanged. Foreign amounts lacking final account-currency
money remain in review. Transfers, repayments, initiations and unsupported formats
retain their additional policy/review checks. A ready candidate is not an Actual write.

`bank-templates-v5` rejects malformed comma grouping and contradictory declined,
reversed, unsuccessful, cancelled or pending language. Changed model facts do not
inherit deterministic approval. Corpus results: 108 ready purchase candidates,
55 financial reviews; all 163 mapped/dated. Zero matches among the 89 labelled
non-transaction messages. Twelve unreadable messages remain source-level review.
These are offline candidate results, before live cross-message duplicate adjudication.
Negative model classifications still require review except the existing whole-message
OTP rule; zero false transaction matches does not mean all negatives are auto-ignored.

### Review storage, commands and decisions

Migration 003 adds `reviews`, `review_decisions`, `action_receipts` and
`notification_outbox`, and allows candidate disposition `ignored`. Extraction creates
review rows and notification intents within the same fenced completion transaction.
No review is generated for a ready candidate or a whole-message ignored result.

Use a dedicated login with `processing_reviewer` for review/API operations. It can
read processing evidence and mutate review/candidate/outbox state, but cannot update
receiver data or read raw MIME/receiver credentials. Worker/extractor roles can
create review intents but cannot decide reviews. Migrate with the migration owner;
rerun explicit provisioning after schema changes.

Local commands:

```text
tabby-processing reviews
tabby-processing review-show <review-uuid>
tabby-processing review-action --file <private-action.json>
tabby-processing notifications
```

`review-show` intentionally displays private normalized source/evidence; use a private
terminal, not routine log collection. `reviews` and `notifications` only expose IDs,
states, revisions or aggregate counts. Local action identity comes from authenticated
PostgreSQL `session_user`, not an arbitrary CLI actor string.

An action JSON has `action_id` (unique stable string), `review_id`, integer `revision`,
`action` (`approve`, `correct`, `ignore`, `defer`) and a bounded `reason`. `correct`
requires complete `facts` matching the event schema. Transfer/repayment approval
requires explicit `treatment` (`expense`, `income`, `refund`, `movement`). Review
approval requires a mapped account, valid nonfuture date, positive currency-precision
money in the account currency, resolved fields and explicit posted lifecycle.
Human attestation can replace missing textual evidence; it cannot bypass those
structural checks. A suspected duplicate cannot simply be approved as another expense.
An ignored/deferred action must not carry a hidden facts correction.

Source-only review supports a full corrected event, producing one candidate with
human provenance; approve without facts is rejected. Ignore resolves the review;
the original extraction result is preserved. Corrections change one candidate, never
the original extraction facts or any reusable template. No automatic rule learning.

Action IDs are locked, digested and receipted transactionally. Same actor/ID/payload
returns the original result; changed payload or actor is rejected. The review row is
locked and its revision/state checked, so stale or competing actions cannot win.
Decisions preserve before/after facts, actor, reason and revision; outbox intent and
receipt commit together. A failed outbox insert rolls the decision back. A successful
decision increments the review revision. Defer leaves it open; other actions resolve it.

### Callback API and deployment contract

`tabby-processing review-api` defaults to loopback. `POST /review/actions` accepts
the same JSON action, up to 65536 bytes. Required headers are `X-Review-Timestamp`
(Unix seconds), `X-Review-Actor`, and `X-Review-Signature` (hex HMAC-SHA256). Sign the
exact bytes `timestamp + newline + actor + newline + body`. The server allows 300
seconds clock skew and requires an actor in `REVIEW_ALLOWED_ACTORS`. A shared key of
at least 32 bytes is read only from `REVIEW_SIGNING_KEY_FILE`. The trusted bridge
must authenticate the actual meowGram user before signing their actor ID; untrusted
chat text must never choose its own actor. Key holders are trusted review principals.

The API rejects unsigned/expired/unauthorized requests, bounds reads to ten seconds,
limits actors to ten requests/second, suppresses request logs, returns generic errors
and stops on process shutdown. Production access requires an HTTPS reverse proxy;
do not publish it directly on the LAN. HMAC authenticates contents but does not encrypt
them. Response 200 is the committed receipt; 409 is invalid/stale action; 503 is
temporary server failure. Resend the same action ID after uncertain acknowledgement.

`compose.review.yaml` is an explicit optional overlay. Copy `.review.env.example`
to ignored `.review.env`; supply a reviewer DB password and signing key as mounted
local secrets. Host binding is loopback. Configure the reviewer DB login, authorized
actors and proxy before starting it. No credentials were generated or deployed here.

### Notification recovery and backup

`outbox.once(db, sender)` supplies a payload and stable outbox UUID as idempotency key
to a provider adapter with a 20-second timeout. It claims with SKIP LOCKED, a 60-second
lease and token fence; retries use bounded exponential backoff, five attempts, then
inspectable `dead` state. Expired claims recover. A stale sender cannot overwrite a
new lease. Payloads contain only review ID, revision, state and generic text—no raw
banking body or amount. There is deliberately no guessed meowGram sender/worker
configuration until its contract is known. No notifications have been sent.

Provider delivery can duplicate after a crash unless it honors the idempotency key;
callback receipts remain repeat-safe independently. Notifications never rerun model
extraction. Old revision notifications cannot resolve a newer review. Following a
restore, fence old workers and invoke `invalidate-restored-leases`; this now expires
notification leases as well as job leases. Combined backups support the new 17-table
layout while retaining recognition of the older 9- and 13-table layouts.

### Remaining external acceptance gates

Local implementation/testing does not establish a deployed meowGram bridge or fleet
rollout. Required before live completion: verified meowGram send/action contract and
service credentials; private production DB/model connectivity and role provisioning;
sample-only deployment; real authenticated review round-trip; combined backup restore
and old-worker fencing on the deployment environment; then a narrow candidate-only
activation. Actual writes remain Phase 3. These are explicit remaining gates, not
claims that the entire live Phase 2 system is already complete.

Final local verification for this change: 86 isolated tests passed; production image
built successfully; optional review Compose overlay validated with placeholder
network and no environment-file resolution. The corpus report was regenerated.
The suite includes concurrent decisions (exactly one winner), decision/outbox
rollback, source-level correction, replay conflicts, stale actions, signature expiry,
outbox exhaustion and stale-token recovery, plus the existing crash/capture and
combined backup/restore tests. Earlier interim test totals included duplicate test
discovery; 86 is the final suite count. Real provider and fleet checks remain as
listed above. No notification has been sent and no live pipeline activated.

## 23. Resume under root AGENTS.md and user-checkable sample — 18 October 2026

Read the root AGENTS.md, latest runbook entry and Git status before resuming. The
working tree was clean at snapshot `77d93ff`. The user asked to pick up the next
work item under those rules. Selected the independently actionable acceptance
sample rather than repeating the unresolved meowGram interface question.

Done when: a 25-email review sheet spans transaction and non-transaction types,
shows source beside extracted fields, separates generated-label agreement from
user-checked agreement, and the generator/documentation are committed.

The user's new working rules are recorded here: define a pass/fail completion check
before work; use confirmed contextual fallbacks; report problems with a chosen fix;
reserve questions for consequential choices; stop repeated unchanged blockers;
label assistant-generated expectations `unverified (model-generated)`; supply
20–30 varied source/output rows for human checking; report format coverage,
agreement with unverified labels and agreement with user-checked labels separately;
commit working increments; preserve settled user facts and update this runbook.

Implemented `processing/tests/build_review_sample.py`. It deterministically selects
one example per 16 supported financial templates, eight varied negative scenarios
(OTP, statement, offer, loan notice, reminder, application/operational messages),
and one unreadable-input review: 25 unique source IDs. The private static HTML shows
the full available visible body beside current extracted fields and labelled
fallbacks, with saved model fields/JSON separately identified. It loads no external
resources or active email content. User responses can refer to row numbers in chat;
a private response JSON starts with no approvals and is not overwritten on reruns.
Changing the selected sources while responses exist is rejected.

Reproduce with `PYTHONPATH=processing/src;processing/tests` on Windows and:
`python processing/tests/build_review_sample.py processing/exports/verification`.
Run `export_verification.py` first if the underlying output map needs refreshing.
Reports and response templates stay in ignored exports; only the generator and
documentation are committed. No new model calls, production changes or notifications.

Verification: 25 rows, 25 unique source IDs, all 16 template types, eight labelled
non-transactions and one input-review case. Format coverage remains 163 matches
among 264 total emails. Numeric field agreement remains in validation-summary.json,
now explicitly labelled unverified. User-checked extraction agreement is not measured
(zero rows checked); prior account/policy confirmations do not imply those rows were
reviewed. Earlier runbook accuracy-like figures are agreement with assistant-created
expectations unless explicitly identified as user-reviewed. This section corrects
their interpretation without rewriting historical outputs or claiming new accuracy.

## 24. Recipient/payee review requirement — 18 October 2026

User feedback: the existing samples look good, but RECIPIENT was missing from the
summary and is important to track where transactions go and how much. Record this
as approval of the previously displayed sample fields, not of recipient values
which were not yet displayed. Preserve the existing sample selection and responses.

Decision: expose the existing `merchant` counterparty field beside amount in both
reports, with a direction-aware recipient/sender projection. For debits, the
merchant/payee is the recipient; for credits, it is the sender and the credited
account is the recipient. An RTGS beneficiary identified only by a masked suffix
is displayed as that beneficiary account, not as the source account. Unknown names
remain unspecified. The projection records its basis and preserves the raw merchant
field and original saved model JSON. It does not merge merchant aliases or invent
recipient identities, and it requires no new model run or schema migration.

Done when: all 25 rows show recipient/payee; incoming messages distinguish sender
from recipient; the full report includes these fields next to amount; direction and
beneficiary handling tests pass; documentation and code are committed.

Verification: both recipient-direction regression tests passed. Regenerated all
264 report entries and the same 25-row sample. The private response record now
captures the user's positive feedback on all 25 previously displayed rows, scoped
to those fields; recipient/sender/merchant are explicitly not yet user-verified.
Sample metrics report 25 checked/25 agreed for that prior scope, independently of
generated-label comparisons. No recipient accuracy claim follows from prior feedback.

## 25. Recipient approval and next integration item — 18 October 2026

The user confirmed the refreshed recipient review sheet with “Looks good. Next
step.” Record all 25 displayed sample rows, including recipient/sender, as checked
and agreed. This approval is scoped to the displayed current extraction results;
it does not certify every historical model output or all 264 emails. Updated the
private response records, sample badges and metrics: 25 checked, 25 agreed,
25 recipient checks. Generated-label comparisons remain separately identified.
Verified regeneration reports those counts and no longer asks for recipient checks.

Next work item: meowGram notification send/action integration. Read-only Git branch
inspection found existing `feat/r2-epic-2.4-message-api` and `release/r2` workstreams,
while the checkout is on `feat/ust-2.3.2-bot-auth`. The inspected message-API branch
does not yet register a bot POST message route or document its request contract.
Use that existing workstream to establish the send/action contract, then connect
tabbyTally's tested outbox and signed review endpoint. Do not switch or overwrite
meowGram's current checkout, guess a deployed API, or repeat the sample-review request.
No meowGram files or live services changed during this inspection.

## 26. meowGram notification consumer — 18 October 2026

User directed proceeding with the integration, then asked to resume after another
usage-limit interruption. The interruption occurred before the Docker regression
command could execute: automatic approval review was unavailable due to the usage
limit, not because the action was judged unsafe. No test success was inferred from
that rejected command. Resumed from the saved changes and clean prior commit.

Read-only inspection of the message-API epic found no send route. The shared
message-service delivery plan explicitly leaves HTTP routing and transactional
idempotency to later tasks. Chosen implementation: a disabled-by-default consumer
for a clearly labelled proposed `durable-send-v1` contract, with an explicit full
HTTPS endpoint configured locally. Do not describe this as a verified provider or
live end-to-end integration. Do not modify or switch meowGram's active checkout.

Added `notify` / `notify --loop --interval 5`, wired to the existing fenced outbox.
The worker validates configuration before claiming work. Each send uses its stable
outbox UUID as the idempotency key, and acknowledges only a 200/201 durable receipt
with the matching key. Redirects, queued acknowledgments, malformed receipts,
timeouts and HTTP errors remain failed deliveries under the existing five-attempt
retry policy. A subprocess enforces the total 20-second deadline inside the
60-second lease. Credentials come from local files; the client requires HTTPS and
never logs credentials, provider bodies or banking content. Message construction
allowlists only the review ID, revision and state; raw email fields cannot leak
through arbitrary extra payload keys.

Added opt-in `compose.notify.yaml`, `.notify.env.example`, and Git/Docker ignores
for the real `.notify.env`. No deployment, credential creation, live notifications,
or changes to capture/unread flags were made. The five-second durable-queue worker
does not recreate the cancelled daily 09:00 schedule.

Detailed proposed provider contract, replay/restore acceptance checks, startup and
stop commands, and signed callback bridge requirements are in
[MEOWGRAM.md](MEOWGRAM.md). The existing local review commands remain usable now.
meowGram buttons and the authenticated human-action bridge are not implemented by
this increment. The provider must implement/verify the documented durable send
contract before setting `MEOWGRAM_VERIFIED_CONTRACT=durable-send-v1` and provisioning
approved bot credentials. This setting is an operator attestation, not a probe.

Verification before interruption: six focused adapter tests passed. Full isolated
PostgreSQL regression and packaging checks resumed after the usage limit reset;
their results are recorded below when complete.

Completed verification on 18 October: **94/94 tests passed** in the isolated Docker
PostgreSQL suite (20.677 seconds), including six adapter tests and existing crash,
lease, retry, permissions, callback concurrency and backup/restore checks. Built
the production image successfully; its `notify --help` exposes loop/interval
options. Running `notify` with no configuration exits 1 with only a generic
configuration error before database/network access, as intended. Removed the
disposable test containers/network. No new model evaluation was performed and no
accuracy figures changed. Local adapter increment is complete; provider acceptance
and the meowGram action bridge remain separate integration work.

## 27. Provider and authenticated bridge implementation — 18 October 2026

User explicitly requested implementing and verifying meowGram's send endpoint and
authenticated review-action bridge. Created an isolated meowGram worktree at
`.worktrees/meowgram`, branch `feat/tabbytally-review-integration`, from refreshed
`origin/main`; added that local worktree directory to tabbyTally's ignore rules.
The original meowGram checkout remains unchanged. Locally integrated the existing
bot-auth, bot-principals and shared-message-service branches. Preserved all runbook
additions when resolving their append-only conflicts and retained `sender_kind`
in shared-service broadcasts. No PR was merged or branch pushed.

Implementation uses atomic PostgreSQL message/receipt insertion, indefinite replay
receipts keyed by authenticated sender kind/ID and outbox UUID, and conflicts for
changed text. Authentication is repeated on retries. The new bridge accepts only
OIDC-authenticated, explicitly allowlisted human subjects; it derives and signs
the actor server-side and never forwards caller-supplied identity or credentials.
Credentials, live deployment and Authelia changes remain untouched. Verification
and exact operating instructions are being recorded in the meowGram runbook too.

Verification completed: meowGram Go race suite and vet passed; Flutter analysis,
83 tests and release web build passed. Scratch backup/restore preserved nonempty
message receipt counts and associations. Added `processing/compose.bridge.test.yaml`
and a synthetic-only Python fixture server to exercise the actual callback API
from the Go bridge. This passed first decision, repeat-safe replay, stale revision,
conflicting action ID and exactly one persisted decision. The first cross-project
assertion compared raw JSON bytes; JSONB key ordering made that assertion fail.
Changed the test to compare decoded JSON and reran successfully. Production action
semantics were unchanged. No new extraction/model evaluation was needed.

The implemented provider contract and bridge settings now supersede the pending
status in section 26. Live enablement still requires owner-approved deployment and
local credentials; HTTP implementation does not add Flutter review buttons. Full
connection and reproduction instructions are in [MEOWGRAM.md](MEOWGRAM.md).

## 28. Final integration verification and commit — 19 October 2026

User requested resuming after another usage-limit interruption. The limit had
blocked automatic approval review before the last authentication check and commits
could execute; no unsafe-action determination was made. Re-read both repositories'
working rules, runbook entries and Git status; retained all saved implementation.
The final meowGram handler race test passed, explicitly checking that a real Basic
Authorization header cannot access the human-only review bridge. Earlier full Go
race/vet, 83 Flutter tests/web build, backup/restore and real Go-to-Python callback
checks already passed. No implementation was restarted and no live service or
credential was changed. The finished code and reproduction instructions are saved
as separate working commits in meowGram and tabbyTally.

meowGram implementation commit: `cffda0d` on
`feat/tabbytally-review-integration`, in `.worktrees/meowgram`. Removed both
disposable test stacks and their test-only volumes after verification. The isolated
meowGram worktree is clean; it is retained for review and eventual owner merge.

## 29. Integration review and explicit deployment hold — 21 October 2026

User first requested review and deployment/credential preparation. During review,
identified startup route collision handling and callback throttling status as fixes
to complete before deployment. The user then explicitly held deployment configuration
and clarified R2's message API/pourOver polling scope. The optional tabbyTally review
callback is additional scope, not a requirement for that polling design. No PR is
open and no new R2 story ID was assigned. Explained that the IMAP capture receiver
and signed processing review API are different services; the earlier use of
“receiver” was ambiguous. A polling-only topology does not require an inbound review
callback hostname.

The current subject allowlist authorizes financial review decisions, not Actual
writes; subjects also identify individual audit actors. Verified group/role-based
authorization is possible but requires an explicit policy and implementation on
both sides, and is not already provided by the current bridge. No identity is
chosen until the user resolves this decision.

User instruction: placeholders only (RECEIVER_HOST=,
CALLBACK_HOST=receiver.example.home.arpa, OWNER_OIDC_SUB=); real configuration must
come from an ignored host-local env file. Do not deploy, change DNS or touch live
services until the user answers. Prepared processing/deployment/.env.example and
ignored integration.host.env in Git and Docker context. Credential creation and
configuration are held too. Details and review findings are in INTEGRATION_REVIEW.md.

## 30. Polling bot decision; integration parked — 21 October 2026

User settled the architecture: no inbound callback. tabbyTally runs as a meowGram
bot like pourOver: post review prompts, poll sync replies, apply actions locally,
using R2 bot Basic auth. No new hostname or exposed service. LLDAP reviewer group
membership is the authorization policy; individual subjects remain audit actors
only. Chat is references-only (item IDs/counts); amounts and merchants stay local
to tabbyTally. This supersedes the callback and subject-allowlist design in prior
entries. Those historical implementations/tests do not certify the new design.

User requested only a short design note on feat/tabbytally-review-integration and
a green, parked branch with Where we stopped. Added
docs/requirements-from-sister-projects/tabbytally-review-bot.md in the meowGram worktree.
Do not build further integration until BOTH UST-2.4.2 and UST-2.4.3 are merged into
release/r2. No deployment, credentials, DNS or live-service changes. The just-finished
review checks passed (95 processing tests, Go config/handler race tests). No new
integration code will be added while parked. Keep placeholders only.

## 31. Sister-project requirements handoff — 21 October 2026

User requested moving the meowGram-hosted tabbyTally document into a dedicated
“requirements from sister projects” folder, structured to explain requirements
from the other project, work completed and the corresponding plan. Chosen path:
docs/requirements-from-sister-projects/tabbytally-review-bot.md in meowGram, with a
README requirements register. Added stable requirement IDs, responsibility split,
completed-work evidence, planned acceptance checks and the unchanged parking gate.
Updated cross-project references and removed the old release-folder copy. No code,
configuration values or integration behavior changed; no test rerun was required
for this documentation-only reorganization. Link/path checks are the verification.

## 32. pourOver requirements added to sister-project register — 21 October 2026

User requested adding pourOver's requests to the same meowGram folder. Added
pourover-message-api.md under docs/requirements-from-sister-projects in the isolated
meowGram worktree, and updated its README and runbook. The document records the
source dates, requirements, consumer/provider responsibilities, reported completed
work, pending acceptance checks and Where we stopped. It includes Basic polling,
sender identity, composite cursors, prefixed reply idempotency keys, stable bot
usernames and backoff. Dedicated channels remain R2.1 proposal-only; R2 is lounge
API delivery. The original external requirements artifact was not independently
inspected; the new PO IDs identify a synthesis of available local project records.
No integration or deployment resumed. Tests were not rerun for documentation-only
changes; relative-link and whitespace checks verify this increment.
