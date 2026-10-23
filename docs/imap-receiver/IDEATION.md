# IMAP Receiver: ideation

Date: 15 October 2026

## Problem

TabbyTally needs a reliable source of banking emails for transaction extraction. Email capture should keep working independently of n8n, the language model, and Actual Budget. A consumer should be able to restart or be replaced without changing how mail is collected.

The receiver has one responsibility: capture new email and persist it in PostgreSQL with enough identity and evidence to support safe downstream processing.

## Intended use

The first deployment watches a dedicated Purelymail inbox receiving bank emails directly. The broader TabbyTally system covers HDFC, Axis, and ICICI accounts and Indian credit cards, including overseas purchases. These are consumer concerns: the receiver should accept mail without interpreting banks, transactions, currencies, transfers, or loan payments.

n8n may later observe database inserts and process them. That integration is currently on hold and is not a receiver dependency.

## Agreed requirements

- Self-hosted, Docker-deployable service.
- One container manages multiple accounts and folders through independent mailbox workers.
- PostgreSQL is the permanent store; no Redis requirement.
- New mail only on first activation, with catch-up after later downtime.
- Use IMAP IDLE for timely notification where supported.
- Read-only access: do not mark messages read, move them, or delete them.
- No n8n webhook, HTTP delivery retries, or application-specific workflow logic.
- Reuse established protocol and MIME libraries.
- Build in guided stages with visible verification at each stage.

## Proposed v1 boundaries

- One worker per enabled mailbox, with its own connection, checkpoint, retries, and health.
- One active worker per mailbox, enforced through a database lock.
- Store original RFC822 bytes plus useful parsed fields.
- Keep mail records immutable; consumers own their processing status separately.
- Capture malformed or oversized-message metadata explicitly so one message cannot silently disappear or indefinitely block the inbox.
- Defer historical backfill, mailbox discovery, a management UI, sending mail, OAuth providers, and automatic mailbox-reset reconciliation.

These boundaries are implementation proposals, not claims of existing capability.

## Options considered

| Approach | Benefits | Costs | Decision |
|---|---|---|---|
| n8n IMAP trigger | Minimal additional code; continuous listening | Capture lifecycle tied to n8n | Keep receiver independent |
| EmailEngine unchanged | Broad headless email platform | Redis, commercial licensing, and another writer still needed | Too broad for this scope |
| EmailEngine fork replacing Redis | Existing application features | Redis queues and Lua operations require redesign; ongoing fork maintenance and license conditions | Do not pursue |
| Email archive application | Existing storage, search, and UI | Sync latency, schema contract, and new-mail-only behavior need evaluation | Reserve for broader archive needs |
| Python imaplib + email + psycopg | Small responsibility, reusable libraries, direct control over durability | We own capture/recovery tests and maintenance | Selected direction |

The initial prototype used ImapFlow, also used by EmailEngine. The user subsequently selected Python. Python 3.14's standard-library imaplib provides IDLE; the email package will handle MIME, and psycopg handles PostgreSQL. Protocol implementation remains delegated to maintained libraries.

## Why PostgreSQL

Email evidence, metadata, checkpoints, and uniqueness constraints belong in durable relational storage. Transactions can commit a captured record and its checkpoint together. A separate notification or queue service is unnecessary for the initial volume.

PostgreSQL notifications can later reduce consumer latency, but stored rows remain authoritative. Notifications are not a durable queue.

## Success criteria

1. A new email becomes a durable database record without running n8n.
2. Messages already present at initial activation are excluded.
3. Messages arriving during receiver downtime are captured after restart, provided they remain in the mailbox.
4. Reprocessing the same mailbox UID creates no second source record.
5. Database or IMAP failures do not advance a checkpoint past unrecorded work.
6. Raw evidence remains available if parsing fails.
7. Consumers can use parsed text without needing mailbox credentials.

## Open deployment decisions

- Build and deployment host: Windows development machine or Linux fleet node.
- PostgreSQL placement: alongside the receiver or an existing database host.
- Database TLS, private network route, and credential provisioning.
- Raw email retention, backup schedule, and storage capacity.
- Message-size limit and procedure for manually retrieving oversized messages.

These affect deployment and operational policy; they do not change the core architecture.

## References

- [ImapFlow API](https://imapflow.com/docs/api/imapflow-client/)
- [Purelymail features](https://purelymail.com/docs/features)
- [EmailEngine dependencies](https://github.com/postalsys/emailengine/blob/master/package.json)
- [EmailEngine Redis implementation](https://github.com/postalsys/emailengine/blob/master/lib/db.js)
- [EmailEngine license](https://github.com/postalsys/emailengine/blob/master/LICENSE_EMAILENGINE.txt)

These references were consulted during the design discussion. Pin and verify dependency versions when implementing.
