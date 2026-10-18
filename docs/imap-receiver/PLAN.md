# IMAP Receiver: implementation plan

Date: 15 October 2026
Status: Python setup and capture-once milestones implemented; continuous observer implemented and enabled for the banking inbox

## Current progress

The receiver now uses Python 3.14 and psycopg. One-shot commands implement database diagnostics, certificate-verified read-only IMAP diagnostics, explicit idempotent checkpoint initialization, and capture-once. Existing database schema, account configuration, mounted secrets, and checkpoints are reused. The JavaScript setup files in imap-receiver were removed. Independent supervisor-managed mailbox threads now provide continuous observation.

See ../../imap-receiver/README.md for current commands. The checkpoint initializer is deliberately explicit; building or checking connectivity never creates a baseline.

Capture-once now parses and persists post-checkpoint mail with raw evidence and attachment metadata. Eleven tests cover setup, parsing, replay, rollback, oversized records, and mailbox-generation checks. A live Purelymail test captured one unread email and verified it remained unread. Continuous monitoring now uses IDLE plus periodic scans; 16 tests cover the current implementation. The banking mailbox has connected and completed a live observer scan. New-message IDLE delivery and multiple real accounts still need live validation.

## Working approach

Build together in small stages. Explain the purpose, provide commands appropriate to the chosen host, run a visible check, and address failures before moving on. Do not ask the user to paste mailbox passwords into chat.

Existing code in `../imap-listener/` may be reused after inspection. Its webhook delivery, delivery state, and n8n-specific configuration must be removed from the final receiver. Preserve any existing data and do not assume a successful image build proves reliable mail ingestion.

## Stage 1: choose the host and scaffold

Confirm where commands will run: Windows with Docker Desktop or a Linux fleet node. Confirm PostgreSQL will initially run alongside the receiver, unless the user selects an existing database service.

Deliver:

- Source and tests under this `imap-receiver/` directory.
- Pinned requirements.txt and a Python Dockerfile, and Compose file.
- .env.example, .gitignore, and .dockerignore excluding secrets.
- Multi-account configuration/seed format with stable account and mailbox IDs, endpoint settings, folder lists, enable flags, and credential references; database connection settings remain service-level configuration.
- One-container supervisor with independent mailbox workers, worker limits, and a shared pool sized to support pinned ownership connections.
- Proposed limits for message size, batch size, reconciliation interval, and reconnect delay.

Check: configuration validation works and the image builds. No n8n or Actual credentials are required.

## Stage 2: establish durable storage

Implement migrations for accounts, mailboxes (including checkpoint fields), emails, and attachments. Add unique source identity and supporting indexes. Implement mailbox-scoped ownership locking and transaction helpers. Configuration import must preserve existing IDs/checkpoints and reject unsafe changes to source identity. Secrets remain outside database rows.

Start PostgreSQL with persistent storage. Verify connectivity using a harmless query and confirm migrations can run twice safely.

Check: database integration tests prove duplicate source inserts are idempotent, rollback preserves the previous checkpoint, and a second instance cannot own the same mailbox.

## Stage 3: establish read-only IMAP access

Connect using Python imaplib with ssl.create_default_context() and verified TLS. Select the configured mailbox read-only, record its UIDVALIDITY, and establish the new-mail baseline. Add lifecycle logging without email content.

Run this lifecycle independently for every enabled mailbox. For v1, load configuration on restart; disable/re-enable preserves the checkpoint and a newly added mailbox initializes only its own baseline.

Check: mail already present is skipped, read flags remain unchanged, and a message delivered after initialization is eligible. Record the baseline event before asking the user to send the test message.

## Stage 4: capture and parse

Implement bounded scans, metadata-first fetching, source-size enforcement, MIME parsing, and raw-source preservation. Store parsed address lists, subject, dates, text, HTML, and attachment metadata.

Implement explicit parse_failed and oversized outcomes. Use fixture emails with plain text, HTML, Unicode, multipart alternatives, attachments, absent headers, and malformed content.

Check: stored raw bytes match the fixture hash, parsed content is useful, and one exceptional email does not silently block subsequent mail.

## Stage 5: recover safely

Add IDLE-driven scans, immediate catch-up after reconnect, periodic safety scans, coalesced scan requests, backoff with jitter, UIDVALIDITY blocking, and graceful shutdown.

Check with integration tests:

1. Stop the receiver, deliver mail, restart, and verify catch-up.
2. Replay an already-captured UID and verify the row count does not increase.
3. Interrupt database access and verify the checkpoint does not skip pending mail.
4. Inject a failure before commit and after commit acknowledgement is lost; verify eventual capture without duplicates.
5. Deliver during an active scan and verify the next pass captures the message.
6. Simulate a changed mailbox generation in a disposable fixture and verify intake blocks visibly.
7. Run two accounts and multiple folders concurrently; fail one account and confirm the others continue.
8. Add and disable/re-enable a mailbox without resetting existing checkpoints; verify equal UIDs across mailboxes remain separate records.
9. Exercise worker and pool limits to prove startup cannot exhaust all connections and deadlock.

Use controlled IMAP test infrastructure or mocks plus real PostgreSQL tests. Document what has and has not been exercised against Purelymail.

## Stage 6: package and guide deployment

Provide exact commands for the chosen host to configure secrets, build, start, inspect logs, query captured records, restart, and back up the database. Add health reporting and an operational checklist for blocked intake and capture exceptions.

Check: a clean deployment works from the guide; a restart preserves data; backup restoration preserves the checkpoint and source records. Confirm database exposure is limited to intended networks.

## Stage 7: user acceptance

Use a harmless email before processing banking content. Verify its database record, compare read state in the mailbox, and perform a short downtime/catch-up test. Explain the activation boundary and retention requirements.

Completion criteria:

- Receiver operates with only IMAP and PostgreSQL.
- One container captures multiple accounts/folders with independent recovery and checkpoints.
- No webhook or n8n-specific delivery code remains in the implemented receiver.
- First-run and restart behavior match DESIGN.md.
- Checkpoint and data durability tests pass.
- Parsed fields and original evidence are available.
- Exceptional captures and blocked states are observable.
- Deployment guide and validation results are recorded.

## Deferred work

- PostgreSQL notifications and n8n consumer workflows.
- Consumer leases, extraction, corrections, and review learning.
- Actual API bridge and transaction import.
- Historical backfill and automatic UIDVALIDITY reconciliation.
- Multiple accounts managed through a UI.
- Separate attachment storage and an email retrieval HTTP API.

## Existing verification, with limits

The earlier prototype passed four checkpoint unit tests and built a Docker image. Those checks did not verify real mailbox capture, transactional failure recovery, MIME parsing, or production deployment. They must not be presented as acceptance of this redesigned service.

## 15 October 2026 — current delivery update

Restricted runtime role, health probes, snapshot backup/restore verification, and versioned
schema migrations are now implemented and live verified. The full suite has 41 passing
tests, including disposable-database migration checks. Existing live schema was adopted
at version 1 without application-row changes; post-adoption restore includes the ledger.
The old 001_initial_schema.sql registration example is now examples/register_account.sql.
Current commands and limits live in the receiver README and dated runbook. Next is the
downstream durable processing interface for n8n; keep generic intake independent of it.
