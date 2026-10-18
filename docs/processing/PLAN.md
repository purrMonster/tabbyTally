# End-to-end delivery plan

Status as of 18 October 2026: 2.1 locally verified; 2.2 supports ready purchase
candidates and explicit financial reviews. 2.3 local review/correction, signed API,
receipts and outbox are implemented. A disabled meowGram consumer now implements
the proposed [durable-send-v1 contract](MEOWGRAM.md); provider verification and the
human-action bridge remain pending. Local 2.4 regression/restore acceptance passes, while live fleet
deployment and authenticated meowGram round-trip remain pending. The latest suite
has 94 passing tests. The 264-email offline corpus produces 108 ready purchases,
55 financial reviews and zero template matches among 89 non-transaction messages;
12 unreadable emails need source review. These are measured fixture outcomes, not
universal accuracy. See RUNBOOK.md section 22 for exact remaining deployment gates.
The current phase name is **Phase 2 — Python ingest**, divided into 2.1–2.4 below.
The detailed [2.1 plan](PHASE_2_1_PLAN.md) governs the initial implementation slice.
All milestones below belong to Phase 2 unless explicitly labelled Phase 3.

| Stage | Existing milestone mapping |
|---|---|
| 2.1 — Durable jobs, retries, crash recovery and backups | M0 deployment prerequisites, M1–M3, and minimum packaging/operations needed to test them |
| 2.2 — Local extraction and deterministic validation | M4–M5 |
| 2.3 — Review/corrections and messaging callbacks | M6 |
| 2.4 — Integrated failure/restore testing and gradual rollout | M7 |

M1 introduces only the foundation tables specified in 2.1. Extraction, candidate, account
mapping and review/outbox tables follow in 2.2/2.3. Backup verification expands with every
schema change. Crash/restore testing starts in 2.1 and repeats end-to-end in 2.4.

## M0 — record deployment and interface contracts

Inspect the deployed receiver/database versions and available resources. Decide whether
the processing container joins the receiver's local Docker network or runs on a separate
fleet node. Record redacted configuration, image versions and ownership. Keep PostgreSQL
private; do not expose it through an HTTP Traefik router.

Prefer the same-host network initially if resources permit. A separate Compose project
must explicitly join the shared network; service DNS is not automatically cross-project.
For a remote node, configure a private interface, source-restricted firewall and database
access rules, certificate-verified TLS, and a dedicated runtime login. Verify using a
harmless query and negative permission tests. Do not publish a port merely to write docs.

Deliver: deployment decision and configuration contract. Model and messaging discovery
can wait until M4 and M6; neither blocks schema and fake-worker development.

## M1 — processing schema, privileges and recoverable backups

Implement checksum-verified, transactional migrations for the separate `processing`
schema and ledger. Define the tables and constraints in [Architecture](ARCHITECTURE.md).
Separate migration, worker, review and inspection privileges. Grant only the required
receiver columns; runtime roles cannot update source rows or mailbox checkpoints.

Extend the existing backup system to archive both schemas under one exported snapshot.
Version its manifest and verifier, preserve verification of old receiver-only archives,
and cover migrations, constraints, processing rows and cross-schema references. Do not
change the receiver fingerprint semantics silently: its migration drift checks reuse
the current fingerprint function. Add processing-aware verification separately.

Gate: clean install, repeat apply, checksum/drift rejection, forbidden-operation tests,
and isolated restore of both schemas pass. Receiver migrations still pass unchanged.
No live processing activation before combined backup verification succeeds.

## M2 — explicit activation and durable discovery

Implement a CLI to inspect and explicitly activate a pipeline version for selected
mailboxes. Record per-mailbox UIDVALIDITY and committed last-UID boundaries as described
in Architecture. Explicit stored-email IDs provide a separate sample/replay scope.
Activation never silently includes the existing mailbox history.

Run bounded scheduled reconciliation with `INSERT ... ON CONFLICT DO NOTHING` on
`(email_id, pipeline_version)`. Repeated passes must eventually cover every eligible row,
including rows committed after a prior scan. Include capture failures as review outcomes.
Persist activation configuration independently of process restarts.

Gate: concurrent/repeated scans create one job; downtime catches up; boundary races,
new UIDVALIDITY and explicit samples behave as specified. No IMAP calls or source writes.

## M3 — claims, attempts, retries and crash recovery

Build a fake processor with deterministic success, transient failure, permanent failure,
delay and crash modes. Implement atomic claim/attempt creation, expiring leases,
conditional completion, recovery sweeps, backoff, exhaustion and audited operator retry.
Persist all outcome rows and job completion together. Enforce a token and unexpired lease
before any authoritative result mutation. Use database time for lease decisions.

Gate: the concurrency/crash cases in [Operations](OPERATIONS.md) pass against PostgreSQL
17, including the ambiguous-commit case. A stale worker cannot save candidates or retry
state. Completed work remains completed after restart. Capture continues during worker
failure. Demonstrate this milestone without a model or Actual credentials.

## M4 — normalization and local structured extraction

Verify the actual local model service API, authentication, alias, resolved model identity
and structured-output behaviour. Do not assume Ollama or OpenAI compatibility from its
name. Pin the adapter contract and bounded timeout/response limits.

Implement plain-text/HTML normalization with evidence offsets and version/hash recording.
Build the extraction schema in [Contracts](CONTRACTS.md), including multiple events and
separate original/billed amounts. Use strict parsing and a bounded repair policy. Keep
synthetic or vetted anonymized fixtures in Git; private samples remain local.

Gate: malformed output, oversized input, HTML, embedded instructions, missing facts and
model outages have explicit outcomes. Every result records source, attempt, input,
prompt, schema and model provenance. No external HTML resources are fetched.

## M5 — deterministic validation and account resolution

Implement money/date/evidence checks, explicit account mappings, event classifications,
duplicate evidence and transfer/repayment correlation. Version rules and mappings.
Separate a completed extraction from an eligible financial candidate.

Gate: the financial fixture matrix passes with zero false-ready cases in the approved
suite. Record critical-field accuracy and review rate per supported format. Unsupported
or insufficiently tested formats remain review-only. A synthetic suite alone does not
establish live bank-wide accuracy.

## M6 — review, corrections and notification delivery

First provide authenticated local/operator inspection and candidate-specific correction
commands. Then add a review API and messaging adapter once the interface is known.
Persist decisions and notification intents atomically; deliver through a separately
retryable outbox. Notification failure must not rerun extraction or undo a decision.

Callbacks carry review ID, expected revision and action ID. Authenticate the actor;
enforce replay/idempotency rules and reject stale decisions. Revalidate corrected facts.
Promote reusable mapping/rule changes only through versioned regression-tested releases.
Keep notification delivery disabled until explicitly authorized.

Gate: duplicate, stale, forged, concurrent and out-of-order callbacks behave correctly;
outbox retries survive crashes; corrections preserve original evidence and audit history.
Review remains usable locally while the messaging service is unavailable.

## M7 — package, operate and run acceptance

Package the application as one Python distribution/container with separate command modes
for reconciliation, work, recovery, notification and API serving. Choose and pin compatible
Python/library versions when implementation begins. Use psycopg for PostgreSQL, a strict
schema validator, an HTTP client with explicit limits, and a small API framework only when
callbacks are needed. Keep dependency and deployment choices in version control.

Add graceful shutdown, bounded connection pools, resource limits, health checks, safe
structured logs, operator inspection and backlog/dead-job alerts. Finish the rollout and
restore runbook; run the full acceptance matrix. Start with sample-only shadow processing,
then activate a narrow live scope in candidate-only mode.

Gate: evidence is recorded for each acceptance case; restore recovers jobs and reviews;
downstream outages do not interrupt capture or alter unread flags. No Actual writes.

## Phase 2 completion and Phase 3 handoff

Every selected email has a durable processing status and a traceable result or inspectable
failure. Every ready candidate passes the supported deterministic policy; review items
have reasons, evidence and a correction path. Backups cover source and processing state.
Document actual sample coverage, unresolved cases, deployed versions and rollback steps.

Phase 3 will implement the Node.js bridge using the official Actual API client, discover
budget/account mappings, and add a separate idempotent import-job ledger. It must handle
uncertain write outcomes, linked transfer legs and Actual rules before automatic imports.
Candidate IDs and revisions are handoff identities; an email-job ID alone is insufficient
when one email contains several events. Start with controlled writes. Statement processing
and historical inbox import remain separate future scope.

## Dependency order

```text
M0 deployment decision ──────────────────────────────> live rollout
M1 schema + backup -> M2 discovery -> M3 fake worker
                                      |
                         M4 extraction -> M5 validation
                                               |
                                        M6 review -> M7 acceptance
                                                          |
                                                Phase 3 budget writes
```

Do not substitute model demonstrations for the M1–M3 recovery gates. No calendar estimate
is committed until the deployment and fixture inputs are available.
