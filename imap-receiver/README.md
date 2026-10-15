# IMAP receiver — usage and operations

## Development checkout status

The observer is verified against an existing deployment. This is not yet a complete
fresh-install release: versioned schema migrations and tested backup/restore tooling
are still pending. `001_initial_schema.sql` is an example account-registration INSERT,
despite its historical filename; it does not create the schema and is not idempotent.
Do not rerun it against an existing configured inbox.

`.env.example` documents the bootstrap variables. Copy it to a local `.env` and supply
your own password. Compose also requires local files in `secrets/` for the IMAP and
runtime database passwords; see the provisioning instructions below. Never commit
these files, raw emails, database dumps, or unredacted financial samples. Backups and
exports belong in ignored `backups/` and `exports/` directories. Ignore rules do not
sanitize data inside an otherwise tracked file: review staged changes before pushing.

The ignored `.env` also records `BANKING_IMAP_USERNAME`, `BANKING_IMAP_PASSWORD`, and
`RECEIVER_DB_PASSWORD` for local configuration. In the current deployment, the mounted
files in `secrets/` remain the password source and PostgreSQL remains the mailbox
username source. Editing these three `.env` values alone does not update the running
receiver, change account identity, or rotate a database password. Keep the corresponding
local values consistent when intentionally changing configuration. Do not share `.env`.

The `examples/*.txt.example` files document the two mounted secret files. Supply your
own values in `secrets/banking_imap_password.txt` and `secrets/receiver_db_password.txt`;
write exact UTF-8 bytes without a trailing newline. The runtime database password must
contain at least 32 ASCII alphanumeric characters. Never use the example text as a
password or overwrite existing secrets merely to set up these examples.

For the dated decisions, verification history, and next-session handoff, see
[runbook.md](runbook.md).

This Python 3.14 service captures new IMAP email into PostgreSQL using standard-library
imaplib and email, plus psycopg. It supports continuous observation with independent
mailbox workers, as well as one-shot diagnostics and capture commands.

## Continuous observer

The banking account is enabled and the receiver service runs `observe`.

```powershell
docker compose up -d --build receiver
docker compose logs -f --tail 30 receiver
docker compose stop receiver
docker compose start receiver
```

Each enabled mailbox under an enabled account gets an independent thread, read-only
IMAP connection, and pinned PostgreSQL connection. A mailbox-scoped session advisory
lock prevents another process from capturing it concurrently. Unlike the earlier pool
proposal, this implementation uses dedicated worker connections plus one short-lived
supervisor connection; provision PostgreSQL capacity accordingly.

IDLE notifications trigger scans, with a 60-second safety reconciliation and immediate
catch-up on reconnect. Servers without IDLE use the reconciliation interval. Batches
remain limited to 50 messages, but the observer drains further batches automatically.
Failures reconnect with exponential backoff and jitter, capped at about five minutes.
Missing checkpoints and mailbox-identity changes are retried every minute without
resetting the baseline. `last_error_code` records worker faults when the database is
reachable; a successful scan clears it.

The supervisor rereads enabled accounts/folders every five seconds. Disabling or
changing a mailbox stops its worker before a replacement starts. A scan already in
progress may finish first. A newly enabled mailbox must already have an explicitly
initialized checkpoint. Credentials must be mounted into the container; changing
Compose secret mappings requires container recreation. Do not repoint an existing
mailbox record at an unrelated source while retaining its checkpoint.

Compose settings: `MAX_MAILBOX_WORKERS=8` (accepted range 1–32) and
`RECONCILE_SECONDS=60` (accepted range 10–1740). Additional enabled mailboxes beyond
the worker limit remain unscheduled and produce capacity warnings. Each worker can
hold one bounded capture transaction; memory use increases with concurrent mailboxes.

Logs include an ISO 8601 UTC timestamp with millisecond precision (ending in `Z`),
IDs, counts, and safe error codes, not message contents. `scan_committed`
indicates progress; `mailbox_retry` requires attention if persistent. A running
container alone does not prove healthy capture. A Docker health probe checks progress
as described below; automatic alerts are not implemented. Shutdown signals stop workers, with a bounded 25-second
join period; interrupted database transactions roll back on connection loss.

Stop the observer before manually running `capture-once` or `init-mailbox` against
an actively owned mailbox, otherwise the ownership lock will reject the command.

## Setup and connection checks

Run these from this directory in PowerShell, with Docker Desktop running:

```powershell
docker compose up -d --wait postgres
docker compose config --quiet
docker compose build receiver
docker compose run --rm --no-deps receiver check-db
docker compose run --rm --no-deps receiver check-imap
```

For the current banking inbox, setup and checkpoint initialization are already done.
Normally, leave the observer running. Manual `capture-once` as described below saves emails newer than the checkpoint into
PostgreSQL and leaves read/unread flags unchanged. Repeating it does not duplicate
the same mailbox UID. A second delivery with a different UID is a separate source record.

The image default prints help, while Compose overrides it with `observe` and restarts
the service unless stopped. Explicit one-shot commands still exit when finished.
Connection checks do not initialize checkpoints or enable accounts.

## Current limits

- **One mailbox per manual invocation:** defaults to BANKING_IMAP_PASSWORD / INBOX.
  Use `--credential-ref OTHER_PASSWORD --folder "Bank Alerts"` for another configured
  mailbox, with its secret mounted and checkpoint initialized separately.
- **Explicit commands can access disabled accounts:** enabled flags are reserved for
  automatic workers; they do not block these targeted setup/capture commands.
- **Up to 50 messages per run:** repeat while the summary reports `more_pending: True`.
- **10 MiB source limit per email:** larger mail produces an `oversized` metadata record,
  not a full saved source. The checkpoint advances past it; manual recovery is required.
- **Parsing problems:** `parse_failed` records retain raw evidence; normal capture does
  not automatically retry parsing. Attachment metadata is stored separately; original
  attachment bytes remain within the raw email.
- **No historical import:** initial checkpoint skips existing mail. Later downtime is
  recoverable only while newer messages remain on the IMAP server.
- **Mailbox resets stop capture:** UIDVALIDITY changes require manual reconciliation.
- **ASCII folder names only** in the current command interface.
- **No n8n, LLM, or Actual integration** at this stage. No automatic retention cleanup.

Preserve `.env`, the `secrets/` files, and the PostgreSQL volume. Never use
`docker compose down -v` as routine shutdown: it deletes the database volume.

## Checkpoint initialization

```powershell
docker compose run --rm --no-deps receiver init-mailbox
```

This is an explicit database write. The first run saves the current UIDVALIDITY and
UIDNEXT minus one. Existing mail is skipped; mail arriving after selection is eligible
for future capture. Repeated runs leave an existing checkpoint unchanged. Checks do
not initialize checkpoints or enable accounts. Keep newly arriving mail in the inbox.

Target another registered mailbox with `--credential-ref SOME_PASSWORD --folder "Bank Alerts"`.
Set `SOME_PASSWORD_FILE` to its mounted secret path in Compose. Disabled accounts may
be explicitly tested or initialized. Current diagnostic folder handling supports ASCII
folder names; internationalized IMAP folder encoding is deferred.

## One-time capture

After initializing the checkpoint and sending a test email:

```powershell
docker compose run --rm --no-deps receiver capture-once
```

This explicitly targets the configured mailbox even if the account is disabled.
It requires an existing checkpoint and refuses UIDVALIDITY changes. Each invocation
captures up to 50 newer messages using read-only selection and BODY.PEEK, saves source
bytes, parsed fields and attachment metadata, and commits them with the checkpoint.
Run again if more_pending is True. A later invocation skips already examined UIDs;
database uniqueness also protects replay. No subjects or bodies are printed.

The 10 MiB source limit produces an oversized metadata-only record for larger messages.
MIME defects produce parse_failed records retaining original bytes. SQL-unsafe NUL
characters are replaced in parsed fields only. Original bytes remain unchanged.
Read flags are compared before/after, but other clients may independently change them.
Each bounded run holds a transaction and mailbox lock during network operations;
further resource hardening remains future work.

## Capture results and recovery

The command prints counters after the database transaction commits:

| Field | Meaning |
|---|---|
| examined | Messages processed during this invocation |
| inserted | New source records inserted; replay conflicts do not increase this count |
| parse_failed | Messages retained with MIME parsing defects or errors |
| oversized | Messages recorded as metadata-only because of the size limit |
| seen_unchanged | Messages with the same read flag before and after capture |
| unread_before / unread_after | Unread counts among the messages examined |
| more_pending | More messages from the scanned range remain beyond this run's limit |

If a fetch or database operation fails, the transaction rolls back, including its
checkpoint advancement. Resolve the reported connection or data issue and rerun the
command. Previously committed captures remain intact. A changed UIDVALIDITY requires
investigation; do not delete the checkpoint as a workaround, since reinitializing
would skip mail currently present. Deleted-before-capture mail cannot be recovered.

An oversized or parse_failed record is a committed exception, so repeating normal
capture will not repair it. Preserve the original server message for oversized-mail
recovery. Retained raw bytes can support future reparsing of parse_failed records.

## Verification

Unit tests without database fixture writes:

```powershell
docker compose run --rm --no-deps --entrypoint python receiver -m unittest discover -s tests -v
```

Tests with temporary PostgreSQL fixtures and permission checks (all fixture writes
are rolled back). Run these through the separate administration service:

```powershell
docker compose run --rm --no-deps -e RUN_DB_TESTS=1 -e RUN_ROLE_TESTS=1 --entrypoint python admin -m unittest discover -s tests -v
```

## Files and credentials

- `.env` retains PostgreSQL configuration; do not share it.
- `secrets/` retains mounted passwords; exact bytes are preserved.
- `001_initial_schema.sql` currently contains account-registration SQL despite its
  filename. It was preserved as user input. Do not rerun it: it can create duplicates.
- Planning documents: `../docs/imap-receiver/`.
- `../imap-listener/` is an older, separate JavaScript prototype, not used by this service.

IMAP is selected read-only over certificate-verified TLS. Diagnostics do not fetch
message bodies or modify flags. No listener service or checkpoint command is run
automatically during image builds.

## Database roles and administration

The receiver uses `imap_receiver_runtime`, a non-superuser login. Its password is read
from `/run/secrets/receiver_db_password`, mounted from the ignored local file
`secrets/receiver_db_password.txt`. The administrator password is not passed to the
receiver service. Existing `.env` credentials remain for PostgreSQL initialization and
the explicitly invoked administration service.

| Object | Runtime permissions |
|---|---|
| accounts | SELECT |
| mailboxes | SELECT; UPDATE only uid_validity, last_uid, initialized_at, last_scan_at, last_error_code |
| emails | SELECT and INSERT |
| attachments | SELECT and INSERT |
| Schema | USAGE, no CREATE grant |

The role cannot change account enable flags, folder paths, stored email content, or
delete/truncate receiver records. It owns no receiver tables and has no superuser,
database-creation, role-creation, replication, or RLS-bypass attribute. Explicit
checkpoint initialization remains allowed; a runtime role necessarily can advance
checkpoints, so its credentials still require protection. PostgreSQL's ordinary PUBLIC
privileges (for example temporary objects and built-in functions) are not globally
revoked by this change.

Provisioning is performed separately, never during observer startup:

```powershell
docker compose build receiver admin
docker compose run --rm --no-deps admin
```

The admin service belongs to the maintenance profile and is not started by ordinary
`docker compose up`. An explicit `run admin` invokes provisioning. The script reuses
the mounted runtime password, creates/updates the role and grants, and leaves existing
accounts, emails, and checkpoints intact. It refuses an existing role with memberships
or object ownership that needs manual investigation. Do not regenerate the secret on
every startup. For password rotation, change the local file, run provisioning, and
recreate the receiver; retain a secure rollback copy until verification completes.

For emergency rollback, restore receiver PGUSER/PGPASSWORD to the bootstrap `.env`
settings and remove PGPASSWORD_FILE from that service, then recreate only receiver.
This deliberately restores broader privileges and should be temporary. Do not delete
the database volume or change mailbox checkpoints to troubleshoot authentication.

Tested backups and reproducible schema migrations remain pending.

## Health checks

Check Docker's status and run the probe inside the running receiver:

```powershell
docker compose ps receiver
docker compose exec receiver python -m src.health
```

Expected output for the active inbox:

```json
{"healthy": true, "mode": "observing", "enabled_mailboxes": 1, "reasons": []}
```

Use `exec`, not `run`: the probe must inspect the observer's container-local heartbeat.
A separate one-off container has no observer heartbeat and should fail this check.
The probe exits 0 when healthy and 1 otherwise. It does not connect to IMAP, mark mail
read, or write database rows. It uses the same restricted runtime role with SELECT only.

The supervisor atomically publishes `/tmp/imap-receiver-health.json` normally every
five seconds. This records its PID, monotonic heartbeat, and worker progress. The file
is not a checkpoint and does not need to be backed up. A stopped observer is explicitly
marked. Worker retry errors clear only after a successful scan. The probe checks:

- Observer PID exists, supervisor heartbeat is no older than 30 seconds, and no
  supervisor error/stopped marker is present.
- Every enabled mailbox has a live, non-stopping worker that has scanned successfully
  in this process; historical database timestamps cannot substitute for this.
- Each enabled mailbox is initialized, has no stored error, and has a recent database
  scan timestamp. Defaults allow up to max(180 seconds, three reconciliation intervals).
- Database connection and SELECT complete within their three-second timeout settings.

`HEALTH_SCAN_MAX_AGE_SECONDS` can override scan freshness; add it to receiver environment
if needed. It must be at least RECONCILE_SECONDS and at most 86400. A long scan/backlog
or reconnect delay can make health fail even when recovery is underway; this is deliberate
visibility, not proof of lost mail. The supervisor has a separate fixed freshness limit.

Zero enabled mailboxes reports healthy with `mode: idle` when supervisor and database
are healthy. Enabled but unscheduled mailboxes (including worker-capacity overflow)
report unhealthy. Configuration changes may briefly show missing/stopping workers until
the next refresh and first successful scan.

Docker probes every 30 seconds, allows 10 seconds per probe, and requires three consecutive
failures after a 60-second startup grace to mark the container unhealthy. A successful
probe restores healthy status. `restart: unless-stopped` does **not** automatically restart
a running unhealthy container, and this feature sends no notifications.

Common reason codes: supervisor_stale, supervisor_error, worker_missing,
worker_stopping, worker_retry, worker_not_scanned, worker_scan_stale, checkpoint_required,
mailbox_error, database_scan_stale, heartbeat_missing, observer_missing, and probe_failed.
Output includes mailbox IDs and safe error types only, never credentials or email content.
Investigate the receiver logs and database scan status before restarting or changing state.
