# Python processing — Phases 2.1 and 2.2

Durable PostgreSQL jobs for emails already stored by `imap-receiver`. This implementation
supports the durable fake processor and a **review-only extraction pilot**. It does not
send messages or write to Actual Budget. Phase 2.2 still needs real-model and bank-format
acceptance. See the [verification record](../docs/processing/VERIFICATION.md) and
[Phase 2.2 runbook](../docs/processing/RUNBOOK.md#13-phase-22-verification-and-pilot-operation).

Implemented: explicit activation and sample scopes, duplicate-safe discovery, expiring
claims, attempt history, fenced atomic completion, jittered retries, exhaustion, operator
retry/pause, synthetic results, least-privilege group roles, and combined backup support.

For the complete decision history, exact runtime behaviour, role/configuration tables,
test evidence, deployment procedure and incident recovery, read the
[detailed processing runbook](../docs/processing/RUNBOOK.md).

## Roastery model configuration

Use `compose.model.yaml` with the base Compose file for extraction. It selects a 1,200-second
worker deadline, 1,320-second claim lease and 1,230-second shutdown grace period. The base
fake-worker defaults remain unchanged. `MODEL_SOCKET_TIMEOUT_SECONDS` defaults to 1,140;
the subprocess deadline bounds the entire call even if the server keeps sending bytes.

The model example uses `MODEL_ALIAS=fast`, `MODEL_BACKEND=llama-swap`, thinking disabled,
up to 6,144 output tokens and 8,192 total context. Output tokens cover reasoning AND final JSON;
there is no guaranteed separate final-answer allocation. Set `MODEL_THINKING=true` only
for comparison runs; live probes exhausted even 6,144 tokens with thinking enabled.
The library default also remains false unless configured.
`MODEL_TEMPERATURE` defaults to 0.7 and accepts finite values from 0 to 2.
Prompt experiments were rejected after paired email tests; the verified baseline is
documented in [the model benchmark](../docs/processing/MODEL_BENCHMARK.md).
The adapter applies the upstream chat template and tokenizes it before generation, keeping
512 tokens of context headroom. The output budget shrinks to fit measured input, with a
4,096-token minimum (`MODEL_MIN_OUTPUT_TOKENS`). At most 3,584 measured input tokens
fit while preserving that minimum. Oversized inputs are reviewed, never silently truncated. Missing tokenizer endpoints
stop the attempt rather than silently substituting an estimate. Generic backends retain
the conservative byte-based check.
The backend setting enables read-only `/api/profiles` observations before/after generation.
Metadata retains both observations and the response's reported model. Stable observations
cannot prove there was no intervening profile change or establish a weight hash;
`weights_verified` remains false. `MODEL_PROFILE` is a client configuration label, not a
command to change llama-swap's active profile. `MODEL_REVISION` is a supplied annotation.
Token counts and configured budgets are recorded; raw reasoning is not retained. A profile
change during token preflight causes a transient retry. The entire operation, including
tokenization, remains inside the worker deadline. A crashed worker may take up to 22 minutes
plus recovery/backoff to become retryable under the model overlay. New settings change the
pipeline identity; activate a new extraction version rather than reusing an existing one.

For a one-shot extraction worker, explicitly use:

```text
tabby-processing work --deadline 1200 --lease-seconds 1320
```

Run `tests/probe_model.py` explicitly, with `processing/src` on `PYTHONPATH` and local model
environment configured, to send three synthetic cases through the actual adapter. It
requires no database and sends no real emails. It checks purchase amounts versus balances,
foreign amounts without invented INR, and reminder classification, reporting each case.
Do not count this small smoke test as real-bank acceptance. Remote use requires the HTTPS
route and an approved Basic-auth service account; loopback success does not establish either.

## Run isolated tests

From the project root, with Docker available:

```powershell
docker compose -f processing/compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
docker compose -f processing/compose.test.yaml run --rm --entrypoint python tests /app/processing/tests/run_receiver.py
docker compose -f processing/compose.test.yaml down
```

The test database has no published port or production mounts and uses disposable tmpfs
storage. Individual tests create/drop uniquely named databases. The second command runs
receiver regression tests in another disposable database. It may start the test DB again.
Do not point these test commands at a production database.

## Configuration and deployment

Deployment remains an explicit operator step; no live database has been migrated or
activated by creating this code. The supplied Compose file joins an existing same-host
receiver network. For a remote node, configure a separate deployment using private DNS,
source-restricted database access and certificate-verified TLS. Do not expose PostgreSQL
through an HTTP router.

1. Build from the repository root: `docker build -f processing/Dockerfile -t tabbytally-processing .`.
2. Copy `.env.example` to a private `processing/.env`, configure the database and create
   `processing/secrets/processing_db_password.txt`. Set `RECEIVER_NETWORK` for Compose
   interpolation in the shell or use `--env-file processing/.env` and include it there.
3. Run `tabby-processing migrate`, `status` and `provision` using a separate administrator
   connection inside the private database network. Never supply admin credentials to the
   long-running services. Migration creates only the `processing` schema.
4. Provision separate local LOGIN roles and secrets, granting membership in
   `processing_runtime`, `processing_operator` or `processing_inspector` as appropriate.
   `provision` creates NOLOGIN group roles; it does not create or print passwords. Verify
   login inheritance, CONNECT access and negative permissions before starting services.
5. Create and verify a combined backup as below before activation.
6. With the operator login, activate explicit samples or a narrow mailbox scope. Start
   discovery, work and recovery with `docker compose --env-file processing/.env -f
   processing/compose.yaml up -d`. All three services use only the worker login.

Configuration uses standard libpq variables including `PGHOST`, `PGPORT`, `PGDATABASE`,
`PGUSER`, `PGSSLMODE` and `PGSSLROOTCERT`; `PGPASSWORD_FILE` reads the mounted secret.
Application logging emits safe identifiers and error classes. Configure PostgreSQL logging
separately to avoid retaining sensitive statement parameters and row details as future
stages introduce financial content.

## Commands

Commands below assume the appropriate local database connection/role has been configured.
IDs are obtained from source inspection and command output. Keep real identifiers local.

```text
tabby-processing migrate
tabby-processing status
tabby-processing provision
tabby-processing activate --version fake-v1 --email EMAIL_UUID --reason "sample test"
tabby-processing activate --version fake-live-v1 --mailbox MAILBOX_UUID --reason "explicit boundary"
tabby-processing discover
tabby-processing work
tabby-processing recover
tabby-processing inspect
tabby-processing history JOB_UUID
tabby-processing pause RUN_UUID --reason "maintenance"
tabby-processing resume RUN_UUID --reason "maintenance finished"
tabby-processing retry JOB_UUID --allowance 1 --reason "transient issue resolved"
tabby-processing health
```

`discover`, `work` and `recover` accept `--loop --interval SECONDS`. Work also accepts
`--lease-seconds` and `--deadline`; the deadline must be shorter than the lease. Default
intervals are 60/1/30 seconds, with a 180-second lease and 120-second fake-processing
deadline. Five claims are allowed initially; transient failures use full-jitter backoff
with a 30-second base and 15-minute cap. Operator retry adds a bounded allowance to a
dead job without deleting history. Pausing stops discovery/claims for that run; already
claimed work may finish, and recovery still accounts for expired attempts.

Fake activation accepts `--scenario success|review|transient|permanent|delay`, `--failures`
and `--delay`. Configurations are immutable per version. Only synthetic outcomes can be
stored. Changed UIDVALIDITY is reported by discovery and excludes that mailbox; the
operator must reconcile the receiver and explicitly activate a new scope/version.

Health checks establish schema/database readiness, not proof that a particular loop made
recent progress. Inspect backlog and attempt history alongside process/container status.
Each command uses a bounded connection and SQL timeout. Loops reconnect after database
connection failures; configuration/programming errors exit for operator inspection.

## Backup and restore

Rebuild the receiver backup image to include the new verifier. From `imap-receiver/`:

```text
docker compose --profile maintenance run --rm backup create --include-processing --verify
docker compose --profile maintenance run --rm backup verify ARCHIVE_BASENAME
```

`--include-processing` creates a version-2 snapshot archive containing both schemas.
Without it, the existing receiver-only format remains supported but does **not** protect
processing. Update scheduled backup commands before activation. Verification restores into
a new disposable database, checks schema/data fingerprints, and removes that database.
Backup files and manifests contain private state; protect them and maintain off-host copies.

For a real recovery, stop/fence all old workers, restore both schemas together into an
isolated replacement, verify integrity, reprovision roles, and test permissions. Before
restarting work, an administrator runs:

```text
tabby-processing invalidate-restored-leases --old-workers-fenced --reason "verified restore"
tabby-processing recover
tabby-processing discover
```

The confirmation flag records an operator assertion; it cannot stop external old workers.
The invalidation is audited and prevents an old token from completing restored work.
Completed results stay completed. Coordinate receiver checkpoint catch-up separately;
deleted IMAP messages cannot be assumed recoverable from the server. See the
[operations plan](../docs/processing/OPERATIONS.md) for production recovery prerequisites.

## Boundaries

No production activation, remote connectivity setup or off-host backup scheduling is
performed automatically. Fake processing uses metadata only; email body access is not
granted. Schema migrations and tests must be extended for Phase 2.2 before adding actual
extraction. Phase 2.3 adds review/API/outbox storage; those tables do not yet exist.
