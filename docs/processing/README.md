# Phase 2 — Python ingest

Updated: 16 October 2026. Status: Phase 2.1 verified locally; Phase 2.2 review-only pilot
implemented with synthetic tests. Real-model and bank-format acceptance remain pending.
No live processing deployment or activation has been performed. See [verification evidence](VERIFICATION.md).

**Phase 2 outcome:** captured emails become validated transaction candidates, ignored
messages, or review items, with reliable retries and traceability. Exhausted processing
failures remain visible for inspection. Actual Budget writes begin in Phase 3.

Python replaces the proposed n8n orchestration. PostgreSQL remains the source of truth.
The existing Python IMAP receiver continues to own capture independently.

## Phase breakdown

| Stage | Outcome |
|---|---|
| [2.1 — Durable foundation](PHASE_2_1_PLAN.md) | Jobs, retries, crash recovery and backups, tested with a fake processor |
| 2.2 — Extraction and validation | Local-model extraction and deterministic financial validation |
| 2.3 — Review and corrections | Candidate corrections, notifications and authenticated messaging callbacks |
| 2.4 — Acceptance and rollout | Integrated failure/restore testing and gradual rollout |

Here, Python ingest consumes already captured emails; IMAP capture remains in Phase 1.

| Document | Purpose |
|---|---|
| [Detailed runbook](RUNBOOK.md) | Decisions, implementation history, exact behaviour, operations, tests and recovery |
| [Delivery plan](PLAN.md) | End-to-end sequence, dependencies, deliverables and completion gates |
| [Phase 2.1 plan](PHASE_2_1_PLAN.md) | Detailed foundation implementation sequence and acceptance checklist |
| [Architecture](ARCHITECTURE.md) | Deployment, data ownership, activation, jobs, leases and retries |
| [Contracts and validation](CONTRACTS.md) | Extraction, financial checks, review and Phase 3 handoff |
| [Operations and acceptance](OPERATIONS.md) | Backups, restore, rollout, monitoring and failure tests |
| [Processing node](../../processing/README.md) | Runnable foundation, commands and deployment instructions |
| [Verification](VERIFICATION.md) | Executed checks and remaining deployment prerequisites |

This replaces the n8n implementation sequence previously in
[the Phase 2 entry point](../PHASE_2_PLAN.md). The root README's sprint roadmap is
historical planning; this directory governs Phase 2 implementation.

## Confirmed repository baseline

- `imap-receiver/` implements capture, migrations, health checks and backup verification.
- Capture stores immutable source evidence in `imap_receiver.emails`; it uses IMAP
  `BODY.PEEK` and records mailbox checkpoints separately.
- Receiver Compose uses PostgreSQL 17 and does not publish its database port.
- The backup command supports both schemas with `--include-processing`; receiver-only
  archives remain supported. Live backup schedules still need that option enabled.
- `processing/` implements durable fake processing, recovery, operator commands and a
  review-only model adapter/extraction path. The review API and Actual bridge remain unimplemented.

These are repository observations, not a fresh verification of deployed fleet services.

## Decisions

1. Build a Python application with PostgreSQL-backed jobs; no n8n, Celery or Redis
   dependency for the initial implementation.
2. Implement and test the durable foundation before introducing a model.
3. Start with one model request at a time and scheduled reconciliation.
4. Keep unknown financial facts unknown. Deterministic validation controls readiness.
5. Scope initial fixtures to HDFC, Axis and ICICI savings/card alerts. Coverage must be
   demonstrated per format and event type, not inferred from the bank name.
6. Treat loan payments as expenses for v1; preserve transfers and card repayments as
   linked movements. Foreign purchase amounts do not imply a final INR debit.
7. Keep live credentials and unredacted banking samples local and outside Git.

## Inputs needed later

Foundation work can start without model or messaging details. Before deployment, confirm
same-host versus remote processing placement and private database access. Before model
integration, supply the local API type, endpoint, authentication mechanism, alias/model
identity, capabilities and representative anonymized emails. Before messaging integration,
confirm the app, identity model, callback authentication and notification authorization.
Provision secret values locally; do not put them in these documents or chat.
