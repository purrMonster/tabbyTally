# IMAP listener prototype

**Historical JavaScript prototype; not the active implementation.** Use the
[Python IMAP receiver](../imap-receiver/README.md) for current development.
The active receiver writes to PostgreSQL only; it does not call n8n webhooks.

Purelymail → IMAP IDLE → PostgreSQL → authenticated n8n webhook.

This service only captures email. It does not extract transactions or modify Actual.
It uses ImapFlow automatic IDLE, read-only mailbox access, bounded UID scans,
and a durable outbox. Normal intake is notification-driven; a 60-second scan
also checks for missed notifications. Webhook delivery checks the outbox every second.

## Start

1. Copy `.env.example` to `.env` in this directory.
2. Set the Purelymail mailbox credentials, webhook URL and random bearer token.
   Use the same database password in POSTGRES_PASSWORD and DATABASE_URL;
   URL-encode special characters in the connection URL.
3. Configure and publish the n8n webhook described below.
4. Run `docker compose up -d --build` from this directory.
5. Run `docker compose logs -f listener`. Wait for
   `new_mail_checkpoint_created`, then send a test email.

The first successful mailbox selection skips all messages already present.
Subsequent restarts retain the checkpoint and catch up, even for read emails.
Do not delete the PostgreSQL volume: that discards the checkpoint and pending work.
Run only one listener instance. A database advisory lock prevents a second owner.

## n8n contract

Create a POST Webhook node at `bank-email`, with Header Auth:

- Header name: `Authorization`
- Header value: `Bearer <same WEBHOOK_TOKEN>`
- Response mode: use a Respond to Webhook node, not immediate acknowledgement.

The payload is:

```json
{"event_id":"a UUID", "type":"bank_email.received", "schema_version":1}
```

Create a separate durable processing-jobs table with a UNIQUE event_id. The intake
workflow must INSERT the event ID with ON CONFLICT DO NOTHING, then return HTTP 202.
Only acknowledge after this commit. A separate processing workflow claims these
jobs. Repeated webhook delivery is expected, including when an acknowledgement
is lost. A repeated event should return success without creating another job.

Read the email using a parameterized Postgres query with the event ID:

```sql
SELECT event_id, encode(raw_email, 'base64') AS raw_email_base64, received_at
FROM mail_event WHERE event_id = $1;
```

The stored bytes are full RFC822 email, including MIME/HTML and any attachments;
decode and MIME-parse them before LLM extraction. The listener deliberately keeps
the original evidence. This prototype fetches full messages into memory; add size
limits or streaming before using it for large statements/attachments.

n8n on another fleet host needs PostgreSQL connectivity. This compose file exposes
no database port. Provide private, firewall-restricted database access with TLS
and a dedicated least-privilege n8n database role, or add an authenticated retrieval
API. A normal Traefik HTTP route cannot proxy PostgreSQL. Do not expose the database
publicly. The listener itself needs no inbound port or Traefik route.

## Recovery and operations

- Raw email insertion finishes before checkpoint advancement. Replays are safe
  because mailbox/UIDVALIDITY/UID is unique.
- Failed webhooks retry with exponential backoff, capped at one hour.
- HTTP 2xx means n8n durably accepted the job, not that Actual was updated.
- UIDVALIDITY changes log `uidvalidity_changed_manual_reconciliation_required`
  and block capture until an operator reconciles mailbox identity. Do not simply
  delete the checkpoint, which would skip outstanding mail.
- Message-ID and transaction-level duplicate detection belong downstream; a bank
  sending the same alert under a different UID produces a separate source event.
- Keep emails in the mailbox until captured; deleted-before-capture messages
  cannot be recovered by this service.
- Monitor pending-event count, oldest pending event, process restarts and the
  listener logs. Financial email retention and database backups need deployment
  policies; this prototype does not automatically delete evidence.
- No message bodies, passwords or connection strings are deliberately logged.

## Verification

Run `node --test test/checkpoint.test.js` (Node 24). Tests cover first activation,
restart catch-up, empty ranges and UIDVALIDITY changes.

Before live use, verify real IMAP delivery, reconnect catch-up, n8n downtime,
duplicate webhook acceptance, database restart and process termination during
capture. These require your deployed services and credentials.

The Dockerfile pins direct dependency versions. Generate and commit a package
lock and switch to `npm ci` after dependency installation is verified, before
production deployment.

References: https://imapflow.com/docs/api/imapflow-client/ and
https://purelymail.com/docs/features
