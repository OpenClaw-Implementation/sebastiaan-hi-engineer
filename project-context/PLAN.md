<!-- template: pogan-context v2 · project-context/PLAN.md -->
# Plan — milestones

Based on the 2026-10-09 meeting and the October emails. Current milestone details and open questions:
`project-context/milestones/M3/MAP.md`.

## Done
- **M1 — Scraping engine and supplier database** (May–July 2026). Trade-show scrapers, normalised `companies`,
  enrichment cascade, Logs/Stats. Cristian proposed closing it on 2026-07-31.
- **M2 — Content engine, first part** (July–October 2026). Jobs and news pipelines from supplier sites, role and
  topic tagging (rules + AI), master Excel import, Dashboard/Contacts/Taxonomy/Export pages (deployed 2026-10-09).
  Left out of the original content-engine scope: RSS detection, AI article summaries, media portals.

## M3 — Netherlands supplier master file into Softr (current, October–November 2026 (estimate))
**Goal.** One clean, deduplicated master file of Dutch suppliers (companies + contact people) built from the
database and the client's own spreadsheets, enriched with the agreed (cheaper) route, and loaded into Softr —
first 5 companies as a pilot, then hundreds.

**Done when** (each line can be checked by a person):
1. The Bizzy supplier list (email 2026-10-09) and the Industrial_Engineering_NL_BB_19972 file (email 2026-10-15)
   are imported or matched: every company in them can be found on the Companies page, with no duplicate company
   names, and the client's 10-15 question has been answered in a reply Cristian sent (emails 2026-10-09, 10-15).
2. Missing contacts for imported suppliers are found with the agreed enrichment route; the Logs page shows the run
   with its cost per step, and the Contacts page shows the new people (email 2026-10-09; WhatsApp 2026-10-09).
3. Contacts per company are picked by the client's role list: founder/CEO/director, sales lead, technical lead,
   HR (email 2026-06-19).
4. A master Google Sheet exists, shared with the client, with one row per supplier and its contacts, generated
   from the database, with no duplicate companies (meeting 2026-10-09, ADR 0003).
5. 5 pilot companies are visible in the client's Softr app with the agreed fields, and the client confirms the
   mapping (meeting 2026-10-09).
6. The remaining suppliers are loaded into Softr (hundreds), with a repeatable way to refresh them
   (meeting 2026-10-09).

**Housekeeping** (needed, but not what this milestone is judged on):
- Daily jobs/news runs scheduled on Heroku Scheduler, so the Logs page shows a run in the last 7 days
  (email 2026-07-31 said runs were daily; they are not).
- Heroku ownership transferred to the client's account, Cristian stays developer (email 2026-09-23; meeting
  2026-10-09).
- Set `ENABLE_APOLLO=false` before the next bulk run (ADR 0004).

## Later (sketches)
- **M4 — Access and monetisation layer (Dec 2026–Jan 2027 (estimate)).** Search and navigation on top of the data;
  freemium (company names and general info free, contacts paid); rate limits, export limits, tiers
  (meeting 2026-10-09).
- **M5 — Platform launch, Q1 2027.** Softr platform live with supplier and plant data for the Netherlands; rest of
  NL suppliers and manufacturers (meeting 2026-10-09; email 2026-06-19).
- **M6 — Jobs board and news (2027 (estimate)).** jboard.io-style board with the agreed roles; news on
  beehiiv/Circle with agreed tags; then copy the workflow to the next country (emails 2026-08-30, 09-24).
