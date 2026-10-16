# Hi-Engineer — index

This file is an index. Facts live in the files below; read the ones your task needs.

| File | What it holds | Read it when |
|---|---|---|
| `GOALS.md` | Destination, why, who decides what, out of scope | Starting any task; judging whether a request is in scope |
| `ARCHITECTURE.md` | What exists now: components, tables, integrations, hosting, data flows | Before touching code or data |
| `WORKFLOW.md` | How a client message becomes a ticket, work, checks, deploy and a reply draft | Every task (start and finish) |
| `FRAMEWORK.md` | How to run, test and ship; project rules; "What deployed means here" checks | Before running, testing or deploying |
| `PLAN.md` | Current milestone in full, later ones sketched | Choosing or scoping work |
| `GLOSSARY.md` | Project terms, one line each | When a word in a ticket is unclear |
| `docs/adr/` | One file per decision already made, with its source | Before reopening a settled question |
| `docs/sources/` | Digests of meetings and the email/WhatsApp history | Checking what the client actually said |
| `docs/waves/M3/MAP.md` | Current milestone map: notes, decisions, open questions | Working on the current milestone |

Other material:
- `../tasks/YYYY-MM-DD-*.md` — one log per finished task (history, details, numbers).
- `../CONTEXT.md` — short current-status note for the operator.
- `docs/*.html`, `docs/*.pdf`, `docs/*.xlsx` — client-facing reports already sent (documentation, roadmap,
  enrichment cost guide, investigation report, review workbook). They contain commercial figures; do not copy
  those into the context files.

## Post-task protocol
After every task: update the affected context file(s) above (ARCHITECTURE for what changed in the system,
PLAN/MAP for progress, a new ADR for any new decision), update `../CONTEXT.md`, and log the task in
`../tasks/` as `YYYY-MM-DD-description.md`. See `WORKFLOW.md` → "Keeping the repo files current".
