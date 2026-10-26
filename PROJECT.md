---
project: tabbyTally
status: paused
status_reason: "Integration development has not resumed after its dependency gate cleared; implementation remains off main."
resume_trigger: "Owner resumes polling integration; imports will be started manually later."
last_activity: 2026-09-22
last_reviewed: 2026-10-23
repo: https://github.com/purrMonster/tabbyTally
related: ["[[meowGram]]"]
tags: [project]
---

# TabbyTally

## What it is
Self-hosted bank-email capture and transaction extraction for a single-user Actual Budget workflow, with statement reconciliation planned.
Python and PostgreSQL handle capture, durable jobs and validation; a local model assists extraction.
A Node.js Actual bridge is planned for Phase 3. The JavaScript IMAP listener is an older prototype ([project overview][overview]).

## Current state
| Area | State | Evidence |
|---|---|---|
| Code | Partial: main contains only README; receiver and Phase 2 processing/review implementations are on unmerged branches. Actual writes are planned. | [Main baseline][main], [receiver][receiver], [processing snapshot][processing] |
| Release | None; owner confirmed on 2026-10-23 that no published image or release exists elsewhere. | [Owner confirmation][owner-confirmation]; [local build verification][verification] |
| Deployment | Receiver still running, owner-confirmed 2026-10-23; imports will be started manually later. No fresh health probe or processing rollout. | [Owner confirmation][owner-confirmation], [processing rollout record][rollout] |
| Tests / CI | Passing in recorded local runs: 41 receiver tests (2026-10-15), 95 processing tests (2026-10-21). No GitHub workflow files in main or the published WIP tree; no fresh suite run for this card. | [Receiver ledger][receiver-runbook], [processing ledger][polling] |

The nine previously local commits are published on the Phase 2 branch, with [owner decisions][owner-confirmation] recorded in one follow-up commit; they remain off main.
The [latest runbook][runbook] records sample approval, the polling decision, and the dependency gate clearing on 2026-10-23; integration implementation has not resumed.

## Open points
- Review [Phase 2 PR #2](https://github.com/purrMonster/tabbyTally/pull/2) before merging; implementation remains off main ([runbook][runbook]).
- When work resumes, implement durable meowGram send/sync polling and verified LLDAP reviewer-group authorization; replace the superseded inbound-callback design ([decision][polling], [cleared gate][gate]).
- Complete integrated acceptance, recovery checks and a separately authorized processing rollout ([acceptance gates][acceptance]).
- Recheck backup scheduling/off-host recovery before future rollout; completion is unverified and the owner closed the current status question. Actual writes and statement reconciliation remain later phases ([owner confirmation][owner-confirmation], [plan][plan]).

## Branches
- `origin/codex/imap-receiver-foundation` — `48dae7d`, 2026-10-15: receiver and Phase 2 handoff; older, unmerged foundation, superseded for ongoing work by WIP.
- `origin/tabbytally/phase-2-wip` — `f8f7b59`, 2026-10-23: processing/review implementation and current decisions; now published, awaiting review, no longer behind local history.
- `docs/project-card` — this documentation-only delivery branch from main; awaiting owner review.

## Key decisions
- 2026-10-15 · Python/PostgreSQL own processing; capture remains independent and Actual writes stay in Phase 3 · [phase boundaries][boundaries].
- 2026-10-18 · Use labelled deterministic fallbacks for missing dates/accounts; keep financial validation in code · [fallback policy][fallbacks].
- 2026-10-18 · The displayed 25-row sample, including recipient/sender, was approved; this does not certify the whole corpus · [sample approval][sample].
- 2026-10-21 · Poll meowGram using bot auth; no inbound callback; authorize reviewers through LLDAP groups; chat carries references only · [polling decision][polling] (supersedes [callback prototype][callback]).
- 2026-10-23 · Required meowGram stories reached its main via [R2 merge][r2]; development gate is cleared, without rollout authorization · [gate verification][gate].
- 2026-10-23 · Publish preserved work for review; receiver remains running, owner will start imports manually later; no published release exists · [owner decisions][owner-confirmation].

## How to resume
1. Check `git status`, fetch origin, and inspect `tabbytally/phase-2-wip`; read the [runbook][runbook] newest-first before switching or merging anything.
2. Review the published implementation, then implement polling against merged meowGram R2 when work resumes; preserve the settled group-authorization and references-only policy.
3. Run the [isolated test procedure][tests] and new polling/replay/authorization checks. Keep credentials local; request separate rollout authorization only after acceptance.

## Decisions to remake
- Revisit the callback-specific implementation and tests when replacing transport with polling; their previous passing results do not validate polling ([decision][polling], [gate][gate]).
- Reassess deployment placement and recovery scheduling before rollout, using the [operations prerequisites][rollout].

## Questions for Roastmaster
- None outstanding for this handoff; [owner answers recorded on 2026-10-23][owner-confirmation].

## Card history
- 2026-10-23 · created by Codex; checked refreshed remote refs and local implementation history, without changing implementation or deployment.
- 2026-10-23 · updated by Codex after owner answers and Phase 2 publication; replaced local-only citations with remote decision links.

[main]: https://github.com/purrMonster/tabbyTally/tree/be60adfe5ae8d72d69cbaf521eb503e7b215ea1f
[overview]: https://github.com/purrMonster/tabbyTally/blob/77d93ff/README.md
[receiver]: https://github.com/purrMonster/tabbyTally/tree/48dae7d/imap-receiver
[processing]: https://github.com/purrMonster/tabbyTally/tree/77d93ff/processing
[receiver-runbook]: https://github.com/purrMonster/tabbyTally/blob/48dae7d/imap-receiver/runbook.md#2026-10-15--phase-1-completion-and-phase-2-planningpublication
[verification]: https://github.com/purrMonster/tabbyTally/blob/77d93ff/docs/processing/VERIFICATION.md
[rollout]: https://github.com/purrMonster/tabbyTally/blob/77d93ff/docs/processing/RUNBOOK.md#8-controlled-deployment-procedure--not-yet-executed
[acceptance]: https://github.com/purrMonster/tabbyTally/blob/77d93ff/docs/processing/RUNBOOK.md#remaining-external-acceptance-gates
[plan]: https://github.com/purrMonster/tabbyTally/blob/77d93ff/docs/processing/PLAN.md
[boundaries]: https://github.com/purrMonster/tabbyTally/blob/77d93ff/docs/processing/RUNBOOK.md#2-decisions-and-phase-boundaries
[fallbacks]: https://github.com/purrMonster/tabbyTally/blob/77d93ff/docs/processing/RUNBOOK.md#21-discussion-decisions-and-practical-fallbacks--18-october-2026
[callback]: https://github.com/purrMonster/tabbyTally/blob/77d93ff/docs/processing/RUNBOOK.md#callback-api-and-deployment-contract
[r2]: https://github.com/purrMonster/meowGram/pull/49
[tests]: https://github.com/purrMonster/tabbyTally/blob/77d93ff/docs/processing/RUNBOOK.md#71-repeat-the-complete-isolated-checks
[runbook]: https://github.com/purrMonster/tabbyTally/blob/f8f7b59/docs/processing/RUNBOOK.md
[sample]: https://github.com/purrMonster/tabbyTally/blob/f8f7b59/docs/processing/RUNBOOK.md#25-recipient-approval-and-next-integration-item--18-october-2026
[polling]: https://github.com/purrMonster/tabbyTally/blob/f8f7b59/docs/processing/RUNBOOK.md#30-polling-bot-decision-integration-parked--21-october-2026
[gate]: https://github.com/purrMonster/tabbyTally/blob/f8f7b59/docs/processing/RUNBOOK.md#33-meowgram-dependency-gate-verified--23-october-2026
[owner-confirmation]: https://github.com/purrMonster/tabbyTally/blob/f8f7b59/docs/processing/RUNBOOK.md#34-publication-authorization-and-project-card-answers--23-october-2026
