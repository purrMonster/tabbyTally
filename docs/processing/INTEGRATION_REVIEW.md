# Integration review and deployment hold — 21 October 2026

**Superseded by the user's polling-bot decision (RUNBOOK §30).** No inbound
callback; LLDAP reviewer-group authorization, subjects for audit only, references-
only chat. Parked until UST-2.4.2 and UST-2.4.3 merge into release/r2.
The record below describes the earlier review, not the selected design.
The placeholder inventory now reflects the polling design.

## Scope and ownership

This change implements tabbyTally Phase 2.3 review notifications and decisions on
meowGram branch `feat/tabbytally-review-integration` (implementation `cffda0d`).
No PR has been opened and no new R2 story ID was assigned. It locally integrates
the existing bot authentication, bot principal and shared message-service branches;
it must not be represented as an approved expansion of the R2 message-API story.

The user clarified that R2 covers the message API and pourOver polls. Message
delivery/polling does not require an incoming review callback. The implemented
callback bridge is an additional tabbyTally push-review design; its deployment is
on hold pending the user's scope/topology decision. Do not assume pourOver already
parses or authorizes financial review commands: that consumer has not been inspected
or integrated by this task.

## What receives what

The **IMAP email receiver** captures email into PostgreSQL. It is unrelated to the
optional callback URL. The **processing review API** receives signed financial
approve/correct/ignore/defer actions from meowGram's proposed human review bridge.
The latter needs reachable HTTPS only if that push topology is selected. A polling
consumer can fetch messages without a publicly or privately routed inbound callback
hostname; applying actions still requires its own authenticated authorization and
repeat-safe processing design.

## Identity and authority

The current bridge checks the verified OIDC subject against REVIEW_ALLOWED_SUBJECTS,
then signs that subject as the audit actor. The Python service checks the same actor
against REVIEW_ALLOWED_ACTORS. This permits review/correction/ignore/defer decisions
on processing candidates, including changing import readiness; it does not authorize
Actual Budget writes or changes to email capture. The bot send credential grants
message sending only and cannot authorize those decisions.

A verified group/role policy can replace the per-person authorization allowlist,
while preserving each user's stable subject as the audit actor. That requires
deliberately validating the issuer's group/role claim and changing both sides of
the authorization contract; the current bridge and Python receiver do not implement
that policy. Never trust a group supplied in a message body or arbitrary header.
No owner subject or group is selected by this preparation.

## Review findings and chosen fixes

1. Optional routes could collide with an existing configured route and panic at
   ServeMux registration. Fix: reject collisions explicitly during startup, with
   regression coverage for canonical and customized routes.
2. Python callback throttling returned 403, which the bridge treated as an auth
   failure. Fix: return 429 and Retry-After: 1 without reapplying the decision;
   exercise two signed HTTP requests and check exactly one decision invocation.

Reviewed the atomic message/receipt transaction, sender-scoped replay key, changed-
content conflict, authentication on every send retry, OIDC-derived review actor,
callback signature/size/timeout/redirect handling and secret-file boundaries.
Earlier race, restore and cross-project acceptance evidence is in RUNBOOK §27–28.
This is a scoped code review, not approval of a live infrastructure configuration.

## Prepared files and restrictions

`processing/deployment/.env.example` contains placeholders only, including the
user-requested RECEIVER_HOST, CALLBACK_HOST and OWNER_OIDC_SUB names. Copy it to
`integration.host.env` on the intended host only when configuration work resumes.
That filename is ignored by Git and Docker context. It is an inventory for later
configuration, not a directly runnable deployment. Existing Compose examples remain
opt-in; this inventory does not enable them or create any routes.

Record real values only in the ignored host-local file and credentials only in
protected host-local secret files after the user resolves scope/authorization.
No credentials are generated, read, rotated or provisioned by this preparation.
No DNS, Authelia, LLDAP, live database or live services may be changed. No deployment
is authorized while the user's hold is active.
