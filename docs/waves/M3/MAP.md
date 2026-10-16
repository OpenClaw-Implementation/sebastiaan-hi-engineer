# M3 — Netherlands supplier master file into Softr

## Destination
One clean, deduplicated master file of Dutch suppliers (companies + the right contact people), built from the
database and the client's spreadsheets, enriched with the approved cheaper route, and loaded into the client's
Softr app — 5 pilot companies first, then hundreds. Done-when lines: `PLAN.md` → M3.

## Notes (state on 2026-10-16)
- Database (Heroku Postgres): 3,066 companies (1,876 from the master Excel), 791 contacts (14 with email),
  930 job links (455 real vacancies), 2,328 news links. 93% of companies have a canonical category.
- **The Bizzy supplier list (email 10-09) is not on the VPS and not imported** — no `bizzy` source in the database.
- **No enrichment or pipeline run is recorded after 2026-07-16**, although the client approved the cheaper option
  on 10-09 and Cristian replied "Running it now". The only processing after that date was the AI classification
  script, which writes no run log.
- The 10-15 file `Industrial_Engineering_NL_BB_19972 (1).xlsx` sits untracked in `repo/`.
- Contact-email finding is not built; the enrichment cascade only fills company fields.
- No Google Sheets or Softr connection exists; exports are CSV only.
- Apollo is still on by default in code (ADR 0004 says fallback only).
- Supabase has only a backup copy of the data (ADR 0005).

## Decisions so far
- Suppliers first, Netherlands first (ADR 0001).
- Softr is the portal; Airtable dropped (ADR 0002).
- Master Google Sheet as single source before Softr; pilot 5, then hundreds (ADR 0003).
- Apollo fallback only (ADR 0004); the cheaper enrichment route was approved by the client on 2026-10-09.
- Fill-only, logged AI classification (ADR 0007).

## Open requests from the client
- 2026-10-09: add the Bizzy supplier list and enlarge it with contacts.
- 2026-10-15: "Are the contacts found from attached Industrial_Engineering_NL_BB_19972 also in contacts.csv?" —
  answered in its own ticket, not here.

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
   the 209 uncategorised and the 301 "nothing found".
7. **Refresh after the first load.** Recommended: weekly sheet regeneration from the database, Softr re-sync on
   the client's side until an automatic sync is agreed.
8. **Product name.** Recommended: confirm whether the portal launches as EPCM Guide (epcmguide.com) or
   Hi-Engineer (hi-engineer.nl) before building anything user-facing.

## Out of scope for M3
Public front-end features (search UI, freemium tiers, rate limits — M4), jobs board and news products,
manufacturer data (client handles), other countries, messaging contacts.
