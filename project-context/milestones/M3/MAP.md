<!-- template: pogan-context v2 · project-context/milestones/M3/MAP.md -->
# M3 — Netherlands supplier master file into Softr

## Destination
One clean, deduplicated master file of Dutch suppliers (companies + the right contact people), built from the
database and the client's spreadsheets, enriched with the approved cheaper route, and loaded into the client's
Softr app — 5 pilot companies first, then hundreds. Done-when lines: `PLAN.md` → M3.

## Notes (state on 2026-10-17)
- Live: Heroku release **v42 = commit `78dfc4c`** (deployed 2026-10-09). Local `main` is ahead by docs-only
  commits (not deployed, by rule). `github` remote is at `31618aa`, 12+ commits behind local `main`.
- Live checks all pass (release, remote, dyno up, `/healthz`, login gate, no tracebacks); Heroku Postgres
  essential-0 Available, PG 17.
- Supabase backup project hostname does not resolve (paused or removed) — `HEALTH.md` → Needs a person.
- Firecrawl reports 1,525 credits remaining on a 1,000-credit plan (period ends 2026-10-23), although the 10-09
  meeting said "credits exhausted" (possibly another account). FullEnrich balance 0.75 credits.
- `Industrial_Engineering_NL_BB_19972 (1).xlsx` is no longer in the repo working tree (only `.mcp.json` is
  untracked).

## Notes (state on 2026-10-16)
- Database (Heroku Postgres): 3,066 companies (1,876 from the master Excel), 791 contacts (14 with email),
  930 job links (455 real vacancies, 475 `not_a_job`), 2,328 news links (696 `nav_residue`). 93% of companies
  (2,857) have a canonical category; 209 uncategorised; 301 "nothing found". Taxonomy: 11 top-level + 22
  sub-categories. 26 trade-show sources. 2,547 enrichment-log and 5,616 AI-log rows.
- The 10-15 file (Industrial_Engineering_NL_BB_19972, a Bizzy export of 1,717 companies, no persons) is fully
  covered — every company is already in the directory via the master Excel import; 16 of them have people in
  contacts.csv (55 people), 1,701 have none. Confirm whether the 10-09 attachment is the same file.
- **No enrichment or pipeline run is recorded after 2026-07-16**, although the client approved the cheaper option
  on 10-09 and Cristian replied "Running it now". The only processing after that date was the AI classification
  script, which writes no run log.
- Contact-email finding is not built; the enrichment cascade only fills company fields.
- No Google Sheets or Softr connection exists; exports are CSV only.
- Apollo is still on by default in code (ADR 0004 says fallback only).

## Decisions so far
- Suppliers first, Netherlands first (ADR 0001).
- Softr is the portal; Airtable dropped (ADR 0002).
- Master Google Sheet as single source before Softr; pilot 5, then hundreds (ADR 0003).
- Apollo fallback only (ADR 0004); the cheaper enrichment route was approved by the client on 2026-10-09.
- Heroku Postgres is the database; Supabase only a backup (ADR 0005).
- Fill-only, logged AI classification (ADR 0007).

## Open requests from the client
- 2026-10-09: add the Bizzy supplier list and enlarge it with contacts — open (PLAN M3 lines 1–2).
- 2026-10-15: "Are the contacts found from attached Industrial_Engineering_NL_BB_19972 also in contacts.csv?" —
  checked 2026-10-16; reply drafted for Cristian; contact enrichment for the other 1,701 offered as a follow-on
  (needs spend approval).

## Other open items (not access)
- Heroku ownership transfer to the client's account (email 2026-09-23; meeting 2026-10-09) — waiting on the client.
- Heroku Scheduler has no working jobs — configure the daily jobs/news runs (PLAN M3 housekeeping).
- Softr access from the client — asked 2026-10-09.
- Claude CLI on the VPS: `which claude` found no `claude` on the shell `PATH` on 2026-10-17; `ai_classify.py`
  calls it by bare name. Confirm before the next AI-classification task.
- The v1 workflow said app deploys wait for "the ticket says ship"; no source for that. Pogan default (straight to
  production) is written in `WORKFLOW.md` — confirm with Cristian.

## Not yet specified
1. **Dedup key across sources.** Recommended: normalised domain first, then normalised company name
   (strip B.V./BV/GmbH, case, punctuation); same rule for the Bizzy and Industrial_Engineering files.
2. **Master sheet location and owner.** Recommended: a Google Sheet in the client's Google account, shared with
   Cristian, written by an export script (one tab companies, one tab contacts).
3. **Which contacts per company, and how many.** Recommended: the four roles from the 2026-06-19 email
   (CEO/owner, sales lead, technical lead, HR), at most one per role.
4. **Contact-finding tool.** Recommended: pilot on 50 contacts with the cheapest tool first (IcyPeas email
   finder), compare with one alternative, then pick; Apollo only as fallback.
5. **Softr data model / fields.** Recommended: ask the client for Softr access and mirror its tables; start the
   pilot with company name, category, location, website, LinkedIn, summary, specialities + contacts.
6. **Which records reach Softr.** Recommended: only companies with a canonical category and a website; hold back
   the uncategorised and "nothing found" rows.
7. **Refresh after the first load.** Recommended: weekly sheet regeneration from the database, Softr re-sync on
   the client's side until an automatic sync is agreed.
8. **Product name.** Recommended: confirm whether the portal launches as EPCM Guide (epcmguide.com) or
   Hi-Engineer (hi-engineer.nl) before building anything user-facing.

## Out of scope for M3
Public front-end features (search UI, freemium tiers, rate limits — M4), jobs board and news products,
manufacturer data (client handles), other countries, messaging contacts.
