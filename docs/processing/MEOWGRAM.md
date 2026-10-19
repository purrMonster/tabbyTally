# meowGram delivery and review connection

18 October 2026. **Consumer, provider endpoint and authenticated action bridge
implemented and locally tested; not deployed.** Provider code is on meowGram branch
`feat/tabbytally-review-integration` in the isolated `.worktrees/meowgram` checkout.
It integrates the existing bot-auth, bot-principals and shared-service branches.
The original checkout, credentials and live services remain untouched. Do not
enable this client against the WebSocket ticket or sync routes.

## Implemented durable-send-v1 provider contract

The endpoint is configured as a complete HTTPS URL; no route is assumed. Authenticate
with a dedicated bot service account using HTTP Basic over verified TLS. The bot
identity and message destination must be restricted by the provider configuration.
Never use a human password or include credentials in the URL. The adapter does not
follow redirects or disable certificate verification.

Request: POST with `Content-Type: application/json`, `Idempotency-Key: <outbox UUID>`
and body `{"text_content":"..."}`. Only a review UUID, revision, state and generic
instruction are sent. No bank email, recipient, amount, account number, model output,
callback signing key or approval link is sent.

Required successful response, after a durable commit:

```json
{"id":"provider-message-id","idempotency_key":"same-outbox-UUID","persisted":true}
```

Use 201 for first creation, 200 for an identical replay. The provider must atomically
persist the message and its receipt, scoped to the authenticated bot and key.
Concurrent or later identical retries must return the original receipt without
creating a second message. The same key with different text must return 409.
Retain receipts for as long as a processing backup could be restored and replayed;
do not expire them on a short HTTP retry window. Persistence must precede broadcast;
a broadcast failure after commit must still allow receipt recovery on retry.

The client accepts only 200/201 with matching key, a nonempty message ID and
`persisted: true`. It rejects 202, redirects, malformed/oversized responses and all
other status codes. The existing outbox retries failures up to five attempts with
backoff, retaining exhausted rows. This includes authentication failures: fix local
configuration before explicitly requeueing an exhausted item. Preserve its UUID.
There is no internal HTTP retry; the durable outbox owns retries. A child process
enforces the whole 20-second delivery deadline, below the 60-second claim lease.

## Enable only after provider acceptance

1. Review and deploy the meowGram integration branch and its dependencies with
   owner approval. Set `MESSAGE_SEND_ENDPOINT` to the desired API path. Messages
   go to the existing shared lounge; only generic review notifications belong here.
   Verify the deployed route and bot authorization.
2. Run synthetic requests: first send, identical replay, concurrent replay,
   conflicting text, wrong credentials, timeout after commit, provider restart,
   and replay after restoring processing state. Count stored messages: exactly one
   per bot/key. Mock client tests do not establish this provider guarantee.
3. Provision approved local service-account credential files. Copy
   `processing/.notify.env.example` to `.notify.env`; set the actual HTTPS route.
   Only after step 2 passes set `MEOWGRAM_VERIFIED_CONTRACT=durable-send-v1`.
   This flag is an operator attestation, not an automatic compatibility probe.
4. Use the separate reviewer database login already described in RUNBOOK section
   22. Mount its password and both meowGram credential files through Compose secrets.
   `compose.notify.yaml` adds only the opt-in notification worker; no ports exposed.
5. From `processing/`, after setting `RECEIVER_NETWORK`, run one delivery first:

```powershell
docker compose -f compose.yaml -f compose.notify.yaml run --rm notifier notify
docker compose -f compose.yaml -f compose.notify.yaml run --rm notifier notifications
```

6. Verify the synthetic message in meowGram, then start the worker:

```powershell
docker compose -f compose.yaml -f compose.notify.yaml up -d notifier
```

Stop with the same Compose files and `stop notifier`. Email capture and processing
continue independently. `notify --loop --interval 5` checks the durable queue; this
is not the cancelled daily 09:00 scheduler. Configuration errors fail before any
claim. Logs expose only outcomes/error classes. Neither live credentials nor a
working provider URL are checked in.

## Review actions: receiver and implemented meowGram bridge

Notifications currently direct the operator to the private processing console.
Use `reviews`, `review-show <UUID>` and `review-action --file <private-json>` today.
Recipient/sender remain available in the private verification report. Do not turn
notification text into an executable approval command.

The bridge authenticates the human through existing meowGram OIDC middleware and
allowlists their stable subject. Set `REVIEW_ACTION_ENDPOINT`, `REVIEW_CALLBACK_URL`
(HTTPS), `REVIEW_SIGNING_KEY_FILE` and `REVIEW_ALLOWED_SUBJECTS` in meowGram; the
same subjects must appear in processing's `REVIEW_ALLOWED_ACTORS`. Both services
read the same local signing key with surrounding whitespace trimmed. The bot's
send credential cannot authorize decisions. Client actions must bind the displayed
review UUID/revision and reuse the action ID on retries. Flutter buttons are not
part of this HTTP bridge increment.

The existing receiver is POST `/review/actions`. Send the exact JSON bytes with
`action_id` (stable across retries), `review_id`, integer `revision`, `action`
(`approve`, `correct`, `ignore`, `defer`) and `reason`. Corrections supply full
`facts`; transfer/card repayment approvals require explicit `treatment` according
to `review.decide`. Use a new action ID for a genuinely new decision.

Headers: `X-Review-Timestamp` (Unix seconds), `X-Review-Actor` (authorized stable
human ID), and `X-Review-Signature` (hex HMAC-SHA256 of timestamp + newline + actor
+ newline + exact body, using the private review signing key). Never expose that
key to browser code or message content. Transport the callback on a private trusted
connection; the HTTP listener is loopback by default, so a remote bridge needs a
TLS reverse proxy or private tunnel configured separately.

The receiver checks a five-minute timestamp window, actor allowlist, payload size
and action receipts. On a timeout retry the identical body/action ID, with a fresh
timestamp/signature if needed. 200 returns a committed result; 403 means fix auth;
409 means stale/conflicting/invalid action: refresh the review, never auto-approve
a newer revision; 503 permits retry. Test forged actor/signature, expired timestamp,
replay, conflicting action ID and concurrent/stale corrections before enabling
in-app actions. Decisions and updated notifications commit atomically.

## Reproduce the cross-project acceptance test

From the tabbyTally root, point at the integration branch's server checkout:

```powershell
$env:MEOWGRAM_SERVER_PATH = (Resolve-Path '.worktrees/meowgram/server').Path
docker compose -f processing/compose.bridge.test.yaml up --build --abort-on-container-exit --exit-code-from bridge-test --attach bridge-test
docker compose -f processing/compose.bridge.test.yaml down --volumes
```

This uses synthetic data, a disposable PostgreSQL database and the actual Python
review API. A temporary TLS proxy exercises the Go bridge's signed HTTPS request.
It checks first decision, identical replay, stale revision, conflicting action ID
and exactly one committed decision. The separate meowGram Go suite tests real OIDC
JWT verification, the bot gate, durable send receipts/concurrency, publication
failure, actor spoofing and provider errors. LDAP authentication is emulated in the
route integration test; existing directory tests cover that component separately.
No live directory or account credentials are used.
