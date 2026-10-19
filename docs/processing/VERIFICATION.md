# Verification through Phase 2.2

## Latest status — 18 October 2026

The dated historical results below are retained for traceability and superseded by
RUNBOOK.md sections 16–26. The latest isolated suite passes **94 tests**, including
candidate readiness, local corrections, repeat/stale/concurrent callback decisions,
outbox retry/exhaustion/stale leases, atomic rollback and review-state backup/restore.
Readiness is no longer universally blocked: the current offline corpus produces
108 ready purchase candidates and 55 financial reviews. All 163 financial events
have effective dates/accounts under the user-approved fallback policy. Zero of the
89 labelled negatives match transaction templates. Twelve unreadable inputs need review.

Signed callback authentication is unit-tested. The real Go bridge/Python receiver
round-trip now passes in scratch containers, including replay, stale revisions,
conflicting actions and one committed decision (RUNBOOK section 27). meowGram's
separate HTTP integration suite checks OIDC identity and bot authentication.
Notification delivery is tested with injected senders and six consumer tests for the
[durable-send-v1 contract](MEOWGRAM.md). They cover receipt checks, failure handling,
privacy, disabled configuration, HTTPS requirements and subprocess timeout wiring;
they do not themselves establish provider idempotency. The meowGram integration
branch now tests that guarantee with real PostgreSQL concurrency and backup/restore.
Production credentials/connectivity and sample-only live rollout remain open gates. No Actual
Budget writes or mailbox changes occurred. See the private output map for individual
model outputs and current deterministic/validation results.

The [detailed runbook](RUNBOOK.md#13-phase-22-verification-and-pilot-operation) expands this
ledger with implementation details, operating commands and limitations.

Reverified **16 October 2026 (Asia/Calcutta)**. Implementation: `processing/`.
No live inbox, database, credentials or
budget was modified. Tests used Docker Desktop and an isolated PostgreSQL 17.11 server,
with Python 3.14 and psycopg 3.3.3 in the test image.

## Executed checks

| Check | Result |
|---|---|
| Foundation PostgreSQL integration suite | 20 tests passed |
| Extraction integration and financial validation | 16 synthetic tests passed |
| Model adapter subprocess/HTTP suite | 10 tests passed against a local synthetic server |
| Total processing suite | **46 tests passed** |
| Existing receiver regressions, with database/migration/role opt-ins | 41 tests passed in the earlier verification; unchanged receiver code was not rerun for the adapter-only update |
| Production Docker image build and CLI help | Passed |
| Production Compose plus model overlay validation | Passed with placeholder network and no environment-file resolution |
| Combined empty/populated snapshot archives and disposable restores | Passed |
| Restore of queued, leased, retry-wait, completed and dead jobs | Passed, including re-provisioned permissions and stale-token rejection |
| Populated extraction/candidate backup and restore | Passed |

**Verdict:** Phase 2.1 is locally verified. Phase 2.2's review-only implementation passes
synthetic verification but has **not** passed real-model or bank-format acceptance.
No candidate can become `ready`: `format_not_regression_approved` is unconditional.

## Live Roastery integration results — 16 October 2026

Latest requested rerun (unchanged prompt v2): all 46 automated processing tests passed.
The live normal-profile 9B probe failed overall: purchase returned an empty amount
(11.4 s); foreign preserved USD 12.50 and no billed charge (5.9 s); reminder correctly
returned non_transaction (1.3 s). The foreign case passed the probe's suffix-only account
assertion, but emitted `card_ending_1234`, not exact `1234`. That is not an exact account
extraction pass and would not match the configured exact account mapping. This exposes
a limitation in the smoke-test assertion; do not treat its two passing cases as financial
acceptance. No proposed accuracy improvements were implemented during this rerun.

Local `/health`, `/v1/models` and read-only `/api/profiles` checks passed outside the
sandbox. The HTTPS endpoint failed to connect on port 443. The user confirmed no service
credentials have been provisioned; authenticated LAN/container access remains unverified.

The actual Python adapter sent synthetic purchase, foreign-purchase and reminder cases
through alias `fast`. The game-mode watcher switched profiles naturally; no profile writes,
service restarts, model downloads or real email requests were performed.

| Run | Observed result |
|---|---|
| Initial prompt v1 CPU attempt | Contradictory classification rejected by parser; probe stopped |
| Complete prompt v1 CPU run | Purchase and reminder matched selected fields; foreign purchase was incorrectly classified unsupported |
| Prompt v2 during natural profile transition | Purchase passed on 4B CPU (~46.1 s); foreign USD amount preserved but another field assertion failed (~36.6 s); routing changed gaming → normal during that request; reminder passed on reported 9B (~11.0 s) |
| Complete prompt v2 normal-profile run | Purchase failed: empty transaction amount and invented identifier prefix (~7.5 s); foreign purchase failed: account identifier missing, though USD 12.50 and unknown billed amount were preserved (~5.6 s); reminder passed (~1.3 s) |

For the final normal run, reported model was `/models/Qwen3.5-9B-Q6_K.gguf` and both profile
observations were normal. The CPU runs reported `/models/Qwen3.5-4B-Q4_K_M.gguf`.
Weight hashes and actual GPU offload were not independently measured. Complete runs
returned structurally valid JSON and no reasoning content; this is compatibility evidence
for these requests, not proof of comprehensive grammar enforcement or reasoning internals.

The foreign probe originally required both unknown billing amount and currency to be null.
That assertion was corrected: the synthetic source explicitly names INR, so a known INR
currency with a null numeric charge is allowed. Earlier failed probes were not retroactively
counted as passes. Final failures above are directly observable in selected-field output.

**Live extraction acceptance failed.** The integration code is retained for review-only
evaluation, with longer timeouts, profile observations and a versioned prompt clarification.
Further prompt/model evaluation and a labelled bank corpus are required. The existing
validation rejects empty amounts and unmatched/missing accounts, and every candidate
still carries the unconditional review gate. See the
[integration runbook](RUNBOOK.md#14-roastery-adapter-integration) for exact configuration.

Commands from the project root:

```text
docker compose -f processing/compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests --attach tests
docker compose -f processing/compose.test.yaml run --rm --entrypoint python tests /app/processing/tests/run_receiver.py
docker build -f processing/Dockerfile -t tabbytally-processing .
docker run --rm tabbytally-processing --help
```

Compose validation in PowerShell (uses no live configuration):

```powershell
$env:RECEIVER_NETWORK='verification-placeholder'
docker compose -f processing/compose.yaml -f processing/compose.model.yaml config --no-env-resolution --quiet
```

Remove the isolated test containers/network after the run:

```text
docker compose -f processing/compose.test.yaml down
```

Integration coverage includes activation during an uncommitted capture, repeated/concurrent
scans, concurrent claims/recovery, crash after claim, crash after fake processing, interrupted
save transaction, persisted completion after reconnect, stale completion/heartbeat/failure,
database connection termination/reconnect, transient retries, timeout, exhaustion and
operator retry/pause, migration drift/checksum rejection, runtime/operator/inspection
permissions, fake IMAP unread preservation and source immutability, archive corruption
rejection, and combined restore recovery.

Crash tests kill subprocesses; no production crash hooks exist. The lost-acknowledgement
case verifies persisted completion after reconnect rather than injecting packet loss at
the network layer. The database-outage case terminates a connection; a fleet-wide host
failure or physical disk-loss drill has not been performed. The IMAP test uses a synthetic
server implementation; this is not a second live-inbox verification.

## Deployment prerequisites and limits

- Confirm placement and private database connectivity. The supplied deployment Compose
  expects a same-host external receiver network; remote-node TLS/firewall configuration
  remains deployment work.
- Provision login secrets locally and validate their inherited role privileges. Runtime
  group roles and positive/negative permission tests are implemented.
- Rebuild the receiver backup image and enable `--include-processing` in the actual backup
  schedule. Protect off-host copies and choose retention/recovery objectives.
- Inspect and explicitly activate the intended source scope. Fake versions cannot produce
  financial candidates and must not be reused for a later real processor.
- Health currently reports schema/database readiness; loop progress is inspected through
  backlog/attempt state and process status, not a separate persisted heartbeat table.
- The model transport is tested using a local HTTP server, including Basic auth, schema
  requests, aliases, 429/503 retries, 401/302 rejection, malformed/oversized responses,
  unsafe Unicode/NUL, subprocess deadlines, input limits and configuration identity.
  Actual authenticated HTTPS access, weight hashes and GPU fit remain unverified. Local
  generation/selected-field checks are recorded above; no representative anonymized bank
  corpus has been evaluated.
- Extraction tests verify durable malformed-output review, atomic save rollback, stale
  worker fencing, duplicate suspicion, source immutability, permissions and populated
  backup/restore. Financial tests cover precision, amount evidence, balances, accounts,
  foreign purchases, dates, movement/loan treatment and conservative review gating.
- Fixes made during verification: reject partial-number evidence matches; explicitly flag
  unknown lifecycles; reject invalid Unicode/NUL model content; retain sanitized model
  failure codes in attempt history. Regression tests cover these changes.
- Production rollout, external notifications and Actual writes remain outside this
  implementation. Transfer counterpart linking, bank-specific interpretation and promotion
  to eligible candidates remain unfinished. The full pipeline repeats acceptance in 2.4.

Operational commands and recovery ordering are documented in [processing/README](../../processing/README.md).

### 16 October 2026 — corpus and budget update

- All 264 supplied emails evaluated offline; 99 narrow template proposals and 165
  fallback/review messages. Selected negative cohort: 54; template false positives: 0.
  These are coverage checks, not full extraction accuracy. See CORPUS_EVALUATION.md.
- 57 automated processing tests passed (17.216 seconds), including PostgreSQL
  crash/retry/fencing and backup/restore checks, financial validation, negative template
  cases, normalization bounds and adaptive model-budget/truncation metadata checks.
- Production Docker image build and CLI help passed. Disposable test containers removed.
- Prompt v3 explicitly includes the schema. Normalizer v2 allows bounded HTML markup
  before enforcing visible-text size; eight formerly oversized messages now readable,
  twelve messages still have no readable body.
- Output target 6144, minimum 4096, context 8192, reserve 512. Server-template token
  preflight determines actual allowance. Model worker deadline/lease/grace are
  1200/1320/1230 seconds. No raw reasoning is retained.
- Live thinking=true probe on normal profile, alias fast -> qwen3.5-9b: purchase and
  foreign cases both exhausted 6144 completion tokens with model_output_incomplete.
  Measured prompt tokens were 1210 and 1201 respectively; routing observations stayed
  normal. More time/output did not establish accuracy. Example defaults to thinking=false.
- No production pipeline activation, Actual writes or inbox modifications performed.
  Authenticated LAN service-account setup remains outstanding; loopback synthetic probes
  do not establish authenticated deployment readiness.

Final live comparison: the reminder also exhausted 6144 tokens with thinking enabled
(1201 prompt tokens). With thinking disabled, all three synthetic cases passed the
probe's schema and selected-field checks: purchase 8.110 s / 476 output tokens;
foreign purchase 5.765 s / 445 output tokens; reminder 0.922 s / 58 output tokens.
The foreign case retained USD 12.50 without inventing an INR billed amount; the
reminder produced no events. Prompt v3, temperature 0.7, normal-profile fast alias,
reported Qwen3.5-9B-Q6_K.gguf. These are one-run smoke results, not full-field corpus
accuracy or proof of a weight hash. Thinking is disabled in the example configuration.

### 17 October 2026 — full corpus verified; prompt candidates rejected

The saved baseline contains all 264 inputs: 248 valid model responses, 12 input-review
cases, three budget refusals and one invalid response. Financial-event detection and
amount/currency correctness: 161/163. Negative false transaction proposals: 0/89;
five negatives remained unsupported/refused. Median/p95: 6.13/7.27 seconds; 19.79 minutes
active adapter time. See MODEL_BENCHMARK.md for field denominators and date-policy caveats.

Resumed prompt experiments after usage reset. The broad rewrite generated OTP false
positives; the narrow v6 date addition achieved 13/22 paired all-fields matches versus
baseline 15/22. Neither was promoted. Restored v3 prompt hash
edf55e14c43183d130abdff83782002cbf6838e7196899b9c749811703c5b1ff.
61 isolated regression tests passed (19.783 seconds on latest candidate adapter);
restored prompt matches the fully benchmarked baseline. Configurable temperature,
private benchmark/resume tooling and scorer tests are retained. No production activation.
