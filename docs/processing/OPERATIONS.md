# Operations and acceptance plan

Status: planned runbook and test requirements. Commands will be added alongside their
implementation; this document does not claim deployment or successful acceptance.

## Configuration and service operation

Keep configuration names and placeholders in `.env.example`; mount database/model/API
secrets from local protected files. Never commit credentials, private addresses, raw
emails, model responses or production exports. Keep processing secrets separate from
receiver and future Actual credentials.

Record database host/port/name, role, TLS settings, active pipeline configuration,
reconciliation/recovery intervals, request limits, attempt budget, lease duration,
backoff limits and model concurrency. Validate configuration on startup and fail closed
for unsupported combinations. Model/messaging configuration is not required for the
fake-processor foundation or local review mode.

The container exposes command modes for discovery, worker, recovery, inspection and
later review/API/outbox operations. Restart policies recover crashed processes; PostgreSQL
leases recover their work. Health checks distinguish process liveness, database readiness,
configuration failure and model unavailability. Model downtime should report degraded
processing without declaring the independent receiver unhealthy.

Routine logs contain IDs, state changes, durations, retry counts and safe error codes.
Do not log SQL parameters, prompts, bodies, full model output, callback credentials or
unfiltered exception text. Protect stored evidence and restrict inspection access.

Monitor queued/due/leased/dead counts, oldest eligible unprocessed email, reconciliation
success time, lease expirations, rejected stale writes, model failure rate, review age,
outbox lag, database capacity and last verified backup. Initial alert thresholds are
deployment configuration; avoid notifications on every unchanged retry. Operator actions
include pause dispatch, inspect attempts, grant a bounded retry allowance, resolve review,
activate a version and explicitly supersede a result. All mutations are audited.

## Backup and restore

The existing receiver backup is insufficient for Phase 2. Extend it before activation:

1. Dump `imap_receiver` and `processing` together under one exported database snapshot.
   Include both migration ledgers, constraints, indexes and all processing/audit/outbox rows.
2. Version the manifest and verifier. Check archive digest, schema structure, row counts
   and deterministic row digests, source hashes and cross-schema references. Cover any
   functions/views added for permissions or transitions. Preserve old archive verification
   without pretending receiver-only archives contain processing state.
3. Keep receiver migration fingerprints compatible with existing drift detection.
   Processing verification must not silently alter the baseline used by receiver migrations.
4. Restore only trusted archives into a newly created disposable database during tests.
   Reprovision roles/grants separately: schema dumps are not a backup of cluster-level
   role credentials. Verify permissions under real runtime roles after provisioning.
5. Maintain protected off-host backup copies and document retention, recovery-point and
   recovery-time objectives before live activation. A local dump alone does not cover
   host loss. Keep secret recovery instructions separate from Git.

Production recovery procedure: stop/fence all old processing workers and callbacks;
restore both schemas from the same archive into an isolated replacement; verify integrity,
roles and migration compatibility; rotate/revoke old access if needed; invalidate restored
leases with an audited recovery operation; inspect outbox uncertainty; reconcile missing
eligible jobs; then enable processing. Never run old and restored environments as active
authorities simultaneously. Coordinate receiver restoration and mailbox catch-up separately
so database checkpoint rollback does not silently lose captured messages. Test catch-up
with retained IMAP messages; messages deleted since the backup require separate source
recovery and cannot be assumed retrievable.

An old callback absent from a restored receipt ledger may be replayed. Rotate callback
credentials/epoch or reject pre-restore callback tokens and reissue review notifications
before reopening the endpoint. Provider notifications already sent cannot be rolled back;
reconcile or tolerate documented duplicate delivery. Phase 3 will need additional budget
write reconciliation before replay; there are no such writes in Phase 2.

Do not automatically purge sources, attempts or decision history in v1. Establish explicit
retention and storage limits before unattended use; deletion must preserve required audit
references and evidence. Unknown tables or manifest scope must fail verification visibly.

## Acceptance matrix

Use unit tests for pure validation and real PostgreSQL 17 integration tests for concurrency,
permissions and transactions. Run destructive/crash tests only in disposable environments.
Store synthetic/anonymized fixtures and expected outcomes; never use a live inbox for
destructive testing. Record each case's build, configuration, fixture ID and result.

| Case | Required evidence |
|---|---|
| Clean/repeat migrations | Deterministic install; repeat is safe; modified history/drift rejected |
| Permissions | Worker cannot write receiver rows/checkpoints, read secrets or perform DDL; review scope is restricted |
| Activation race | Capture transaction spanning activation is discovered after commit; prior committed UIDs excluded |
| Scope changes | Uninitialized mailbox rejected; changed UIDVALIDITY paused; explicit samples handled without history import |
| Concurrent discovery | Repeated/concurrent scans yield one source/version job, including late commits |
| Worker competition | Concurrent workers cannot own the same active claim |
| Crash before model | Attempt is abandoned after expiry; bounded retry recovers work |
| Crash after model / before save | A later model call is allowed; only one authoritative outcome persists |
| Crash during save | Transaction rolls back entirely or commits entirely; no orphan ready candidates |
| Lost commit acknowledgement | Inspection finds committed completion; no duplicate result is created |
| Stale worker | Late completion, heartbeat and retry updates fail after expiry/reclaim, including before another claim |
| Retry exhaustion | Jitter/backoff and attempt limits hold; dead job and history remain inspectable |
| Operational retry | New bounded allowance is audited; old attempts retained |
| Invalid model output | Wrong types, invalid JSON, excessive output and unsupported enums get bounded handling |
| Input safety | HTML resources never fetched; injected instructions cannot bypass schema/validation; incomplete input enters review |
| Money/date checks | Balance and dues excluded; precision, unknown currency, invalid/ambiguous dates cannot become ready |
| Account ambiguity | Missing mappings and colliding masked suffixes enter review |
| Foreign purchase | Original currency retained; final INR amount never invented |
| Event types | OTP/promotion/decline/reminder ignored appropriately; mixed valid events retained; loans are expenses |
| Transfers/repayments | Supported linked movements do not become double expenses; ambiguous pairs reviewed |
| Financial duplicates | Repeated references linked safely under concurrency; legitimate same-amount purchases preserved |
| Model/service outage | Jobs back off/recover; capture continues; processing does not exhaust database resources |
| Database outage | No local-only success claimed; reconnect reconciles state; capture resumes via its existing recovery |
| Review callbacks | Forged/stale/conflicting payloads rejected; identical replay returns prior result; concurrent decisions serialize |
| Corrections/reprocessing | Candidate revision and provenance preserved; new versions cannot overwrite approved facts silently |
| Notification crash | Outbox recovers independently; provider limitations documented; no extraction rerun |
| Backup restore | Both schemas/ledgers/audit state match snapshot; privileges reprovisioned and tested |
| Restore replay | Old workers fenced; restored leases recovered; old callbacks invalidated; backlog reconciled |
| Capture independence | Downstream outage leaves source persistence and IMAP unread flags unchanged |
| Phase boundary | No Actual credentials, requests or writes occur throughout acceptance |

For the model evaluation set, report per-format/event critical-field exact matches,
false-ready count, review rate and ignored-message errors. Require zero false-ready cases
in the approved suite and document sample size and limitations. Freeze a holdout set;
do not evaluate prompt changes only on the examples used to tune them.

## Rollout and rollback

1. Complete M1–M3 with fake processing and disposable data; verify combined backups.
2. Run explicit anonymized/sample selections with the real model in candidate-only mode.
3. Review outcomes and approve supported mappings/formats; keep unsupported inputs in review.
4. Record a narrow live activation boundary, deploy one worker and monitor capture/backlog.
5. Enable the authenticated messaging adapter only after local review works and outbound
   notification integration is authorized.
6. Record full acceptance evidence and open limitations before declaring Phase 2 complete.

Rollback pauses discovery/claims/outbox dispatch and stops the faulty release. Keep all
source and processing history. Redeploy a schema-compatible prior application version;
do not blindly reverse migrations or restore an older database over new captured emails.
Use forward fixes for incompatible schema changes. Disable the affected pipeline version
and explicitly scope any replacement run. The receiver continues independently.
