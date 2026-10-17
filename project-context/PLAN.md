# Plan — milestones

Based on the 2026-10-09 meeting and the October emails. Details and open questions for the current milestone:
`docs/waves/M3/MAP.md`.

## Done
- **M1 — Scraping engine and supplier database** (May–July 2026). Trade-show scrapers, normalised `companies`,
  enrichment cascade, Logs/Stats. Cristian proposed closing it on 2026-07-31.
- **M2 — Content engine, first part** (July–October 2026). Jobs and news pipelines from supplier sites, role and
  topic tagging (rules + AI), master Excel import, Dashboard/Contacts/Taxonomy/Export pages (release v42,
  2026-10-09). Not done from the original content-engine scope: RSS detection, AI article summaries, media portals.

## M3 — Netherlands supplier master file into Softr (current, October–November 2026)
**Goal.** One clean, deduplicated master file of Dutch suppliers (companies + contact people) built from the
database and the client's own spreadsheets, enriched with the agreed (cheaper) route, and loaded into Softr —
first 5 companies as a pilot, then hundreds.

**Done when** (each line can be checked by a person):
1. The Bizzy supplier list (email 2026-10-09) is imported: every company in it can be found on the Companies page,
   with no duplicate company names.
2. The Industrial_Engineering_NL_BB_19972 file is imported or matched the same way, and the client's question
   about it (email 2026-10-15) has been answered in a reply Cristian sent.
3. Missing contacts for imported suppliers are queued and the agreed enrichment run has finished; the Logs page
   shows the run with its cost per step, and the Contacts page shows the new people.
4. The client's role list (founder/CEO/director, sales lead, technical lead, HR) is the filter used to pick
   contacts per company.
5. A master Google Sheet exists (shared with the client) with one row per supplier and its contacts, generated
   from the database, with no duplicate companies.
6. 5 pilot companies are visible in the client's Softr app with the agreed fields; the client confirms the mapping.
7. The remaining suppliers are loaded into Softr (hundreds), with a repeatable way to refresh them.
8. Daily jobs/news runs are scheduled and the Logs page shows a run in the last 7 days.
9. Heroku ownership has been transferred to the client's account (Cristian stays developer).

**Open questions** — see `docs/waves/M3/MAP.md` (with recommended answers).

## Later (sketches)
- **M4 — Access and monetisation layer (Dec 2026–Jan 2027).** Search and navigation on top of the data;
  freemium (company names and general info free, contacts paid); rate limits, export limits, tiers.
- **M5 — Platform launch, Q1 2027.** Softr platform live with supplier and plant data for the Netherlands;
  rest of NL suppliers and manufacturers.
- **M6 — Jobs board and news (2027).** jboard.io-style board with the agreed roles; news on beehiiv/Circle with
  agreed tags; then copy the workflow to the next country.
