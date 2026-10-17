<!-- template: pogan-context v2 · CLAUDE.md (repo root) -->
# Hi-Engineer — index

Everything this project knows lives in `project-context/`. This file only says where. Read the files your task
needs; do not read them all every time.

| File | What it holds | Read it when |
|---|---|---|
| `project-context/GOALS.md` | Destination, why, what this repo is for, who decides what, out of scope | Starting a task; judging scope |
| `project-context/ARCHITECTURE.md` | What exists now: where it runs, components, data stores, integrations, flows | Before touching code or data |
| `project-context/WORKFLOW.md` | How a request becomes a ticket, work, checks, a deploy and a reply draft | Every task, at start and finish |
| `project-context/FRAMEWORK.md` | How to run, test and ship; project rules; "What deployed means here" | Before running, testing or deploying |
| `project-context/HEALTH.md` | Services this project needs, the checks proving we can deploy and verify, what needs a person | Before deploying; when a login or service fails; health-check tickets |
| `project-context/PLAN.md` | Milestones: done, current in full, later sketched | Choosing or scoping work |
| `project-context/GLOSSARY.md` | Project terms and Pogan terms (ticket, deployed, health check…), one line each | A word in a ticket is unclear |
| `project-context/decisions/` | One file per decision already made, with its source | Before reopening a settled question |
| `project-context/sources/` | Digests of meetings and messages | Checking what the client actually said |
| `project-context/milestones/M3/MAP.md` | Current milestone: dated notes, decisions, open questions | Working on the current milestone |
| `project-context/archive/` | Older notes whose facts were folded into the files above | Only to trace where a fact came from |

Other material:
- `docs/` — client-facing deliverables already sent: documentation, roadmap, enrichment cost guide (`*.html`),
  investigation report (`*.pdf`), review workbook (`*.xlsx`), the original proposal
  (`proposal-and-next-milestones.md`) and the 2026-07-14 enrichment run report
  (`companies-cascade-run-2026-07-14.md`), plus the scripts that build the report and workbook
  (`build_report.py`, `build_excel.py`). They contain commercial figures: do not copy those into the context files.
- `../tasks/YYYY-MM-DD-*.md` (next to the repo, not in git) — older per-task logs with history and numbers; client
  attachments and per-row check results also sit there and must stay out of git.

## After every task
Follow `project-context/WORKFLOW.md` → "Keeping the context current". Never create new status or notes files at the
repo root (CONTEXT.md, NOTES.md, STATUS.md, TODO.md…): the fact goes into the file above that owns it.
