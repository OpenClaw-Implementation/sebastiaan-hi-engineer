<!-- template: pogan-context v2 · project-context/sources/YYYY-MM-DD-<meeting|messages>-<slug>.md -->
# 2026-10-09 · "Seb <> Pogan" · Cristian + Sebastiaan (36 min) — latest direction
Source: Granola summary in PIT (full transcript held in PIT; action extraction not run).

- **Priority.** Suppliers first (data and accounts), not jobs or other features. Netherlands first; perfect the
  workflow, then copy to other countries. Target: launch on Softr in Q1 2027 with supplier and plant data.
- **Data.** Said to be "700–900 records already in Supabase", incl. everything from his Excel. (The live database
  is Heroku Postgres with 3,066 companies and 791 contacts — see ARCHITECTURE.)
- **Enrichment.** Best combination named: SERP API + AI Ark (as in July). New integrations named: "DadaGo",
  Brave, Lusha. Apollo kept as fallback only (resale clause in its terms). → ADR 0004.
- **Firecrawl.** Said to be out of credits, so full enrichment was paused; Cristian to send a breakdown of credits
  needed per integration; Sebastiaan decides the spend.
- **New file.** Sebastiaan sends another supplier Excel (from a separate AI tool); Cristian maps it, dedups, and
  queues missing contacts.
- **Softr.** Sebastiaan buys Softr; Airtable dropped (ADR 0002). Master Excel/Google Sheet as single source →
  merge, dedup, clean → migrate into Softr automatically; pilot with 5 companies, then hundreds (ADR 0003).
- **UX/monetisation idea.** Search and navigation on top of the data; freemium (company info free, contacts
  paid); needs access controls (rate limits, export limits, tiers) before opening to users.
- **Next.** Cristian sends the Heroku ownership transfer link so Sebastiaan owns the app.
