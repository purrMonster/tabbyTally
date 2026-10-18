# IMAP receiver — usage and operations

## Development checkout status

The observer, snapshot backups, restore verification, and versioned schema setup are
implemented and tested. Database installation and existing-schema adoption are described
below. Account registration and secret provisioning remain explicit operator steps.
`examples/register_account.sql` is a one-time account-registration example, not a
migration; it replaces the misleading historical `001_initial_schema.sql` filename.
Do not rerun registration against an existing configured inbox.

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
- `migrations/001_initial.sql` contains versioned schema DDL (no account data).
- `examples/register_account.sql` is a one-time registration example; rerunning it
  creates duplicates. Customize only a local ignored copy with your mailbox address.
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

Snapshot backup/restore verification and versioned schema migration commands are below.

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

## Snapshot backups and restore verification

Run these commands from `imap-receiver/` with PostgreSQL running:

```powershell
docker compose build backup
docker compose run --rm --no-deps backup create --verify
```

A successful command emits `backup_created`, then `restore_verified` with
`temporary_database_removed: true`, and exits zero. `backup_created` alone confirms
archive creation, not a tested restore. Any failure exits nonzero. The service is
maintenance-only, has no IMAP credentials, and never starts an observer. It uses the
bootstrap database administrator because it must create/drop its own test database.
Do not run `docker compose config` in shared logs: configuration may expose passwords.

Files appear in the local, Git-ignored and Docker-build-excluded `backups/` directory:

- `receiver_<UTC timestamp>_<random id>.dump`: compressed PostgreSQL custom archive.
- The same basename with `.json`: archive SHA-256 and expected schema/table fingerprints.
- The same basename with `.verified.<random id>.json`: successful comparison and cleanup.

The dump contains private emails and mailbox configuration. It is **not encrypted**.
The manifest contains counts/hashes, not email contents, but keep the files together and
private. Container file creation uses a restrictive umask; on Windows, host filesystem
ACLs govern access. No archive, manifest, or password file belongs in Git. Verify ignore
rules with `git status --ignored --short`; do not force-add private files.

To create without the restore rehearsal, or re-verify a particular trusted archive:

```powershell
docker compose run --rm --no-deps backup create
docker compose run --rm --no-deps backup verify <archive-filename.dump>
```

Replace the angle-bracket placeholder with the exact basename printed by creation;
paths and arbitrary filenames are rejected. Keep its matching `.json` alongside it.
Only verify locally generated archives you trust: restoration executes SQL. Checksums
help detect accidental corruption; they do not authenticate an archive against someone
who can replace both the archive and its manifest. Re-verification creates a new report.

### Snapshot and comparison guarantees

The manifest and pg_dump share an exported repeatable-read snapshot. Mail capture can
continue, and messages captured after that snapshot belong to the next backup. Do not
run schema migrations concurrently. Schema locks have a ten-second dump wait limit;
tool subprocesses have a 30-minute timeout. Fingerprinting streams rows, but one large
email row still consumes memory and hashing/scans add database load. There is no overall
job deadline or automatic retention policy; budget disk space for both archive and test
restore, and arrange scheduling separately.

The archive includes the `imap_receiver` schema. Verification supports accounts,
mailboxes, emails, attachments, and the schema_migrations ledger when present. Older
four-table archives remain verifiable. It compares column types/defaults/nullability,
constraints and indexes, plus deterministic SHA-256 fingerprints of every full row.
That includes account configuration, IDs, checkpoint/UIDVALIDITY fields, scan timestamps,
raw and parsed mail, and attachment metadata. It independently recomputes the raw-email
hashes. Oversized metadata-only messages have no raw payload to check. The receiver
stores attachment metadata and original MIME mail, not separate attachment binary files.
Future schema changes must extend this verifier before claiming coverage for new objects.

A new randomly named `imap_restorecheck_<id>` database is created from template0, with
PUBLIC connect revoked. Restoration uses one transaction, without original owners or
ACLs. It never uses `--create`/`--clean` or a caller-specified restore target. The generated
database is dropped after success or failure; existing-name collisions fail without
cleanup of that existing database. No test IMAP connection is made. A success report
requires comparison **and** database removal. Ownership, grants, functions, triggers,
sequences, extensions, database settings, and outside-schema dependencies are not part
of the current structural comparison contract; restore errors still fail verification.

### Failures and recovery boundaries

A missing manifest, changed archive checksum, unsupported table layout, raw-hash mismatch,
restore failure, or data/schema mismatch fails the operation. Error output contains safe
exception classes, not SQL or email content. PostgreSQL tool stderr is deliberately not
printed; warnings also fail the operation. Investigate privately rather than enabling
verbose logging of sensitive source data in a shared session.

An interrupted creation can leave `.dump.partial` or a dump without a manifest. These
are incomplete and cannot be verified; preserve them for investigation or remove only
the exact known incomplete files. Do not delete the last verified backup. On ordinary
restore failures cleanup runs; a killed process, host crash, or lost database connection
can leave its generated test database. `restore_cleanup_failed` includes the safe test
database name when cleanup itself fails. Inspect for leftovers with:

```powershell
docker compose exec -T postgres psql -U imap_receiver -d imap_receiver -c "SELECT datname FROM pg_database WHERE datname LIKE 'imap_restorecheck_%';"
```

These example user/database names match the local setup; adjust for your deployment.
Before removing any leftover, confirm the exact name belongs to an interrupted verification
and no active verifier is using it. Never use wildcard deletion or remove the live database.
The verifier shares the existing cluster, so this rehearsal does not test recovery after
loss of the Docker host, PostgreSQL installation, or administrator credentials.

The archive excludes other schemas, database-role definitions/passwords, `.env`, mounted
secret files, Compose configuration, and database-wide settings. Preserve required
configuration and secrets separately in secure storage. A full recovery should restore
into a new isolated deployment, provision the runtime role/grants with the existing
administrator tool, verify data, and check credentials/configuration before starting one
observer. Do not reinitialize restored checkpoints: that could skip mail after the backup.
Do not connect a second observer to the same inbox as part of a restore rehearsal.

Full disaster recovery, off-host encrypted copies, backup frequency, retention, and
recovery-time objectives remain to be agreed and tested. A local verified archive alone
will not survive loss of this host. Schema migrations are documented below;
no destructive live-restore command is provided here.

Implementation reference: PostgreSQL 17 [pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html)
and [pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).

## Versioned schema installation and upgrades

Run migration commands explicitly through the administrator service. The observer never
runs DDL. Build updated images before applying migrations; a container built from older
source cannot see newly added migration files. Required local `.env` and runtime-secret
files must already exist (see the credential section). Start PostgreSQL only first:

```powershell
docker compose up -d --wait postgres
docker compose build admin backup receiver
docker compose run --rm --no-deps --entrypoint python admin -m src.migrate status
```

For a fresh database, status reports `empty`. Install its schema with:

```powershell
docker compose run --rm --no-deps --entrypoint python admin -m src.migrate apply
docker compose run --rm --no-deps admin
```

The first command installs the baseline and migration ledger; the second provisions the
restricted runtime role using the already configured secret. The schema migration creates
no mailbox/account rows, initializes no checkpoint, and has no IMAP connection. On a fresh
installation, register your account separately using an ignored local copy of
`examples/register_account.sql`, initially disabled. Replace its placeholder mailbox
address privately. It is a one-time INSERT, not idempotent configuration synchronization.
Do not copy credentials into tracked SQL. The schema contains no IMAP password column.

For example, after preparing `exports/register_account.local.sql` with the intended
mailbox address, run it once through the existing database service (adjust database/user
names if yours differ):

```powershell
Get-Content -Raw .\exports\register_account.local.sql | docker compose exec -T postgres psql -U imap_receiver -d imap_receiver -v ON_ERROR_STOP=1
```

Follow the existing check-db, check-imap, and init-mailbox instructions before enabling
that registered account. Initialization establishes the new-mail cutoff, so choose its
timing deliberately. For the default single banking account, enabling is an explicit
administrator SQL update to `accounts.enabled`; the mailbox defaults to enabled. Start
the observer only after that configuration is ready. Do not re-register or reinitialize
an already working inbox during an upgrade.

### Existing databases and baseline adoption

Before applying changes, create and verify a backup. If status reports `unversioned`,
the database matches the legacy schema but has no migration ledger. Adopt it explicitly:

```powershell
docker compose run --rm --no-deps backup create --verify
docker compose run --rm --no-deps --entrypoint python admin -m src.migrate apply --adopt-existing
docker compose run --rm --no-deps --entrypoint python admin -m src.migrate apply
docker compose run --rm --no-deps backup create --verify
```

Adoption verifies the baseline then adds one history row; it does not recreate existing
tables or touch accounts, mail, attachments, or checkpoints. The repeat apply must report
`applied_now: 0`. This local deployment is already adopted at version 1. The live adoption
was additionally wrapped in short-lived SHARE locks and complete before/after fingerprints
of the four application tables, proving those rows remained identical within the operation.
The standard runner itself does not acquire these extra application-table locks.

Subsequent upgrades use `apply` after reviewing and testing new migrations. Do not run
migrations concurrently with backups or manual schema edits. Plan observer downtime if a
future migration changes tables used by capture; this first adoption needed no restart.
There is no automatic downgrade, destructive reset, or repair-by-overwrite command.
A failure rolls back the transaction, including newly created schema/history. If drift
or history mismatch is reported, investigate privately; do not delete history or edit
old checksums to bypass validation.

### Migration contract and test scope

Files are contiguous `NNN_name.sql` plus matching `.json` metadata specifying the expected
application-schema fingerprint. The ledger records version ID, filename, SHA-256, applied
time, and whether the baseline was adopted. The checksum covers normalized SQL and the
expected fingerprint, so Windows CRLF versus Linux LF does not change it. Applied files
are immutable: add a new migration instead of editing an existing one. SQL must be
transaction-safe and must not contain BEGIN/COMMIT, psql commands, or role provisioning.
The baseline targets PostgreSQL 17 and uses its built-in UUID generation.

A transaction-scoped advisory lock serializes migration commands. Lock timeout is five
seconds and SQL statement timeout is 60 seconds. Status does not create objects. It checks
history and supported schema structure, and currently performs the same full-row/raw-hash
scan as backup fingerprinting. On large mailboxes this has cost and may hit the statement
timeout; do not treat it as a lightweight health probe. Health checks remain separate.

Current drift validation covers application table columns/defaults, constraints and indexes;
it is not a general audit of grants, functions, triggers, or all PostgreSQL objects. The
ledger is protected by administrator ownership and has no runtime write grants. Its own
structure is included in backup verification, while migration application-schema fingerprints
exclude it. Future table additions require extending the backup/verifier contract as well
as adding the migration. Review schema fingerprints against a disposable database, never
by copying an arbitrary drifted live database's hash to make an error disappear.

Run the full suite, including tests that create and remove isolated databases:

```powershell
docker compose run --rm --no-deps -e RUN_DB_TESTS=1 -e RUN_ROLE_TESTS=1 -e RUN_MIGRATION_TESTS=1 --entrypoint python admin -m unittest discover -s tests -v
```

The migration tests use generated `imap_migrationtest_<id>` databases only, and never
point a receiver at them. The fresh baseline, repeat run, explicit adoption/data preservation,
drift and history rejection, rollback, concurrent-runner exclusion, and line-ending
portability are verified. Cleanup runs on normal failures; killed processes may leave a
test database requiring the same careful exact-name inspection as restore leftovers.
The verified live state has one account, one mailbox, four emails and one migration row.
A complete host-loss recovery rehearsal and automatic account onboarding are separate work.
