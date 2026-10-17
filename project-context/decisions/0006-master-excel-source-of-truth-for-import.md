<!-- template: pogan-context v2 · project-context/decisions/NNNN-title.md -->
# 0006 — The client's master Excel is imported as a source of truth
Status: accepted
Source: decision in the Claude session 2026-10-08 (operator choice); client emails 2026-06-19 and 2026-08-30 with the workbook.

**Decision.** Everything in the client's master Excel is imported (companies, contacts, role sheets, taxonomy).
Re-imports update the database; scraper-found news/jobs pages are never overwritten.
**Consequence.** The directory grew to 3,066 companies and 791 contacts; the 11-category taxonomy from the
`topics` sheet is canonical.
