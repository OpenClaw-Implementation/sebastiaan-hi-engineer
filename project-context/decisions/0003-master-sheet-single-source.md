<!-- template: pogan-context v2 · project-context/decisions/NNNN-title.md -->
# 0003 — A master Google Sheet is the single source before Softr
Status: accepted
Source: meeting 2026-10-09; client email 2026-10-09 ("make 1 masterfile Excel/google sheets and start uploading in softr").

**Decision.** Merge the database with the client's spreadsheets into one master file (Google Sheets preferred,
because Sales Navigator exports go there), deduplicate and clean it, then migrate into Softr automatically.
Pilot with 5 companies, then hundreds.
**Consequence.** Dedup rules and a database → sheet export are needed; the sheet, not the app, is what the
client edits before Softr.
