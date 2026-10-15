# IMAP Receiver

Planning documents for a reusable, self-hosted service that receives new email from multiple IMAP accounts and folders in one container and stores it in PostgreSQL.

| Document | Purpose |
|---|---|
| [Ideation](IDEATION.md) | Problem, scope, alternatives, and decisions |
| [Design](DESIGN.md) | Architecture, data model, capture lifecycle, and failure handling |
| [Implementation plan](PLAN.md) | Guided build stages, tests, and completion criteria |

Status: design prepared on 15 October 2026; production implementation pending.

The existing `../imap-listener/` directory is an earlier prototype. It still contains n8n webhook delivery and is not an implementation of this design. These documents define the intended database-only receiver. No prototype files were moved or changed as part of this documentation task.

Start with IDEATION.md, then DESIGN.md. Follow PLAN.md when implementation begins.
