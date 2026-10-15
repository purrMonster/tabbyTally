# TabbyTally IMAP receiver — runbook and dated session record

Recorded: **15 October 2026**, user timezone **Asia/Calcutta (IST, UTC+05:30)**.
Entries below are chronological within this date; exact event times were not recorded
for every step. Observer logs deliberately use UTC, independently of this document.

Expanded on the same date at the user's request for an extremely descriptive record.
This is a decision history, implementation handoff, and operating reference—not a
verbatim transcript. It deliberately omits credential values, private message contents,
and unrelated account information. Nothing in this documentation update changes the
running service, grants a role, initializes a checkpoint, or performs a migration.

## Navigation and evidence conventions

Read the current-state summary first, then the dated narrative. The detailed appendices
provide the exact runtime model, schema dictionary, test evidence, troubleshooting,
deferred financial workflow, and next-session acceptance criteria.

| Label used in this document | Meaning |
|---|---|
| User decision / confirmed requirement | Explicitly chosen or clarified in this conversation |
| Implemented | Present in the files inspected for this record |
| Live verified | A command result against this Docker/PostgreSQL/Purelymail setup was inspected |
| User-reported | The user reported the outcome; it was not independently repeated afterward |
| Simulated / automated | Exercised with fixtures or mocks; scope is specified |
| Proposed / deferred | Discussed but not implemented or not yet selected |
| Code observation | Found by reading code during this documentation pass; not a new live test |

Avoid turning a proposed design into a claim of live capability. In particular, an
existing Docker image, a green mocked test, and a live provider test establish different
things. Historical message counts are observations at those times, not current totals.

### Quick links

- [Current-state handoff](#read-this-first-when-resuming)
- [Chronological workflow discussion](#2026-10-15--original-workflow-discussion)
- [Operating commands](#operating-commands)
- [User intent and corrections](#a-user-intent-interaction-preferences-and-corrections-to-preserve)
- [Architecture choices](#b-architecture-decisions-and-the-alternatives-in-more-detail)
- [Deployment and configuration](#c-current-deployment-inventory-and-configuration-semantics)
- [Complete schema dictionary](#d-complete-schema-dictionary-and-integrity-model)
- [Command and worker behavior](#e-exact-python-command-behavior)
- [Code observations and gaps](#f-code-observations-and-gaps-that-must-not-be-hidden-by-the-handoff)
- [Verification ledger](#g-verification-ledger-exactly-what-evidence-exists)
- [Logs and incident triage](#h-log-interpretation-and-incident-triage)
- [Deferred downstream contracts](#i-downstream-integration-contract-to-preserve-for-later)
- [Next-work acceptance criteria](#j-next-work-concrete-acceptance-criteria-without-doing-it-yet)
- [Session continuity checklist](#k-session-continuity-checklist)

## Read this first when resuming

**Most recent update, 15 October 2026:** schema migrations are implemented and live
adopted at version 1. All 41 tests passed. Before/after application-table fingerprints
matched, repeated application made no changes, and post-adoption backup restoration
verified the migration ledger too. Observer remains healthy with one inbox. Next:
downstream durable jobs and n8n integration. See the dated migration records at the end.
Earlier status statements below are historical. Off-host encrypted backups and a full
host-loss recovery rehearsal remain pending.

**Health-check work started, 15 October 2026:** user approved proceeding and requested
runbook updates at each step. Design: a local atomic supervisor/worker heartbeat plus
read-only PostgreSQL checks, surfaced through Docker health status. No notification or
automatic unhealthy-container restart is implied. Implementation/testing/deployment
results will be appended separately below.

**Latest update, 15 October 2026:** the restricted runtime-role step below has now been
implemented; see the dated addendum at the end. Earlier sections are preserved as the
historical state at their creation. The observer now uses imap_receiver_runtime, and
the next remaining operational work is health checks, then tested backups.

The Python IMAP receiver has been built and started on Windows Docker Desktop.
One dedicated Purelymail INBOX is enabled. It observes new messages, stores original
email and parsed data in PostgreSQL, and leaves read/unread flags unchanged.
Automatic capture and downtime catch-up were verified. The user wants **one inbox
for now**; do not make adding a second account the next prerequisite.

The latest suggested next step is a **restricted PostgreSQL runtime role**, followed
by receiver health checks and tested backups. These were discussed but have **not**
been implemented. The present request is to record the handoff, not to do that work.

The overall product goal remains banking email → local LLM → Actual Budget, with
n8n orchestrating downstream processing. Only the receiver and its storage are
implemented. Do not claim the budgeting pipeline is operational.

## Workspace and artifact map

Project: `C:\Projects\tabbyTally`

| Path | Purpose / status |
|---|---|
| `imap-receiver/` | Current Python implementation and Docker Compose stack |
| `imap-receiver/src/cli.py` | Connection checks, explicit checkpoint initialization, command dispatch |
| `imap-receiver/src/capture.py` | Bounded capture, MIME parsing, source storage, transactional checkpoint updates |
| `imap-receiver/src/observer.py` | Supervisor, mailbox threads, IDLE, retries, timestamped logs |
| `imap-receiver/tests/` | Setup, parsing, transactional capture, and observer tests |
| `imap-receiver/README.md` | Full usage, limits, results, and recovery guidance |
| `docs/imap-receiver/IDEATION.md` | Problem, scope, alternatives, decisions |
| `docs/imap-receiver/DESIGN.md` | Architecture, schema, and intended behavior |
| `docs/imap-receiver/PLAN.md` | Build stages and progress |
| `imap-listener/` | Earlier JavaScript/webhook prototype; unused by current service, preserved |
| Root `README.md` | Broader original roadmap; may still mention earlier choices such as Ollama |

Planning documents were initially created inside imap-receiver; they were subsequently
found under docs/imap-receiver. Use their current locations. Some planning text may
describe intended behavior beyond the implementation; current code and receiver README
take precedence for operating instructions.

At the last repository inspection, `docs/`, `imap-listener/`, and `imap-receiver/`
were untracked. No commit or push was performed in this session.

## 2026-10-15 — original workflow discussion

The user requested an n8n workflow from scratch and invited requirements questions.
The intended chain was a dedicated banking-email inbox → extraction through a local
model behind llama-swap → Actual Budget updates.

Requirements established:

- Purelymail IMAP; bank emails delivered directly, not forwarded.
- Self-hosted n8n, llama-swap, and Actual Budget on different fleet machines in the
  same subnet, with Traefik per node.
- HDFC, Axis, and ICICI savings/card/loan-related transactions are relevant.
- Overseas purchases are on Indian cards; these are not foreign-currency bank accounts.
- Valid transactions should import automatically; ambiguous cases go to review.
- Actual's rules should categorize transactions.
- No other transaction-entry sources were planned for v1. The user's earlier
  “No auto add for v1” answer was clarified to mean no other entry sources, not a ban
  on automatic validated imports.
- Support own-account transfers and credit-card repayments without double-counting.
- Loan payments are expense-only in v1; principal/interest debt tracking is deferred.
- Actual has no end-to-end encryption in this setup.
- An API wrapper was initially reported present, then corrected: **none exists**.
- Messaging app is under development and can adopt the required review callbacks.
- PostgreSQL was not available initially.
- Capture new mail only, not historical inbox contents.

Proposed downstream design, still unimplemented:

1. Extract structured facts and supporting evidence locally, without agent access to
   budget credentials.
2. Validate amounts, dates, currency, account mapping, transaction status, and duplicates
   using code; do not rely solely on an LLM confidence score.
3. Map bank/account/card suffixes to Actual account IDs explicitly.
4. For overseas purchases, use the billed INR amount and retain foreign amounts in
   notes. Hold for review when the INR amount is missing; do not invent an exchange rate.
5. Use linked transfers for movements between owned accounts and card repayments.
   Match paired bank alerts rather than importing twice. Amount/date alone is insufficient.
6. Add a small HTTP bridge using Actual's official Node.js `@actual-app/api` package;
   Actual's official API is not itself a general REST transaction endpoint.
7. Messaging review actions: approve, correct, ignore, link existing. Authenticate
   callbacks, use unique decision IDs and review versions, and reject stale decisions.
8. Learn through reviewed examples, explicit mappings, and tested parsing changes;
   fine-tuning and unchecked broad rule creation are not v1 requirements.
9. Recover uncertain Actual write outcomes by request identity before retrying.

## 2026-10-15 — receiver boundary and technology decisions

The user questioned n8n email latency. We established that Purelymail supports IDLE
and n8n's IMAP trigger can listen continuously; moving capture out of n8n is chiefly
about independent operation and recovery, not a proven inherent speed improvement.

An initial Node.js prototype used ImapFlow, PostgreSQL, and authenticated n8n webhook
delivery. It built successfully and passed four checkpoint tests. It was not fully
validated for production capture.

The user then selected a more generic boundary:

```text
IMAP mailbox → receiver → PostgreSQL
                              ↓ later
                       n8n / other consumer
```

No n8n webhook, model, or Actual logic belongs in the receiver. Consumers observe
new row inserts; email primary keys are immutable. Consumer state belongs separately.
LISTEN/NOTIFY was discussed as a future wakeup mechanism, with durable row queries for
catch-up because notifications are not retained across disconnects. n8n's Postgres
Trigger supports Listen to Channel; testing it was explicitly postponed.

Alternatives investigated:

- ImapFlow: reusable IMAP library, used by EmailEngine and the initial prototype.
- Mail-Archiver / MailFathom: broader archiving applications; not verified as exact
  drop-in fits for new-mail-only low-latency ingestion.
- EmailEngine: broader API platform, with Redis-backed queues and custom Lua operations.
  Replacing Redis with PostgreSQL would be a substantial fork, not a storage toggle.
  Its commercial source-available license also applies to modified versions.
- Redis versus PostgreSQL: chose PostgreSQL alone for durable email evidence,
  checkpoints, uniqueness, and transactions. Redis adds no necessary capability here.

The user selected **one container managing multiple accounts/mailboxes**, using
independent workers. A shared pool was initially proposed. Current implementation
instead pins one database connection per worker for session locks, plus a short-lived
supervisor connection. This deviation is documented in the README.

## 2026-10-15 — database setup and troubleshooting

User selected Windows Docker Desktop with Linux containers. PostgreSQL 17 was started
through Compose with a persistent named volume and no published host port.

Database: `imap_receiver`. Bootstrap database owner: `imap_receiver`.
Schema: `imap_receiver`.

Password generation initially used newer .NET APIs unavailable in Windows PowerShell
5.1. The working replacement used `RandomNumberGenerator.Create()`, a byte array,
instance `GetBytes()`, and BitConverter hex conversion. Credentials were saved locally
in `.env`; they are not included here.

Large interactive SQL pastes displayed corruption ending in `^C`. We switched to
editing SQL in Notepad, `docker compose cp`, and `psql -X -v ON_ERROR_STOP=1 -f`.
Re-execution reported the schema already existed. Inspection showed all four tables,
columns, indexes, and constraints were already created correctly; nothing was dropped.

Schema approved and verified:

| Table | Contents and key constraints |
|---|---|
| accounts | UUID, label, IMAP host/port, username, credential_ref, enabled, created_at |
| mailboxes | Account FK, folder, enabled, UIDVALIDITY/last UID/initialization checkpoint, scan/error state; unique account+folder |
| emails | Mailbox FK, UID generation and UID, headers, dates, JSON addresses, bodies, raw bytes/hash, size, capture status/error/parser version; unique mailbox+UIDVALIDITY+UID |
| attachments | Email FK, attachment ordinal, filename/type/size/content ID/hash; unique email+ordinal |

UID fields are BIGINT with IMAP bounds; initial last_uid can be zero. Checkpoints are
either uninitialized or consistently populated. Message-ID is nullable and not unique.
Raw bytes/hash are required except for explicit oversized captures. JSON address fields
must be arrays. Foreign keys restrict accidental deletion; no cascading cleanup exists.

The first account, labelled “Banking inbox”, was registered disabled with an enabled
INBOX row and credential reference `BANKING_IMAP_PASSWORD`.

**File naming issue:** `imap-receiver/001_initial_schema.sql` currently contains the
account-registration INSERT, not the initial CREATE TABLE migration. It was preserved.
Do not rerun it: it can add duplicate account records. A proper reproducible migration
set remains unfinished work; do not assume the filename contains the schema.

## 2026-10-15 — credentials and initial JavaScript checks

The user saved the mailbox password with a masked PowerShell prompt into:
`imap-receiver/secrets/banking_imap_password.txt`.

The file preserves exact UTF-8 password bytes, without a trailing newline. Compose
mounts it at `/run/secrets/banking_imap_password`, referenced through
`BANKING_IMAP_PASSWORD_FILE`. `.env` and `secrets/` are excluded from Git and build context.
These are local plaintext files, not an encrypted secret vault.

Node.js connection checks succeeded:

- PostgreSQL account/mailbox query worked.
- Purelymail authentication succeeded.
- INBOX opened read-only.
- 250 existing messages were reported at that point.
- IDLE support was present.

No bodies were fetched by those connection checks.

## 2026-10-15 — switch to Python

The user asked about Python, then explicitly authorized autonomous file deletion and
modification to reach the same milestone, with verbose progress updates.

Changes performed:

- Replaced JavaScript checks in imap-receiver with Python commands.
- Removed that directory's package.json and package-lock.json.
- Changed Docker base to `python:3.14-slim-bookworm`.
- Added `psycopg[binary]==3.3.3`.
- Used Python 3.14 standard-library imaplib, which supports IDLE, and email for MIME.
- Explicit `ssl.create_default_context()` enables certificate/hostname verification.
- Preserved existing PostgreSQL data, schema, account rows, secret files, and config.
- Left the separate earlier imap-listener prototype unused and unchanged.
- Added check-db, check-imap, and explicit idempotent init-mailbox commands.

Six initial Python tests passed. Python live database and read-only IMAP checks also
passed, still reporting 250 messages. No checkpoint existed at that verification.

Checkpoint semantics were explained: initialization saves UIDNEXT minus one and current
UIDVALIDITY; existing messages are excluded. Repeated initialization preserves an
existing checkpoint. The user later confirmed sending a test email **after** initialization.

## 2026-10-15 — capture-once milestone

Implemented capture-once with:

- Explicit target mailbox, even if automatic capture is disabled.
- Existing checkpoint requirement; no implicit baseline.
- Read-only IMAP selection and BODY.PEEK retrieval.
- Bounded UID search and at most 50 messages per invocation.
- Metadata-first fetch and partial source request; 10 MiB source limit.
- MIME headers, addresses, plain/HTML bodies, attachment metadata, raw source/hash.
- `captured`, `parse_failed`, and `oversized` outcomes.
- NUL replacement in parsed SQL text/JSON only; original bytes remain intact.
- Source records and checkpoint advancement in one database transaction.
- Advisory lock plus unique source constraint for safe replay.
- Read-flag comparison before and after retrieval.

Eleven tests passed, including temporary real-PostgreSQL fixture transactions that
were rolled back. Covered MIME/attachments, malformed MIME, duplicate replay,
rollback after a simulated failure, UIDVALIDITY guard, oversized records, and setup.

Live result: one email examined and inserted, no parsing/size errors, unread before
and after. Database query confirmed one raw source and one parsed text body. Second
run examined and inserted zero messages. These counts describe that test, not a fixed
current total.

The user requested TL;DR usage in chat but **full descriptions in README**. Preserve
that documentation preference.

## 2026-10-15 — continuous observer milestone

Implemented observe and set Compose to run it with `restart: unless-stopped`.

- One supervisor, one independent thread per enabled mailbox of an enabled account.
- Persistent read-only IMAP connection per worker.
- Pinned PostgreSQL connection and mailbox-scoped session advisory lock.
- IDLE EXISTS/EXPUNGE responses trigger scans; periodic catch-up every 60 seconds.
- Immediate catch-up on connect/reconnect; automatically drain additional 50-message batches.
- Supervisor refreshes account/mailbox configuration every five seconds.
- Bounded worker count: default 8, accepted 1–32.
- Reconciliation interval configurable from 10–1740 seconds.
- Independent retries with exponential backoff and jitter, capped around five minutes.
- Missing checkpoint / mailbox generation faults retry every minute without reset.
- Safe error codes persisted where possible; successful scans clear the error.
- Bounded shutdown: workers are signalled, joined for up to 25 seconds; Compose grace is 30 seconds.

Sixteen tests passed, adding simulated IDLE wakeup, ownership conflict, independent
workers, worker capacity, error classification, and backoff checks. Multi-account tests
were simulated; multiple real accounts have not been exercised.

The banking account was enabled and the service started. Live logs showed connection
with IDLE true and a committed scan. A controlled restart logged workers_remaining=0,
then reconnected and scanned without duplicates.

The user sent another message and pasted logs showing:

```json
{"examined":1,"inserted":1,"parse_failed":0,"oversized":0,"seen_unchanged":1,"unread_before":1,"unread_after":1,"more_pending":false}
```

This verifies unattended capture and unread preservation. The logs do not identify
whether this particular scan was triggered by IDLE or the periodic timer; IDLE was
advertised by the server and its wakeup path passed a simulated test.

At the user's request, UTC ISO 8601 timestamps with milliseconds were added to every
observer log event. The image was rebuilt and the live output verified. Example format:
`2026-10-15T05:37:37.972Z`. UTC log timestamps can be converted to IST by adding 05:30.

## 2026-10-15 — downtime test and agreed stopping point

The user followed a stop → send email → start test and reported **passed**. This is
user-reported live downtime catch-up verification; the assistant did not independently
inspect the final test's message contents or counts.

We proposed a second-account/folder test. The user chose **one inbox for now**. Keep
multi-mailbox support in the implementation, but do not expand the active setup without
a new request.

Next work proposed, not executed:

1. Restricted receiver database role (current role is bootstrap owner).
2. Health checks that detect stale or blocked capture, not merely a running process.
3. Backup and restore verification.
4. Later: n8n consumer state and notifications, LLM extraction, review app, Actual bridge.

## Operating commands

Run in Windows PowerShell:

```powershell
Set-Location C:\Projects\tabbyTally\imap-receiver
docker compose ps
docker compose logs -f --tail 30 receiver
```

Routine lifecycle:

```powershell
docker compose stop receiver
docker compose start receiver
docker compose restart receiver
# After code/config changes:
docker compose up -d --build receiver
```

Stopping only receiver leaves PostgreSQL running. **Do not use `docker compose down -v`**
for routine shutdown; it deletes the database volume.

Diagnostics:

```powershell
docker compose run --rm --no-deps receiver check-db
docker compose run --rm --no-deps receiver check-imap
docker compose exec postgres psql -U imap_receiver -d imap_receiver -c "SELECT folder_path, last_scan_at, last_error_code FROM imap_receiver.mailboxes;"
docker compose exec postgres psql -U imap_receiver -d imap_receiver -c "SELECT capture_status, count(*) FROM imap_receiver.emails GROUP BY capture_status;"
```

Manual capture, only when necessary (stop the active owner first):

```powershell
docker compose stop receiver
docker compose run --rm --no-deps receiver capture-once
docker compose start receiver
```

The existing inbox is already initialized. Do not recreate its baseline. For a future
explicitly selected mailbox, init-mailbox is the command that establishes the initial
new-mail cutoff. Both manual commands default to BANKING_IMAP_PASSWORD / INBOX and
accept `--credential-ref` and `--folder`.

Tests:

```powershell
# Unit tests; PostgreSQL fixture test skipped:
docker compose run --rm --no-deps --entrypoint python receiver -m unittest discover -s tests -v
# Include fixture transactions, rolled back afterward (currently needs owner privileges):
docker compose run --rm --no-deps -e RUN_DB_TESTS=1 --entrypoint python receiver -m unittest discover -s tests -v
```

## Recovery rules and known limits

- Preserve the PostgreSQL volume, .env, and mounted credential files. Never print or
  paste passwords into chat or logs.
- Do not rerun account-registration SQL blindly or reset checkpoints to resolve errors.
- Runtime currently uses bootstrap owner permissions; least privilege remains pending.
- PostgreSQL has no published host port; cross-fleet consumers will need a deliberately
  configured private connection, TLS policy, and restricted credentials.
- One active real inbox is validated. Multiple real-account behavior remains unverified.
- ASCII folder names only in the current command interface.
- Oversized records omit raw source, advance the checkpoint, and need manual recovery.
- Parse failures keep raw source, advance the checkpoint, and are not automatically reparsed.
- Deleting source mail before capture makes recovery impossible.
- UIDVALIDITY changes or backwards UIDNEXT block capture; investigate rather than reset.
- Each batch holds a database transaction during network operations. Resource hardening,
  especially aggregate memory at higher worker counts, is still pending.
- The database SELECT/INSERT schema was verified live, but a complete migration history
  and reproducible fresh-install schema file are not yet maintained.
- No automatic retention cleanup, backup job, restored-backup test, alert delivery,
  or receiver Docker health probe exists.
- Observer logs can be verbose during empty periodic scans; this is expected.
- Automated tests use mocks for portions of IMAP; they do not prove every provider edge case.
- No downstream notification, n8n processing, LLM extraction, review callback, or Actual
  write has been implemented by this receiver work.

## Suggested next-session prompt

> Read imap-receiver/runbook.md and the current code. Keep one inbox active. Continue
> with a restricted PostgreSQL runtime role while preserving existing emails,
> checkpoints, secrets, and automatic capture. Explain changes and verify permissions
> and capture behavior. Do not rebuild the schema or initialize a new checkpoint.

## Reference documentation used during the discussion

- [Python 3.14 imaplib](https://docs.python.org/3.14/library/imaplib.html)
- [Psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html)
- [Purelymail features](https://purelymail.com/docs/features)
- [Actual API](https://actualbudget.org/docs/api/)
- [n8n Postgres Trigger](https://docs.n8n.io/integrations/builtin/trigger-nodes/n8n-nodes-base.postgrestrigger/)
- [EmailEngine Redis implementation](https://github.com/postalsys/emailengine/blob/master/lib/db.js)
- [EmailEngine license](https://github.com/postalsys/emailengine/blob/master/LICENSE_EMAILENGINE.txt)

References document prior research, not a fresh compatibility audit. Verify dependency
and deployment details when changing versions.

---

# Detailed handoff appendices — 15 October 2026

## A. User intent, interaction preferences, and corrections to preserve

### A1. The goal and why this component exists

The original request was not merely to archive email. It was to design a working,
self-hosted transaction-ingestion workflow for Actual Budget using banking alerts.
The receiver became a separately scoped component because the user wanted intake to
be generic and independent of n8n. PostgreSQL is the integration boundary.

The receiver must not decide whether an email is a financial transaction. It stores
new mail from configured sources, including non-transaction content, for downstream
classification. An OTP, statement reminder, promotional message, or bank alert may all
be captured as source mail. Capture success means source persistence, not financial
correctness, transaction extraction, or permission to change Actual.

The broader TabbyTally README describes eventual statement reconciliation, a gradual
move from n8n orchestration toward Python, one authority for financial writes, and
preview/assisted/automatic modes. That earlier roadmap also mentions SBI, YES BANK,
Ollama, and 12 sprint proposals. The current conversation specifically confirmed
HDFC/Axis/ICICI and llama-swap. Treat the older README as background, not as a new
instruction to implement every bank or substitute Ollama for llama-swap.

### A2. Requirements questions already answered

Do not ask these again unless a change is necessary:

| Topic | Latest answer |
|---|---|
| Email provider | Purelymail, directly delivered mail |
| Initial mail scope | Dedicated banking inbox; new mail from initialization onward |
| Hosting | Self-hosted; broader services on different fleet machines on one subnet |
| Reverse proxy | Traefik per node; no receiver HTTP endpoint is currently needed |
| Current build host | Windows with Docker Desktop, Linux containers |
| Storage | PostgreSQL, initially provisioned as a local Compose service |
| LLM routing | llama-swap; exact model can be selected later |
| Actual deployment | Self-hosted, no end-to-end budget encryption |
| Actual wrapper | None currently; earlier affirmative answer was corrected |
| Transactions | Auto-import validated transactions; review ambiguous ones |
| Other entry sources | None planned for v1 |
| Categories | Actual's rules |
| FX situation | Overseas purchases on Indian cards, not confirmed foreign-denominated accounts |
| Loans | Payment expenses only for v1; no existing debt-account tracking |
| Transfers | Own-account transfers and card repayments should be supported downstream |
| Review application | User's own messaging app, still in development, adaptable API/callbacks |
| Multiple accounts | Architecture should support them in one container |
| Active deployment scope | Keep one inbox for now |
| Read flags | Preserve them; unread must stay unread |
| Implementation language | Python, explicitly selected after initial JavaScript setup |

Still unresolved for the downstream pipeline: representative bank email samples,
model/hardware selection, notification API details, account mapping inventory,
Actual bridge deployment details, transaction matching rules proven on samples, and
retention/backup policy. The user said sample bank emails would come after the base
design was ready. Harmless test emails used for capture do not substitute for that corpus.

### A3. Collaboration style and authorization history

The user initially asked to be guided step by step and ran commands locally. They
preferred a manageable next step with an observable result rather than a large
implementation dump. They later explicitly authorized autonomous deletion/modification
to switch the receiver to Python, asking for verbose progress. Subsequent implementation
steps were carried out directly with progress updates and live verification.

When the user said the context was too large, they asked for a runbook to preserve
the work. The latest request expands that runbook; it is not authorization to silently
complete every backlog item. Keep the service intact while documenting it.

The user specifically corrected the documentation format: **short TL;DR in chat,
full descriptive documentation in README**. This runbook is intended to be even more
complete than the README and to prevent repetition or loss of context next session.

### A4. Misunderstandings and corrections

1. **“No auto add for v1”** was ambiguous. Follow-up clarified that validated imports
   should be automatic, with no other transaction-entry sources in v1.
2. **Actual API wrapper** was first reported present, then corrected to absent.
3. **Non-INR** meant overseas card purchases, not necessarily a foreign-currency ledger.
4. **Email latency:** moving out of n8n does not establish a speedup. IDLE was already
   possible; independent reliability and ownership were the main architectural benefit.
5. **Primary-key updates:** the downstream event is a new email-row INSERT. UUID primary
   keys do not change to indicate processing progress.
6. **“Too big for one session”** referred to a garbled SQL terminal paste. It was initially
   misread as a request to stop work. The actual resolution was executing SQL from a file.
7. **Language:** Node.js was an initial library convenience, not a hard requirement.
   Switching the receiver to Python does not imply rewriting Actual's official Node.js API.
8. **Multiple mailbox deployment:** user chose one container with many workers, not one
   container per mailbox. Later “one inbox for now” narrows live testing, not the schema.
9. **README format:** the user did not want a TL;DR pasted into README in place of a full guide.

## B. Architecture decisions and the alternatives in more detail

### B1. Why a separate receiver

A running receiver should continue persisting emails when n8n is unavailable, an LLM
is loading, the messaging app is down, or Actual is restarting. Only IMAP and PostgreSQL
are required for capture. Downstream consumers read durable rows when they recover.

The very first prototype coupled capture to an HTTP delivery loop. It persisted email,
sent an event ID to n8n, recorded delivery attempts, and retried failed calls. The user
removed that responsibility: there is no n8n URL or webhook token in the current receiver.
Do not copy delivery columns or retry loops from imap-listener into the new schema.

### B2. Existing package research and what was not established

Research identified available protocol libraries and complete email products. It did
not produce a certified comparison, production benchmark, or security audit.

- **ImapFlow:** selected initially for IDLE and IMAP operations. It was already an
  existing library, so the JavaScript prototype did not implement the protocol itself.
- **Mail-Archiver:** advertised IMAP archiving, PostgreSQL, UI/search/API features and
  scheduled sync. Its exact minimum interval, skip-history semantics, and downstream
  schema contract were not verified for this project.
- **MailFathom:** advertised IMAP-to-PostgreSQL synchronization with broader retrieval/AI
  features. It was considered but not deployed or evaluated against the user's mailbox.
- **EmailEngine:** a broader headless email platform. Redis appears in queue handling,
  conditional data operations, and Lua scripts. Replacing it would require more than
  swapping a connection string. Its public source has commercial licensing terms;
  modifying the application does not remove license obligations.
- **Chosen solution:** narrow receiver logic built on maintained Python libraries.
  The scope we own is configuration, persistence, checkpoints, retries, and operational
  behavior. We still need tests for those responsibilities; using a library does not
  eliminate all IMAP edge cases.

### B3. Redis versus PostgreSQL

Redis was discussed as a fast queue/cache/notification system with configurable
persistence, Pub/Sub, and Streams. PostgreSQL was chosen because source records,
relational metadata, unique identities, and atomic checkpoints are the core requirement.
There was no measured throughput problem that required adding Redis.

LISTEN/NOTIFY is optional future consumer acceleration, not the durable store. If
n8n misses a notification, it should discover eligible rows through its own processing
state. Do not rely on notification delivery as proof of transaction processing.

### B4. Current versus proposed connection model

Earlier design text calls for a shared PostgreSQL pool with reserved connections.
Actual code currently creates a dedicated synchronous psycopg connection in each
worker. That connection owns the session advisory lock and runs capture transactions.
The supervisor opens an additional short-lived connection every configuration refresh.

This is simple for one inbox. At eight workers it ordinarily requires eight persistent
worker connections plus supervisor/admin/test capacity. It does not yet have a configured
pool or a global parsing semaphore. Do not claim pool sizing tests validate this runtime;
there is no pool to test at present.

## C. Current deployment inventory and configuration semantics

### C1. Docker artifacts

| Item | Current setting |
|---|---|
| Python base image | `python:3.14-slim-bookworm` |
| Database image | `postgres:17` |
| Python dependency | `psycopg[binary]==3.3.3` |
| IMAP implementation | Standard-library imaplib |
| MIME implementation | Standard-library email |
| Container working directory | `/app` |
| Receiver process user | Non-root Linux user `receiver` |
| Entrypoint | `python -m src.cli` |
| Image default arguments | `--help` |
| Compose receiver arguments | `observe` |
| Restart policy | `unless-stopped` for receiver and PostgreSQL |
| Receiver shutdown grace | 30 seconds |
| PostgreSQL data mount | Named volume `postgres-data` at `/var/lib/postgresql/data` |
| Published host ports | None in the current Compose file |
| Docker receiver healthcheck | Not implemented |
| PostgreSQL healthcheck | pg_isready, 5-second interval/timeout, 10 retries |

The base image tags are mutable. The dependency version is pinned, but this is not a
fully hash-locked or digest-pinned reproducible release. Image builds install Python
dependencies as root during the build, then runtime switches to the non-root user.
The test files are included in the image so tests can run without local Python.

### C2. Environment variables

| Variable | Consumer / meaning |
|---|---|
| POSTGRES_DB | PostgreSQL initialization and Compose interpolation; currently imap_receiver |
| POSTGRES_USER | Bootstrap owner; currently imap_receiver |
| POSTGRES_PASSWORD | Local bootstrap database password in .env; never reproduce its value |
| PGHOST | Receiver database hostname, currently postgres on the Compose network |
| PGPORT | 5432 |
| PGDATABASE | From POSTGRES_DB |
| PGUSER | Currently from POSTGRES_USER; to be changed for a restricted runtime role |
| PGPASSWORD | Currently from POSTGRES_PASSWORD |
| BANKING_IMAP_PASSWORD_FILE | `/run/secrets/banking_imap_password` |
| MAX_MAILBOX_WORKERS | 8 by default in current Compose |
| RECONCILE_SECONDS | 60 by default in current Compose |
| RUN_DB_TESTS | Only test opt-in: `1` runs the PostgreSQL fixture test |

The Python code lets libpq read the PG variables. It does not manually construct a
connection URL, avoiding URL-encoding issues for passwords. Mailbox credentials are
read through `credential_ref + '_FILE'`; they are not read from an arbitrary database
password column.

### C3. Secret handling

`accounts.credential_ref = BANKING_IMAP_PASSWORD` maps to the environment variable
`BANKING_IMAP_PASSWORD_FILE`, whose value is a file path. Compose mounts the local secret
file there. The Python code reads UTF-8 bytes exactly, including any whitespace. This
means an accidentally appended newline would become part of the password; do not trim
secrets silently to hide an editing mistake.

The original PowerShell secret-writing procedure used Read-Host -AsSecureString,
SecureStringToBSTR, WriteAllText with UTF-8 without BOM, and ZeroFreeBSTR in a finally
block. The file itself is still plaintext. Git/Docker ignore rules reduce accidental
inclusion but are not encryption or file-permission hardening.

No secret contents were intentionally printed during the Python conversion or tests.
The runbook includes references and paths, not values. A changed database password in
.env alone does not update a database role password after PostgreSQL has initialized.

### C4. Service state at handoff

The last live checks showed the receiver running, connected to Purelymail, and scanning
the enabled banking INBOX. The user subsequently reported successful downtime recovery.
This documentation pass did not requery Docker or alter the running state. Use `docker
compose ps`, logs, and last_scan_at when resuming rather than treating this historical
statement as a live monitor.

Known historical mailbox identifier, useful for matching the pasted logs:
`00000000-0000-0000-0000-000000000001`. It is an identifier, not a credential. Discover
current records through SQL instead of hardcoding it into generalized logic.

## D. Complete schema dictionary and integrity model

This dictionary reflects the psql output supplied and inspected in this conversation.
It is not a migration script. Verify live definitions before future ALTER TABLE work.

### D1. accounts

| Column | PostgreSQL type | Null/default | Interpretation |
|---|---|---|---|
| id | uuid | Not null; gen_random_uuid() | Account identity |
| name | text | Not null | Human-readable label |
| imap_host | text | Not null | IMAP server hostname |
| imap_port | integer | Not null; 993 | Range 1 through 65535 |
| username | text | Not null | Mailbox login; do not include in routine logs |
| credential_ref | text | Not null | Secret-reference name |
| enabled | boolean | Not null; false | Automatic-worker eligibility |
| created_at | timestamptz | Not null; now() | Account row creation time |

Only id is unique at the account level in the current schema. Duplicate registration
can create two records with the same credential_ref and username. Manual target lookup
requires exactly one matching account/mailbox; this is why rerunning registration SQL
can break commands rather than update the original account.

### D2. mailboxes

| Column | Type | Null/default | Interpretation |
|---|---|---|---|
| id | uuid | Not null; gen_random_uuid() | Stable mailbox identity |
| account_id | uuid | Not null; accounts FK | Parent account |
| folder_path | text | Not null; INBOX | Selected IMAP folder |
| enabled | boolean | Not null; true | Worker eligibility, combined with account enabled |
| uid_validity | bigint | Nullable before initialization | IMAP mailbox generation |
| last_uid | bigint | Nullable before initialization | Last safely examined UID boundary |
| initialized_at | timestamptz | Nullable before initialization | Baseline creation time |
| last_scan_at | timestamptz | Nullable | Last successful capture transaction / initialization |
| last_error_code | text | Nullable | Last recorded worker fault |

Unique: `(account_id, folder_path)`.

Checkpoint CHECK requires either all of uid_validity/last_uid/initialized_at to be NULL,
or all populated with uid_validity in 1..4294967295 and last_uid in 0..4294967295.
Read flags and message count are not checkpoints. A mailbox with 250 messages can
legitimately have a much higher UID because deletions leave gaps.

### D3. emails

| Column | Type | Null/default | Interpretation |
|---|---|---|---|
| id | uuid | Not null; gen_random_uuid() | Consumer-facing immutable source ID |
| mailbox_id | uuid | Not null; mailboxes FK | Source folder identity |
| uid_validity | bigint | Not null | Source generation, range 1..4294967295 |
| uid | bigint | Not null | Source UID, range 1..4294967295 |
| message_id | text | Nullable | Sender-provided identifier, not trusted unique |
| subject | text | Nullable | Parsed header |
| from_addresses | jsonb | Not null; [] | Array of name/address objects |
| to_addresses | jsonb | Not null; [] | Array of name/address objects |
| cc_addresses | jsonb | Not null; [] | Array of name/address objects |
| message_date | timestamptz | Nullable | Date header when parseable and timezone-aware |
| internal_date | timestamptz | Nullable | Server INTERNALDATE; current fetch requires it |
| captured_at | timestamptz | Not null; now() | Database insertion transaction time |
| text_body | text | Nullable | Selected plain-text MIME body |
| html_body | text | Nullable | Selected HTML body, not sanitized for rendering |
| raw_email | bytea | Nullable only for allowed capture exceptions | Original RFC822 source |
| raw_sha256 | text | Nullable; lowercase 64-hex check if present | Source digest |
| size_bytes | bigint | Not null; nonnegative | Reported source size, checked against fetched size |
| capture_status | text | Not null | captured / parse_failed / oversized |
| error_code | text | Nullable | Safe parse/size exception code |
| parser_version | text | Nullable | Current value stdlib-email-v1 |

Constraints and indexes:

- Unique source tuple `(mailbox_id, uid_validity, uid)`.
- `raw_email` and `raw_sha256` must be present unless status is oversized.
- Address JSON values must be arrays.
- Index on `(captured_at, id)` and partial index on non-null message_id.
- Foreign key to mailboxes, with default restrictive behavior rather than cascading deletion.

The schema does not enforce application-level immutability through triggers or a
restricted role yet. Current capture inserts records and does not update prior source
rows. It also does not enforce hash correctness through a database CHECK: application
code calculates the hash. Treat the captured_at index as an aid for queries, not as a
complete durable consumer cursor across concurrent transactions.

### D4. attachments

| Column | Type | Null/default | Interpretation |
|---|---|---|---|
| id | uuid | Not null; gen_random_uuid() | Metadata row identity |
| email_id | uuid | Not null; emails FK | Parent source email |
| part_index | integer | Not null; nonnegative | Ordinal from iter_attachments(), starting at zero |
| filename | text | Nullable | Untrusted parsed filename |
| content_type | text | Nullable | MIME content type |
| size_bytes | bigint | Not null; nonnegative | Decoded content size, or fallback serialized-part size |
| content_id | text | Nullable | Inline content ID |
| sha256 | text | Nullable; lowercase 64-hex check | Content digest |

Unique: `(email_id, part_index)`. The ordinal is not a complete MIME tree path.
Attachment bytes are not duplicated into a separate blob table. The original raw source
contains them. Some multipart/message attachments use serialized-part fallback when
get_payload(decode=True) returns None; their recorded size/hash follows that fallback.

### D5. Rows that do not exist yet

No application-level table for transactions, account-to-Actual mapping, review decisions,
consumer leases, notifications, parsed financial events, job outbox, or schema migration
history has been added. The four receiver tables are the implemented domain schema.
Do not confuse imap-listener's earlier mail_event/mail_checkpoint concept with these tables.

## E. Exact Python command behavior

### E1. check-db

Connects with a ten-second connect timeout and reads all joined account/mailbox rows.
Prints account label, enabled flags, folder, and whether initialized_at exists. Does
not return passwords, insert rows, initialize a checkpoint, or test IMAP. A successful
check proves database access and the query work; it does not prove capture is current.

### E2. check-imap

Looks up exactly one mailbox by credential_ref and folder. It deliberately ignores
enabled flags because it is an explicit diagnostic. Reads the mounted password, opens
IMAP4_SSL with a verified SSL context and 20-second timeout, logs in, and selects the
folder read-only. Prints success, read-only status, count, and whether the capability
response contains IDLE. Does not fetch message bodies or create a baseline.

Folder names are quoted/escaped. CR, LF, and NUL are rejected. Non-ASCII names fail
with a descriptive setup error because modified UTF-7 support is not implemented.
Port is configurable but the connection mode remains implicit TLS; arbitrary STARTTLS
on port 143 is not implemented merely by changing the port.

### E3. init-mailbox

An explicit state-changing setup command, not a continuously running worker:

1. Resolve exactly one configured mailbox.
2. Start a PostgreSQL transaction.
3. Acquire the transaction-level advisory lock for its mailbox UUID.
4. Lock the mailbox row using FOR UPDATE.
5. If initialized_at is already set, return without contacting IMAP or changing it.
6. Otherwise open/select the mailbox read-only.
7. Require valid UIDVALIDITY and UIDNEXT responses.
8. Store UIDVALIDITY and UIDNEXT minus one plus initialization/scan timestamps.
9. Commit; rollback on failure.

The lock key is `hashtextextended(mailbox_id::text, 0)`. The initializer and capture use
transaction locks; continuous workers hold a session lock using the same key convention.
Do not initialize a live-owned mailbox concurrently. A message existing before the
selection boundary is intentionally skipped. A message arriving afterward is eligible
for future capture. No email is deleted or marked read by initialization.

### E4. capture-once

The CLI targets a single credential reference and folder, not all enabled mailboxes.
It is usable for diagnostics even if account enabled is false. It rejects contention
with the continuous worker, so stop the receiver before manually targeting its mailbox.

Inside one transaction:

1. Acquire the mailbox advisory lock and lock the checkpoint row.
2. Require initialized_at; never infer a baseline from a missing checkpoint.
3. Select the mailbox read-only and read its generation and UIDNEXT.
4. Reject changed UIDVALIDITY or a UIDNEXT boundary behind last_uid.
5. If there are newer UIDs, search the closed range `last_uid + 1 : UIDNEXT - 1`.
6. Sort/deduplicate returned UIDs and reject values outside the requested range.
7. Process the first 50 of those UIDs in ascending order.
8. Fetch UID, RFC822.SIZE, INTERNALDATE, and FLAGS. Require the expected UID and usable metadata.
9. For accepted sizes, fetch `BODY.PEEK[]<0.max_bytes+1>`. Require exactly one literal
   and exact agreement between fetched byte length and the reported size.
10. Parse the source; oversized messages receive an explicit metadata-only outcome.
11. INSERT the email with ON CONFLICT DO NOTHING RETURNING id. Only a newly inserted
    email receives new attachment metadata rows.
12. Fetch flags again and count before/after read state. A changed flag is reported,
    not forcibly restored, because another mail client may have changed it concurrently.
13. If more than 50 UIDs were found, advance to the last selected UID. Otherwise advance
    to the captured upper search boundary, allowing legitimate gaps.
14. Update last_scan_at, clear last_error_code, and commit.

An exception from fetching, metadata validation, or SQL rolls back the batch and its
checkpoint. Successful parse_failed/oversized outcomes are committed exceptions, not
transaction failures. Repeated runs do not reparse those rows automatically.

This is at-least-once examination with idempotent source storage, not a claim that an
IMAP network operation happens exactly once. A separate duplicate bank alert with a new
UID gets a separate source row. Financial-event deduplication remains downstream.

### E5. MIME parsing and evidence preservation

The parser uses BytesParser with policy.default. It extracts Subject, Message-ID,
From/To/Cc, timezone-aware Date, selected plain and HTML bodies, and attachment metadata.
An absent/unparseable/naive Date yields a null message_date rather than a guessed timezone.
INTERNALDATE is fetched separately from the server.

Any MIME defect encountered while walking parsed parts sets status parse_failed with
mime_defect. An exception sets mime_parse_error. Parsed fields successfully extracted
before the exception can remain present; status is the indication not to treat the record
as a complete clean parse. Raw bytes/hash are retained regardless of parse status for
within-limit messages.

NUL is replaced by U+FFFD recursively in parsed strings/JSON because PostgreSQL text
cannot contain NUL. This does not modify raw_email. HTML is stored, not sanitized; a
future UI must sanitize it. The receiver does not execute attachments, follow links,
obey email instructions, classify transactions, or call an LLM.

### E6. observe and worker lifecycle

The supervisor validates MAX_MAILBOX_WORKERS (1–32) and RECONCILE_SECONDS (10–1740),
installs SIGTERM/SIGINT handlers, and refreshes enabled targets every five seconds.
Targets include endpoint, username, credential_ref, mailbox UUID/path, and initialized_at.
If a target disappears or these fields change, its stop event is set. A replacement is
not started under the same key until the old thread has exited. Dead threads are removed.

Each worker connects to PostgreSQL, takes the session advisory lock, then logs into
IMAP. It performs an immediate scan. capture_once is reused through a context wrapper
that reselects the folder on the same IMAP connection rather than logging in per batch.
The transaction lock is compatible with the same session's ownership lock.

The worker next waits in IDLE segments of at most about ten seconds. Short segments let
it notice stop requests and check the database connection between waits. EXISTS or
EXPUNGE marks a scan due immediately. BYE raises a connection fault. When the configured
interval expires, a safety scan runs even without a notification. A non-IDLE server
uses timed waits until the next periodic scan. A backlog makes scans run immediately
until more_pending is false.

Before each loop it performs SELECT 1 on the pinned database connection. If that
connection is lost, it cannot safely assume it still owns the mailbox lock; the session
exits and recovery creates a new connection and reacquires ownership.

Stopping or restarting does not clear enabled flags or checkpoints. Re-enabling an
existing configured mailbox catches up rather than treating all current mail as old.
Newly registered mailboxes must be initialized explicitly before observation can succeed.

## F. Code observations and gaps that must not be hidden by the handoff

These are observations from reading the current implementation, not fixes made during
this documentation request. They are useful review targets before claiming production
hardening. No new incident is implied unless a live failure is explicitly described.

### F1. Retry timing is more specific than earlier prose

Earlier messages and README say retry delay is capped around five minutes. Actual code
is `min(300, 2 ** min(failures, 8)) + uniform(0, 1)`, so the exponent cap makes the maximum
approximately **256–257 seconds**, not 300–301. The failure counter starts at zero per
worker and increments after every failed session; it does not currently reset after a
long healthy session. Missing checkpoint and mailbox identity errors use a fixed
60-second wait instead. This is documentation precision, not a new configurable promise.

### F2. Limits are partly constants, not configuration

The 50-message and 10 MiB limits are default function arguments in capture_once. The
CLI has no --limit or --max-bytes flags and Compose does not configure them. Worker
count and reconciliation seconds are environment-configurable; body/batch limits are
not yet exposed the same way.

Metadata-first filtering plus a partial body request reduces oversized retrieval under
a compliant server. The implementation still buffers a returned literal and parses
in memory; it is not the streaming receiver originally proposed. SEARCH can also return
all UIDs in the pending range before the first 50 are selected. Aggregate memory and
large-backlog behavior deserve explicit stress testing.

### F3. Health is partially recorded, not actively monitored

last_scan_at and last_error_code are useful observability inputs. They are not a Docker
health probe, alert subscription, or complete status state machine. If PostgreSQL is
unavailable, the worker may be unable to write its error code. If a worker is not
scheduled due to capacity, its row may retain old status. A running container can have
no healthy mailbox workers. There is no automatic recovery action based on stale scans.

### F4. Supervision and isolation test limits

The worker-limit test mocks threading.Thread and verifies separate stop events; it does
not run two real providers or interrupt one while another captures. The IDLE test uses
a fake EXISTS event. Authentication failure, network reconnect, and multi-account memory
pressure have not all been tested end to end.

The supervisor reads accounts in UUID order. When capacity is reached, additional
mailboxes are left unscheduled and a warning is logged. There is no fairness scheduler
or capacity queue. Live one-inbox scope does not exercise that case.

### F5. Shutdown has a deadline

The successful live restart logged workers_remaining=0. That proves that restart path
completed cleanly on that occasion. Threads are daemon threads, and join is bounded.
A slower operation may outlast the 25-second join deadline; process exit closes sockets
and open database transactions should roll back rather than completing gracefully.
Do not describe every possible shutdown as guaranteed to finish the current batch.

### F6. Error reporting favors secrecy over detail

Known SetupError strings are generated locally and safe to print. External exception
messages are not printed by the CLI; it reports the exception class. Observer codes are
mostly exception class names, with specific mappings for checkpoint_required,
mailbox_identity_changed, and mailbox_owned. This can make authentication versus other
protocol errors less descriptive. Improve error taxonomy carefully without logging
passwords, full server responses, subjects, bodies, or connection strings.

### F7. Source configuration is trusted administration

credential_ref is matched to an environment variable, and worker targets come from
database rows. The code does not implement a general admin UI, schema-validation API,
allowlist of IMAP hosts, or source-change migration. An administrator can repoint a
mailbox row; that does not make its existing checkpoint valid for the new source.
Create a new mailbox identity or explicitly reconcile instead of repointing silently.

### F8. Parsing provenance is a logical version

parser_version currently stores stdlib-email-v1, not an exact Python patch version,
dependency hash, or parser build digest. A future reprocessing mechanism may need
stronger provenance. No reparse command or patch-in-place source repair exists yet.

### F9. No migration framework or reproducible clean bootstrap

The schema was created interactively and verified from psql output. The surviving SQL
filename is misleading. Do not claim a fresh checkout plus Compose creates all receiver
tables and account rows. It starts PostgreSQL, but application schema and registrations
still require a proper migration/bootstrap implementation. Preserve the existing live
schema while repairing this documentation/deployment gap in a future task.

### F10. Documentation drift to resolve deliberately

| Earlier text | Current implementation |
|---|---|
| Shared database pool | Dedicated pinned worker connections |
| Configuration applied only on restart | Supervisor reloads target rows every five seconds |
| Automatic baseline on first worker activation | Explicit init-mailbox command required |
| All source limits configurable / streaming | Function defaults and in-memory parsing |
| No continuous observer / no background workers in old module docstrings | observe is implemented and running |
| Root README: no runnable service, Ollama-centric initial intake | Receiver exists independently; downstream choice is llama-swap |
| Full migration history planned | No implemented migration framework |

The runbook records these rather than rewriting unrelated artifacts or changing behavior
during a documentation-only request.

## G. Verification ledger: exactly what evidence exists

### G1. Sixteen Python tests at the last implementation run

| Test | Evidence type | What it checks |
|---|---|---|
| password_whitespace_preserved | Unit / temporary file | Credential bytes preserve spaces and CRLF |
| missing_reference | Unit | Missing secret reference raises SetupError |
| mailbox_quoting | Unit | Space-containing folder quoted; CRLF injection rejected |
| uid_validation | Unit / mocked response | UIDNEXT integer handling and invalid/missing/range rejection |
| existing_checkpoint_never_contacts_imap | Unit / mocked DB | Initialization no-op does not call IMAP |
| lock_contention_never_contacts_imap | Unit / mocked DB | Initialization refuses lock conflict |
| plain_email_and_missing_message_id | MIME fixture | Plain body, sender, subject, aware date, absent Message-ID |
| malformed_multipart_retains_failure | MIME fixture | Multipart defect marked parse_failed |
| attachment_and_html | MIME fixture | HTML selected and attachment size metadata captured |
| nul_sanitization | Unit | Parsed NUL replacement |
| replay_rollback_and_generation_guard | Real PostgreSQL, fake IMAP | Initial insertion, empty repeat, forced replay no duplicate, rollback after second metadata fetch fails, generation mismatch, oversized outcome |
| blocked_errors_classified | Unit | UIDVALIDITY and initialization errors mapped |
| backoff_bounded | Unit | Large failure count gives delay below 301 seconds |
| worker_limit_and_independent_workers | Mocked threads | Capacity, distinct events, stop only removed target |
| lock_conflict_prevents_imap | Mocked worker DB | Observer refuses ownership conflict before opening IMAP |
| idle_notification_triggers_second_scan | Mocked IMAP/capture | EXISTS after first scan causes a second scan |

The database test creates isolated account/mailbox fixture rows inside an outer
transaction, uses nested capture transactions/savepoints, then raises psycopg.Rollback.
It does not delete real banking emails. Its fixture DELETE and UPDATE operations require
test/admin privileges; those should not dictate the future production role's grants.

“All 16 passed” refers to the full run with RUN_DB_TESTS=1. Running without that variable
skips the database fixture test. Timestamp formatting was verified in live logs after
the observer tests; no dedicated timestamp unit test was added for that small change.

### G2. Live verification chronology

| Milestone | Observed evidence | Boundary of the claim |
|---|---|---|
| PostgreSQL startup | current_database/current_user both imap_receiver | Database is reachable |
| Schema verification | User pasted full psql definitions; inspected successfully | Four tables/constraints matched intended DDL at that time |
| Account registration | Banking inbox, account false, INBOX | Registration existed before capture |
| JavaScript checks | Database success; IMAP read-only, 250 messages, IDLE true | Initial setup only |
| Python conversion | Image build; six tests; live checks same provider | Language switch reached setup parity |
| Checkpoint | User confirmed sending test after init-mailbox | Baseline operation was user-executed; not independently timed |
| capture-once | 1 examined/inserted, no exceptions, unread 1→1 | One live new message captured |
| Repeat capture | 0 examined/inserted; stored source/text counts each 1 | No duplicate in immediate repeat |
| Observer startup | IDLE true, scan committed, no last_error_code | Persistent worker connected and scanned |
| Observer restart | workers_remaining=0; reconnect and successful scan | Clean shutdown/reconnect for that test |
| New automatic message | User pasted 1 inserted, unread 1→1, no exceptions | Unattended new-email capture succeeded |
| Timestamp change | Live event strings with UTC milliseconds | Logging change deployed |
| Downtime recovery | User reported passed after stop/send/start | User-reported catch-up success |

### G3. Not verified by the completed tests

- Every bank template, amounts, currencies, account mapping, transfers, or financial correctness.
- Actual Budget writes or duplicate financial-event prevention.
- Full database outage during live capture, lost commit acknowledgement, or corrupted disk.
- A live UIDVALIDITY reset (it was correctly not induced on the banking inbox).
- Backup restore, restricted-role permissions, or automated health failure detection.
- Multiple real accounts, simultaneous folders, account-specific auth failure isolation.
- Large attachment stress, giant backlog memory, sustained high throughput, or hostile IMAP server behavior.
- A measured latency breakdown separating provider delivery, IDLE wakeup, scan, parse, and commit.

## H. Log interpretation and incident triage

### H1. Event names

| Event | Interpretation |
|---|---|
| observer_started | Supervisor process started and reports limits |
| mailbox_connected | Worker logged in and selected mailbox; IDLE capability reported |
| scan_committed | Capture transaction succeeded, possibly with zero new messages |
| mailbox_retry | Worker session failed or is blocked; code indicates the broad reason |
| worker_capacity_reached | Enabled targets exceed available worker slots |
| supervisor_retry | Configuration refresh or supervisor work failed |
| mailbox_stopped | Worker exited through its stop/retry-loop path |
| observer_stopped | Supervisor finished shutdown waiting; remaining-worker count reported |

Not every clean session return emits mailbox_stopped. Use observer_stopped and process
status as well. Empty scan_committed entries are expected safety scans, not evidence of
duplicate import attempts or errors. There is no notification-reason field distinguishing
timer and IDLE scans in the current logs.

### H2. Capture summary fields

| Field | Meaning / interpretation |
|---|---|
| examined | Number of UIDs processed in this batch |
| inserted | Newly created email rows; can be smaller than examined during replay |
| parse_failed | Parse-defect/error outcomes among examined records |
| oversized | Metadata-only size exceptions among examined records |
| seen_unchanged | Count with same Seen flag before and after |
| unread_before | Count without Seen before source retrieval |
| unread_after | Count without Seen afterward |
| more_pending | Search found more pending UIDs than this batch processed |

A committed oversized record is not a saved full email. A committed parse_failed record
has evidence but needs downstream treatment. A Seen change can be caused by another
client; the receiver intentionally does not issue STORE to reverse it.

### H3. Safe initial triage

1. Check `docker compose ps` and recent receiver logs.
2. Query last_scan_at and last_error_code without selecting subject/body/raw source.
3. If PostgreSQL is down, restore its service/volume access before changing checkpoints.
4. If the worker is blocked on identity, preserve records and investigate the provider
   mailbox generation. Do not “fix” it by deleting state.
5. If credentials fail, inspect file existence/mount/reference locally without printing
   contents. Password whitespace is significant.
6. If another owner holds the lock, identify the other receiver/manual process. Do not
   terminate arbitrary database sessions without knowing which instance owns them.
7. If scans are current but no new rows appear, verify the email reached the selected
   INBOX, not another folder, and arrived after the initialization boundary.

### H4. Known setup mistakes and resolutions

| Symptom | Cause / resolution established here |
|---|---|
| RandomNumberGenerator lacks static GetBytes | Windows PowerShell 5.1 .NET API mismatch; use Create() and instance GetBytes |
| Convert.ToHexString unavailable | Same compatibility issue; use BitConverter.ToString(bytes).Replace('-', '') |
| Password file empty after a failed generation step | Regenerate before first DB initialization; do not assume changing .env changes an existing role password |
| Large SQL paste ends with garbled text / ^C | Stop pasting into psql; use a saved file, docker compose cp, then psql -f |
| schema already exists | Inspect tables before rerun; here all four were already correct |
| Duplicate account registration | Registration script inserts, does not upsert; verify identities before any cleanup |
| Expected exactly one matching mailbox | Missing or duplicate credential_ref/folder match; inspect configuration |
| mailbox_owned | Continuous observer or another process already holds the mailbox lock |
| checkpoint_required | Registering a mailbox is not initializing its baseline |
| mailbox_identity_changed | UID generation changed or UIDNEXT regressed; needs deliberate reconciliation |
| Container up but stale scans | Health gap; examine workers, errors, capacity, DB connectivity, and secret mounts |

## I. Downstream integration contract to preserve for later

### I1. Receiver-to-consumer handoff

The proposed consumer should identify source mail by emails.id. It should not use
Message-ID as a globally unique key, nor use only a timestamp/highest UUID to assume all
work is processed. A separate processing table should track claims, attempts, lease
expiry, status, and errors. Source records remain receiver-owned evidence.

If PostgreSQL NOTIFY is added, emit only a small identifier rather than full email bodies
or attachments. A notification should wake processing; a row query decides actual work.
The consumer needs startup catch-up and periodic recovery for missed notifications.
No notification trigger or consumer table was installed during this session.

### I2. n8n verification already discussed

The suggested verification was: create a Postgres Trigger in Listen to Channel mode,
connect to the same database, listen on tabbytally_mail_received, and issue a pg_notify
with a harmless event ID. Test both editor listening and published workflow execution.
The user deferred this. Do not treat it as passed or reintroduce an n8n webhook setting
into the receiver to work around it.

The built-in option that creates table trigger rules may require additional DDL
privileges. A manually provisioned database trigger plus Listen to Channel can keep
consumer runtime privileges narrower. That choice has not been implemented or approved
as the final downstream security design.

### I3. Proposed extracted transaction contract

The discussion called for event type, bank and account/card suffix, transaction date/time,
amount and currency, debit/credit direction, merchant/counterparty, bank reference,
transaction status, and evidence snippets. Missing values must remain missing. Available
balance and transaction amount must not be confused. Email receipt date is not always
transaction date. Do not infer a successful debit from an OTP or payment reminder.

Use integer minor units for final financial payloads. Prefer the actual billed INR
amount for Indian cards, storing original foreign amounts as context. Rule-driven
account resolution is safer than asking the model to invent Actual account IDs.

### I4. Review and learning contract

Proposed messaging API responsibilities were notification creation, review display,
decision callback, and notification status update. Each review should have a stable ID,
each decision a unique ID, and a version to reject stale corrections. The UI should offer
approve only when required fields are complete; missing amounts/accounts require correction.
Opening a message/link must never itself approve a transaction.

Store the original extraction, correction, reviewer decision, and model/prompt version.
Use approved suffix mappings and relevant reviewed examples to improve future cases.
Repeated corrections can suggest a rule, but a single correction should not silently
generalize to all future bank emails. Evaluate changes against retained examples.

### I5. Actual bridge and financial write contract

The proposed bridge remains Node.js because it uses @actual-app/api. It should serialize
budget writes, keep persistent local API state, authenticate requests, use stable request
and import identifiers, and distinguish “request failed” from “outcome unknown.” A network
timeout after a write is not proof that nothing happened. Query by request identity before
retrying. Rules should handle categorization. Transfers/card repayments should be linked
movements, not two expenses. Loan payments remain expense-only under the user's v1 choice.

No financial data has been written by the receiver. This distinction should remain clear
when demonstrating email capture success.

## J. Next work: concrete acceptance criteria without doing it yet

### J1. Restricted runtime database role

Suggested next task, not an implemented change:

1. Inventory actual SQL operations in cli/capture/observer.
2. Preserve the bootstrap owner for migrations and account administration.
3. Create a separate receiver login with only necessary privileges on the receiver schema.
4. Account for SELECT, INSERT/RETURNING, ON CONFLICT, mailbox FOR UPDATE, permitted
   checkpoint/error updates, and advisory-lock functions when testing grants.
5. Avoid granting schema CREATE, role administration, or blanket DELETE merely to make
   the fixture tests pass. Tests can use separate privileged credentials.
6. Store the new password locally without printing it, switch receiver PGUSER/PGPASSWORD,
   rebuild/recreate only as necessary, and retain a rollback path to the old configuration.
7. Verify check-db, check-imap, observation, a new-message capture, restart, and permissions
   denied for intentionally disallowed operations in controlled tests.

An account-registration role and a capture-only role need not be the same. The current
CLI shares one connection configuration across commands, so decide explicitly whether
init-mailbox remains permitted for runtime or becomes an administration command.

### J2. Health checks

Define health for enabled, initialized mailboxes, including scan freshness, blocked
state, worker capacity, supervisor freshness, and database reachability. Decide how
backlogs, reconnect backoff, no-enabled-mailbox cases, and intentional pauses affect
health. Add a probe that does not expose contents or mutate checkpoints. A Docker
unhealthy result by itself is not an alert or guaranteed restart policy.

### J3. Backup and restore

Design backup of database content and schema plus secure preservation of required
configuration/secrets. Test restore into a separate disposable environment. Verify
email/hash/attachment counts and checkpoints. Do not point a restored test receiver at
the live mailbox alongside the production owner without deliberate coordination.
Retention, destination, encryption, frequency, and restore objectives remain undecided.

### J4. Reproducible schema setup

Create an accurate initial migration from the verified schema and a migration history
mechanism without replaying DDL over the existing database. Rename or archive the
misleading account-registration SQL deliberately. Parameterize future registration and
avoid publishing the user's actual login in example files. Verify a separate fresh
database can reach the same schema without manual psql pastes.

### J5. Later stages

After hardening the current inbox, resume the n8n consumer design. Obtain representative
redacted bank samples and model constraints before implementing extraction. Do not require
a second live mailbox now; the user explicitly deferred it. Preserve the architecture
so a future multi-account test remains possible without schema redesign.

## K. Session continuity checklist

At the next session:

- Read this runbook and inspect current git status before editing.
- Treat the files and live service as potentially changed since this record.
- Keep the single active inbox and preserve its current checkpoint.
- Do not rerun the account INSERT or initial schema SQL blindly.
- Do not delete named volumes or reset UID state as a shortcut.
- Do not assume old prototype paths are the current application.
- Keep runtime secrets local and redact examples.
- Follow the latest explicit user request rather than executing the whole backlog.
- Report concrete verification and limitations; do not present mocked tests as live-provider proof.
- Put full implementation/operating detail in files, with a concise summary in chat unless
  the user asks for verbose narration.

This expanded document captures the substantive requirements, decisions, corrections,
commands, implementation behavior, known gaps, verification boundaries, and next steps
available in this conversation and the inspected workspace. It intentionally does not
invent unrecorded times, dependency audits, live tests, private data, or completed work.

## 2026-10-15 — addendum: restricted PostgreSQL runtime role

After the runbook handoff, the user requested the next step. Implemented the previously
proposed restricted database role without changing existing source records or checkpoints.

Changes:

- Added src/database.py to share connection creation and read PGPASSWORD_FILE as exact
  UTF-8 bytes when configured. Existing PG environment variables still supply host/user/db.
- Receiver now logs in as imap_receiver_runtime. Its generated 64-character hexadecimal
  password is kept in ignored secrets/receiver_db_password.txt and mounted as a Docker
  secret. No password value was printed. The existing administrator password remains unchanged.
- Added src/admin.py for explicit provisioning. It uses a transaction and SCRAM password
  storage, creates/updates the login, applies permissions, and refuses unexpected existing
  role memberships/ownership. It never runs during observer startup.
- Added a maintenance-profile admin Compose service. It receives bootstrap credentials;
  the normal receiver service no longer receives them. Explicit run admin provisions
  the role; normal up does not start this maintenance service.
- Runtime grants: schema USAGE; SELECT on all four receiver tables; INSERT on emails
  and attachments; column-level UPDATE of checkpoint/scan/error fields on mailboxes.
- No grants to modify accounts, enabled flags, mailbox identities, existing email content,
  or delete/truncate source data. No table/schema/role ownership or superuser/createdb/
  createrole/replication/bypass-RLS attributes. Existing PUBLIC privileges are unchanged.
- Explicit init-mailbox remains within runtime permissions, since checkpoint fields
  are required for capture. This is not a read-only database account.

Verification: all 17 tests passed, including a real PostgreSQL fixture test that sets
the runtime role, executes capture and attachment insertion, replays without duplicates,
and verifies 12 prohibited operations raise InsufficientPrivilege. Fixtures are rolled
back. Actual password-based runtime login and the existing account query succeeded.
The observer was then recreated with runtime credentials. Live logs showed IDLE connection
and a committed scan with no errors; pg_stat_activity confirmed its session username was
imap_receiver_runtime. The recorded scan was at 2026-10-15 06:54:34 UTC (12:24:34 IST).
No fresh real-email arrival was required to demonstrate the role's
INSERT permissions; those were exercised with the capture path and isolated fixtures.

Important command change: privileged fixture tests now run through admin:

```powershell
docker compose run --rm --no-deps -e RUN_DB_TESTS=1 -e RUN_ROLE_TESTS=1 --entrypoint python admin -m unittest discover -s tests -v
```

The older receiver RUN_DB_TESTS command elsewhere in this historical record is no longer
appropriate: the restricted runtime role deliberately cannot create/delete fixture
account rows. Unit tests without those opt-ins still run through receiver.

Next steps are receiver health checks and backup/restore verification, not redoing role
provisioning or registering another inbox. The reproducible schema/migration gap remains.

## 2026-10-15 — health checks, step 1: implementation prepared

Added src/health.py. The supervisor publishes an atomic local JSON snapshot in
/tmp/imap-receiver-health.json every configuration loop (normally five seconds).
It contains process ID, monotonic heartbeat, worker liveness/stopping/retry state, and
each worker's last successful scan in this process. It contains no subjects, addresses,
message bodies, or credentials. The file is container-local, not a persistent checkpoint.

Workers report successful scans and retries through a thread-safe registry. The probe
checks the observer PID and heartbeat, then queries enabled mailboxes using the restricted
runtime role and SELECT only. Missing/dead/stopping workers, missing initialization,
worker retry state, stored mailbox errors, and stale scans fail the check. Zero enabled
mailboxes are healthy idle if the supervisor and database are healthy.

Default supervisor freshness is 30 seconds. Scan freshness defaults to max(180 seconds,
three reconciliation intervals); HEALTH_SCAN_MAX_AGE_SECONDS can override within validated
bounds. SQL has a three-second statement timeout and connection timeout. Docker checks
every 30 seconds, with a ten-second timeout, three failures, and 60-second startup grace.
Docker unhealthy does not itself restart the service or send a notification.

No database migration/grant change is needed. Implementation is prepared at this step;
tests and deployment verification are recorded below when completed.

## 2026-10-15 — health checks, step 2: tests passed

Built receiver/admin images and ran the full suite through the maintenance service:
26 tests passed. Nine new health tests cover healthy/idle state, stale supervisor and
worker progress, missing/dead/stopping workers, missing checkpoints, stored mailbox
errors, stale database scan timestamps, retry/first-scan states, stopped/erroring
supervisors, atomic snapshot publication, recovery clearing retry state, missing
heartbeat, and redaction on database-probe failure. Existing IMAP/capture/permissions
tests still pass. These fault cases are simulated; live rollout follows next.

## 2026-10-15 — health checks, step 3: deployed and verified

Recreated receiver with Docker HEALTHCHECK and waited for healthy status. Live probe
returned healthy=true, mode=observing, enabled_mailboxes=1, reasons=[]. Docker ps showed
the receiver Up (healthy). Logs confirmed Purelymail IDLE connection and a successful
scan at 2026-10-15 07:19:55 UTC (12:49:55 IST).

Ran one isolated probe with PGPORT=1: it returned exit code 1 and a safe OperationalError
classification. This override applied only to that exec process, not the observer or
database service. Immediately reran the normal probe: exit code 0 and healthy=true.
No email, checkpoint, account, or permission changes were needed for these checks.

This verifies live normal operation and a real probe connection failure. Stalled workers,
missing/disabled targets, and stale-heartbeat cases were covered through automated
fixtures, not deliberately induced outages in the banking inbox. We did not force Docker
through three consecutive failing scheduled probes; its configured unhealthy transition
is distinct from the isolated failure check.

Updated README with commands, thresholds, failure reasons, idle semantics, and the
important limitation that Docker unhealthy does not send alerts or restart a live process.
Use `docker compose exec receiver python -m src.health` for the active container; a
fresh `run` container correctly lacks the observer-local heartbeat.

Current verification total: 26 passing tests, including PostgreSQL permission and capture
fixtures. Runtime grants remain unchanged. Next task: design and test backup/restore
without deleting live volumes or running a restored test observer against the real inbox.

## 2026-10-15 — GitHub publication, step 1: privacy and scope review

The user requested a branch and GitHub push. Backup/restore implementation was pending
when this request arrived; it remains the next operational task after publication.
Reviewed the tracked root README and untracked receiver, prototype, and design files.
Found a real mailbox address in the example registration SQL and replaced it with
banking@example.com. Replaced workstation-specific paths and the live mailbox UUID
in this public runbook with examples. The example UUID is not a live database target.
These substitutions affect documentation/examples only; the live database and source
mailbox configuration were not changed. No credentials or message contents are included.

Added repository-wide exclusions for local environment files, secrets, overrides,
private-key files, mail exports, database archives, logs, and generated dependencies.
Added backup/export exclusions to the receiver Docker build context and a placeholder-only
receiver .env.example. Clarified the active Python receiver, historical JS prototype,
and missing fresh-install migrations and restore tooling. The existing SQL filename
is misleading: it registers an account only. Kept this historical caveat explicit.
No license was invented; the existing README states that a license is not yet selected.
Publication does not establish an open-source reuse license or a production-ready release.

Next: scan candidate publication files against local secret values without displaying
those values, run the existing test suite, inspect the staged diff, and push a new branch.

## 2026-10-15 — GitHub publication, step 2: checks passed

Confirmed origin is purrMonster/tabbyTally and GitHub visibility is PUBLIC; remote main
is the original README commit. Reviewed 37 candidate files and compared their contents
against three locally loaded credential values without printing the credentials. No
remaining matches were found. Also checked private-key/token patterns, the removed
personal domain and live mailbox ID, and source/test addresses (synthetic example.com).
This is a targeted publication check, not a guarantee that all possible secrets can be
detected. Verified Git ignores the live .env, both mounted secrets, and example paths
for future dumps and mail exports. The existing tracked history contains only README.md.

Reran the existing Docker admin test suite with RUN_DB_TESTS=1 and RUN_ROLE_TESTS=1:
all 26 tests passed, including transactional capture and restricted-role checks. No
Python implementation changed in this publication step. Test database fixtures roll
back and do not read or send live email. The observer remains running.

Preparing branch codex/imap-receiver-foundation with current source, tests, public-safe
examples, design notes, and this runbook. Main remains unchanged. Push completion will
be recorded after GitHub confirms the remote branch.

## 2026-10-15 — publication cancelled; local environment configuration recorded

The user explicitly instructed not to push anything and requested an environment file
for passwords and email IDs. No commit or push had occurred. The local branch
codex/imap-receiver-foundation exists; earlier files had been staged, and publication
is cancelled. Do not resume pushing without a new explicit instruction.

Updated the existing ignored imap-receiver/.env, preserving the bootstrap database
settings. Read the single banking username from the existing database without displaying
it and copied the existing IMAP and runtime database password values from local mounted
secret files. Added BANKING_IMAP_USERNAME, BANKING_IMAP_PASSWORD, and RECEIVER_DB_PASSWORD.
Values were written locally only, not reproduced in the runbook, chat, or tracked example.
Updated .env.example with placeholders and documented current source-of-truth behavior.

This is a local configuration record, not a credential-storage migration: the running
receiver still reads the password secret files and the registered PostgreSQL username.
No credentials were rotated, no account/checkpoint rows changed, and no containers
were recreated. Editing these new environment entries alone does not alter live behavior.
The environment file contains plaintext credentials and must remain local and ignored.

## 2026-10-15 — publication reauthorized and final checks

The user explicitly reauthorized pushing once secret exclusions and placeholder files
were in place. This supersedes the earlier instruction to hold publication. Added
placeholder examples for both mounted password files under examples/; actual secrets/
and .env remain ignored. Documented exact-byte/no-newline requirements and the runtime
password format. Cleaned whitespace in the design documents. No runtime code changed
since the successful 26-test run recorded above.

The intended publication is the existing codex/imap-receiver-foundation branch only;
main is not being merged or modified. Before pushing, check the final staged content
against local credential/address values without printing them, verify excluded paths
are absent from the index, and run git diff --cached --check. Backup/restore and fresh
schema migrations remain pending work after this development snapshot.

## 2026-10-15 — GitHub publication completed

Final staged privacy scan passed across 39 files, including comparison against local
passwords and the mailbox address without printing values. Git confirmed .env and both
actual password files are ignored. Staged whitespace checks passed. Published commit
a096073 to origin/codex/imap-receiver-foundation and configured upstream tracking.
Main was unchanged and no pull request was created. This completion record is committed
separately on the same branch. The previously recorded 26-test result remains applicable:
subsequent changes affected documentation, placeholder examples, and ignore rules only.

## 2026-10-15 — backup and restore, step 1: implementation

Added an explicit maintenance-only backup service using PostgreSQL 17 client tools and
Python/psycopg. The observer image, runtime role, account identity, and checkpoints are
unchanged. The service mounts only backups/ for output and has bootstrap database access;
it has no IMAP secret, no observer startup, no automatic schedule, and no restart policy.

The create command opens a repeatable-read read-only transaction, exports its snapshot,
computes schema and table fingerprints, and passes the same snapshot to pg_dump while
the transaction stays open. Capture may continue. Archives cover imap_receiver only;
credentials, Docker configuration, database roles and other schemas are not covered.
The manifest stores counts/digests, never message contents or mailbox addresses. Raw
messages are in the archive, which is compressed but NOT encrypted. Both files stay
in ignored backups/; callers must arrange secure off-host copies separately.

Verification checks the archive hash, creates a random imap_restorecheck database from
template0, revokes PUBLIC connect, restores without original ownership or grants, and
compares columns/defaults/constraints/indexes and every complete row ordered by UUID.
All mailbox checkpoint fields participate in the row fingerprint. It also recomputes
raw-email SHA-256 against each stored hash. The temporary database is dropped in finally,
including when restore or comparison fails. A collision is never reused or dropped.
No arbitrary target database argument exists. Success reports are written only after
comparison and cleanup. Cleanup errors report the generated database name for follow-up.

The four current tables are the supported verifier contract. Added tests for path
rejection, archive corruption, missing manifests, matching and mismatched restores,
restore failure cleanup, creation collisions, and safe subprocess error messages.
Implementation is prepared; build/test and live restore outcomes follow below.

## 2026-10-15 — backup and restore, step 2: tests passed

Built the maintenance image with PostgreSQL 17 client tools, Debian Python 3.11, and
Debian psycopg 3.1.7. The receiver/admin continue using Python 3.14 and pinned psycopg
3.3.3. Ran all tests using the admin image with database and role fixtures enabled:
34 passed (26 existing plus eight backup tests). Also ran the eight backup tests inside
the actual backup image; all passed. This checks the separate maintenance runtime.

## 2026-10-15 — backup and restore, step 3: live verification passed

At 07:41:20 UTC / 13:11:20 IST, create --verify produced a local custom-format archive
and snapshot manifest. Counts: one account, one mailbox, four emails, zero attachments.
Restored into a new disposable database and matched schema, full-row fingerprints,
checkpoint fields, and raw SHA-256 values. The command reported restore_verified and
temporary_database_removed=true, with exit zero. An independent catalog query found
zero imap_restorecheck databases afterward. Live observer health remained healthy=true,
mode=observing, enabled_mailboxes=1, reasons=[]. No observer restart or checkpoint reset.

The live sample has no attachment rows; attachment metadata capture already has fixture
tests, but this run does not claim a live attachment restore demonstration. Backup does
not include secret files, roles, other schemas, or database settings. Restore verification
omits ownership/grants and is not yet a full host-loss recovery rehearsal. Existing raw
messages remain private in the ignored archive; no content or mailbox address was printed.

Added complete README usage, consistency semantics, failure handling, trust/unencrypted
archive limits, cleanup boundaries, and future disaster-recovery steps. Updated current
status in root README/runbook; historical pending statements remain historical evidence.
Added a Git ignore exception for Dockerfile.backup so the maintenance build recipe is
versionable while actual *.backup files remain excluded. No backup artifacts are staged.

## 2026-10-15 — schema migrations, step 1: baseline and runner

User approved continuing to reproducible schema setup. Exported schema-only definitions
from the working PostgreSQL 17 database (no rows or private mailbox data). Saved immutable
migrations/001_initial.sql and a companion expected structural SHA-256. Renamed the old,
misleading 001_initial_schema.sql account INSERT to examples/register_account.sql.

Added an administrator-invoked migration runner, separate from observer startup. It
normalizes line endings for portable checksums, requires contiguous numbered migrations,
serializes writers with an advisory lock, and applies DDL plus history in one transaction.
A clean database gets the baseline and schema_migrations ledger. An existing unversioned
schema requires explicit --adopt-existing and must match the checked baseline first;
adoption records history without replaying CREATE statements or touching business rows.
Modified history/checksums or supported structural drift fail closed. Read-only status
reports empty/unversioned/versioned without creating the ledger. Errors omit SQL/data.

Extended backup fingerprints to include the migration ledger when present and preserve
verification of older four-table archives. SQL files now explicitly enter the Docker
build only from migrations/. Added disposable-database integration tests for fresh/repeat
setup, adoption preserving rows, drift/checksum rejection, transactional rollback, and
concurrent runner exclusion, plus line-ending portability. No live adoption performed yet.

## 2026-10-15 — schema migrations, step 2: isolated tests passed

All 41 tests passed with database, permission, and migration test opt-ins enabled.
Six migration integration tests each created their own generated imap_migrationtest
 database and cleaned it afterward. Fresh installation matched the expected baseline;
repeat application made no changes; explicit adoption preserved complete table hashes;
drift/history tampering failed; a failed fingerprint rolled back the entire new schema;
and a second connection holding the advisory lock blocked concurrent application.
Line-ending normalization was verified separately. Live adoption follows only after a
new verified pre-adoption backup. The live observer has not been restarted.

## 2026-10-15 — schema migrations, step 3: live adoption and restore verified

Created and restore-verified a fresh pre-adoption archive at 07:49:22 UTC / 13:19:22 IST.
Read-only migration status reported unversioned, zero applied, one available. Performed
explicit baseline adoption inside an additional transaction with SHARE locks on the four
application tables, then compared their complete fingerprints before and after. They
matched: accounts, emails, attachments, and all mailbox checkpoint/state fields were
unchanged. Added only schema_migrations and its version-1 adopted=true record.

Repeat apply reported applied_now=0. Created and verified a post-adoption archive at
07:49:48 UTC / 13:19:48 IST: one account, one mailbox, four emails, zero attachments,
one migration ledger row. The restored ledger/schema/data matched, and cleanup succeeded.
Independent checks found zero restore/migration test databases, no runtime INSERT/UPDATE/
DELETE permission on the ledger, and healthy live observation of one inbox. No observer
restart, account registration, checkpoint initialization, or mail sending occurred.

Updated root README, receiver README, current runbook summary, and plan with migration
commands and limitations. Documented empty installation, one-time registration example,
explicit legacy adoption, version/checksum behavior, transactional rollback, backup
compatibility, and test commands. Existing dated references to the old SQL filename and
pending migrations remain historical records; the current example is now under examples/.

All 41 tests passed before adoption; live repeat/adoption/backup/health checks passed
subsequently. Next implementation boundary is downstream durable processing jobs and
n8n integration, not another inbox. Scheduling/off-host encrypted backup copies and
full disaster-recovery rehearsal remain open operational work. Current source changes
remain local on codex/imap-receiver-foundation; no new push was requested or performed.

## 2026-10-15 — Phase 1 completion and Phase 2 planning/publication

The user confirmed the phase boundary and requested publication of current changes plus
a detailed Phase 2 plan. Phase 1 is complete for the current one-inbox deployment:
read-only continuous intake, durable source identity/checkpoints, restart catch-up,
restricted runtime access, health, tested backup restoration, and schema migrations.
The evidence remains 41 passing tests, live version-1 adoption without application-row
changes, idempotent repeat application, successful post-adoption restore, and healthy
observation. Multi-inbox live testing, backup scheduling/encrypted off-host copies and
full host-loss rehearsal remain open; completion is not a claim those are done.

Added docs/PHASE_2_PLAN.md with implementation steps, proposed tables and states,
activation/catch-up semantics, lease/fencing/idempotency rules, endpoint verification,
normalization/extraction contract, validation/FX/transfer handling, review/correction
learning, n8n workflow decomposition, tests, privacy boundaries, and acceptance criteria.
Phase 2 produces validated candidates and durable review state, not Actual writes.
The later bridge is Phase 3; it does not yet exist. No Phase 2 runtime work was performed
as part of this planning/publication request. Incoming source mail remains independent.

Current n8n/PostgreSQL documentation was checked for notification and query mechanics.
Notifications are a latency aid; persisted jobs and reconciliation supply recovery.
Primary keys are source identities, not an update watcher or chronological cursor.
The plan calls out private PostgreSQL routing between nodes, explicit activation selection,
new downstream backup scope, and dedicated limited credentials. Model endpoint/version,
n8n deployment details and representative anonymized samples are needed when integrating.

Publishing the pending backup/migration implementation and documentation on the existing
codex/imap-receiver-foundation branch after a final staged privacy/whitespace review.
Main remains unchanged. The live deployment's secrets, addresses, archives, and local
configuration must remain ignored. Push completion is recorded after remote confirmation.

## 2026-10-15 — Phase 1 publication confirmed

Final staged privacy scan passed for 18 changed files, checking local credentials and
mailbox address without displaying them. Secret/environment/archive paths remain ignored;
staged whitespace checks passed. Published implementation and Phase 2 plan as commit
353dd43 on origin/codex/imap-receiver-foundation. The 41-test and live restore/adoption
results recorded above apply to this implementation; subsequent edits were documentation.
Main was unchanged, no pull request was created, and no Phase 2 services were deployed.
This confirmation is committed separately on the same branch.
