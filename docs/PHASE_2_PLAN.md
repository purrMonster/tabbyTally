# Phase 2 — Python processing

The authoritative end-to-end plan has moved to [docs/processing](processing/README.md).
Python replaces the earlier n8n orchestration proposal. PostgreSQL owns processing state.

- [Delivery plan](processing/PLAN.md)
- [Architecture and durable jobs](processing/ARCHITECTURE.md)
- [Extraction, validation and review contracts](processing/CONTRACTS.md)
- [Operations and acceptance](processing/OPERATIONS.md)
- [Processing node](../processing/README.md)

Start with milestones M1–M3: schema and backup coverage, explicit activation and durable
job discovery, then claims/retries/crash recovery with a fake processor. Model integration
follows those gates. Phase 2 ends with validated candidates, ignored messages, review items
and inspectable exhausted jobs. Actual Budget writes remain Phase 3.

Status: Phase 2.1 verified locally; Phase 2.2 review-only extraction passes synthetic tests
but still needs real-model and bank-format acceptance. Phases 2.3–2.4 remain planned.
No live processing deployment. See [verification](processing/VERIFICATION.md).
Updated 16 October 2026.
