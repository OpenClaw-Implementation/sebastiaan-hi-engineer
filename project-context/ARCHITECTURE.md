# Architecture — what exists now (checked against the code and live system on 2026-10-16)

> Where the tracker (PIT) and the code disagree, the **code wins** here. Notable differences: PIT names n8n,
> Apify, KvK API, Circle.so, SERP API, Brave, Lusha and "DadaGo" as the stack — **none of these is in the code**.
> PIT says the data lives in Supabase — the app's database is **Heroku Postgres**; Supabase holds only a
> one-off backup copy (see "Data stores").

## Where it runs
- **Heroku app `hi-engineer-app`**, one Basic web dyno: `gunicorn app:app --timeout 120 --workers 3` (Procfile).
  Live URL: https://hi-engineer-app-42963ff5fb67.herokuapp.com/ — release v42 (commit `78dfc4c`, 2026-10-09).
- Add-ons: `heroku-postgresql` essential-0 (attached as `DATABASE_URL`, also `HEROKU_POSTGRESQL_OLIVE_URL`),
  `scheduler` standard (installed; **no scheduled run has happened since 2026-07-16** — check its job list).
- Git remotes: `heroku` (deploy target, in step with the app) and `github`
  (OpenClaw-Implementation/sebastiaan-hi-engineer, **9 commits behind local main** on 2026-10-16).
- Python 3.12; deps: Flask, gunicorn, requests, beautifulsoup4, psycopg2-binary. No test suite.
- One-off scripts run either locally (with `DATABASE_URL` pulled from Heroku) or as `heroku run python <script>`.

## Components (files)
| Part | Files | What it does |
|---|---|---|
| Web app | `app.py`, `auth.py`, `templates/`, `static/style.css` | Flask routes + login gate (Werkzeug hashes, session cookie, 12 h). Every page except `/login`, `/logout`, `/healthz`, static needs a session. |
| Persistence | `db.py` | All SQL. `init_db()` runs on every boot and creates/extends the schema idempotently (advisory lock). Helpers go through `_run()` (reconnect once, degrade on outage, DB-down banner). File fallback when `DATABASE_URL` is unset. |
| Trade-show scraping | `scrapers/event_sources.py`, `exhibitors.py`, `firecrawl.py`, `fetcher.py`, `seed_sources.py`, `rescrape_firecrawl.py` | Each `event_sources` row has a parser: `foodtech`, `easyfairs`, `firecrawl` (JS pages rendered by Firecrawl, then one of five DOM extractors), `unsupported`. |
| Normalise | `normalize.py` | Upserts each exhibitor into `companies` by name; never wipes enrichment fields. |
| Enrichment cascade | `enrichers/cascade.py` + `icypeas.py`, `fullenrich.py`, `ai_ark.py`, `apollo.py`, `site_probe.py` | Per company, cheapest first: IcyPeas → FullEnrich → AI Ark → Apollo, then a free site probe for /news and /jobs paths. Stops early once website + LinkedIn are known. Legs toggled by `ENABLE_<NAME>` env vars (FullEnrich, AI Ark default off; IcyPeas, Apollo default on). Ends a company as `enriched` or `terminal`. |
| Media portals | `scrapers/media.py`, `scrapers/sources.py` | 9 industrial/food portals via plain requests; currently yields no companies (5 need JavaScript, 1 returns 403, 3 parse to nothing). |
| Jobs / news pipelines | `scrapers/jobs_pipeline.py`, `articles_pipeline.py`, `listing_extractor.py`, `bulk_pipeline.py`, `clean_noise.py` | Per company with a website: find the jobs/news page, extract listing links, upsert with first/last-seen dates. |
| Full run | `bulk_full_pipeline.py` | Scrape all active sources → normalise → enrich every pending company → jobs → articles. **Enriches every pending company, including Excel imports.** |
| Excel import | `import_excel.py`, `taxonomy.py` | Imports the master Excel (Companies, Contacts, role sheets, topics) by name / LinkedIn URL, idempotent; scraper-found news/jobs URLs are never overwritten. |
| Rule classifiers | `scrapers/role_classifier.py`, `scrapers/topic_classifier.py`, `taxonomy.map_to_canonical` | Regex rules: job/contact title → role bucket; article title → topic; free-text category → canonical category. |
| AI classification | `ai_classify.py` | Calls `claude -p` (JSON-schema answers, no tools) to fill **empty** category, sub-category, specialities, job role and news topic; every write logged in `ai_enrichment_log`. |
| Cost model | `costs.py`, `runlog.py` | `cost_for(action, …)` → credits and dollars per action; `RunLogger` writes run steps and tallies cost. Known issue: Logs tab converts Apollo credits at the IcyPeas rate (under-reports). |
| Accounts | `seed_users.py` | Create/rotate admin logins (prints the password once). |

## Pages (nav groups in `templates/base.html`)
| Group | Page (route) | Purpose |
|---|---|---|
| Overview | Dashboard (`/dashboard`, `/` redirects here) | KPI tiles, category and role chips, quick links |
| Ingest | Scraping Engine (`/scraping-engine`) · Content Engine (`/content-engine`) | Manage/run trade-show sources; run media portals |
| Directory | Companies (`/companies`) · Contacts (`/contacts`) · Taxonomy (`/taxonomy`) | Supplier list (filters, enrich buttons), role-tagged people, category tree |
| Content | Jobs (`/jobs`) · Articles (`/articles`) | Listings with role/topic chips; "not a job" items and navigation noise hidden by default |
| Operations | Export (`/export`) · Stats (`/stats`) · Logs (`/logs`, `/logs/<run_id>`) | CSV per table + Airtable schema JSON; analytics; live run log with cost per step |

UI conventions: two-row header, collapsible "Menu" under 760 px; lists paginated 100 per page (`_paginate` +
`_pager.html`); template filters `role_label`, `topic_label`, `pct`; CSV export escapes formula-like cells;
"Enrich all pending" asks for confirmation with the count and an estimate.

## Data stores
**Heroku Postgres (primary, live).** Tables, all created by `db.init_db()`:
| Table | Holds | Rows 2026-10-16 |
|---|---|---:|
| `companies` | Supplier directory: name (unique), category_1..3 (free text), category_canonical, subcategory_canonical, location, tel, email, website, news_url, jobs_url, linkedin_url, linkedin_industry, summary, specialities, event_* fields, enrich_status/source | 3,066 |
| `contacts` | People at suppliers: company link, name, title, email, LinkedIn, role_bucket, role_sub, source | 791 |
| `taxonomy_terms` | 11 top-level categories + 22 sub-categories | 33 |
| `jobs` | Scraped job links + role_bucket (`not_a_job` = menu item/link) | 930 |
| `articles` | Scraped news links + topic_tag (`nav_residue` = noise) + relevance | 2,328 |
| `event_sources` | Trade-show URLs, parser, last count/error | 26 |
| `company_enrichment_log` | Every enrichment attempt: provider, success, fields, credits, duration, run_id | 2,547 |
| `ai_enrichment_log` | Every value written by `ai_classify.py` (for audit/rollback) | 5,616 |
| `scrape_runs`, `scrape_events` | Run history and steps (Logs tab) | last run 2026-07-16 |
| `users` | Login accounts (hashed passwords) | — |
| `app_cache` | Raw JSON blobs from the original scrapers | 3 |

**Supabase project (backup only).** Not used by the app since the 2026-06-24 cutover. Holds the old May–June
snapshot in `public` and a full copy of the tables above (except `users`) in schema `backup_2026_10_09`, locked
against Supabase's public API. Free projects auto-pause after about a week idle. The `.mcp.json` Supabase MCP
config in the working tree is untracked. (`db.py`'s module docstring still says "Supabase pooler" — stale.)

## Integrations (configured as Heroku config vars; values never in the repo)
| Integration | Used for | Status |
|---|---|---|
| IcyPeas | Company enrichment via find-people (`lastCompany*` fields) | On |
| Apollo | Organisation enrichment by domain (fallback leg) | On by default; low hit rate — see ADR 0004 |
| FullEnrich, AI Ark | Company search legs | Off (accounts out of credit) |
| Firecrawl | Rendering 9 JavaScript trade-show pages | On. The API reported credits remaining on 2026-10-16, although the 2026-10-09 meeting said "credits exhausted" (possibly another account) — check the balance (FRAMEWORK) before a run |
| Claude (`claude -p` CLI) | AI classification script, run from the VPS | Not in the web app; no API key on Heroku |
Config vars present: `DATABASE_URL`, `HEROKU_POSTGRESQL_OLIVE_URL`, `SECRET_KEY`, `ICYPEAS_API_KEY`,
`ICYPEAS_USD_PER_CREDIT`, `APOLLO_API_KEY`, `FULLENRICH_API_KEY`, `AI_ARK_API_KEY`, `FIRECRAWL_API_KEY`,
`SCRAPED_AT_DISPLAY`. Optional: `ENABLE_ICYPEAS|FULLENRICH|AI_ARK|APOLLO`.

## Data flows
1. **Trade shows → companies:** Scraping Engine (or `bulk_full_pipeline.py`) fetches each active source with its
   parser → exhibitors → `normalize` upserts into `companies` (status `pending`).
2. **Master Excel → companies/contacts/taxonomy:** `import_excel.py <xlsx>` (run locally against the live DB).
3. **Enrichment:** pending company → cascade → fields merged → `enriched` or `terminal`; each attempt logged.
4. **Jobs/news:** `bulk_pipeline.py jobs|articles` or the page buttons → listings upserted → rule tags at import.
5. **AI classification:** `ai_classify.py --task all` fills remaining empty category/specialities/role/topic.
6. **Out:** Export page CSVs (companies, contacts, jobs, articles) + `airtable_schema.json`. **No Google Sheets
   or Softr connection exists yet** (planned, see PLAN).

## Not built (sometimes assumed)
Scheduled runs (Scheduler has no working jobs), contact-email finding, Firecrawl web search, KvK API, RSS feed
detection and AI article summaries, Softr/Google Sheets sync, user tiers/rate limits for a public front end.

## Details carried over from the previous CLAUDE.md
- Every scrape/enrich route opens a run (`db.create_run`), passes a `RunLogger` (one `scrape_events` row per
  step, autocommit so it is readable live) and closes it (`db.finish_run`). The Logs page polls
  `/logs/events?after=<id>` about every second; `/logs/<run_id>` shows one run's companies and events
  (joined on `company_enrichment_log.run_id`, falling back to time overlap for old rows).
- Stats page polls `/stats/data?window=24h|7d|30d|all` every 7 s: provider results with deltas vs the previous
  window, field fill rates, top industries/locations/categories, source distribution, 14-day cost, recent runs
  (helpers in `db.py`: `cascade_by_source_with_deltas`, `field_fill_rates`, `top_*`, `daily_cost`, `run_detail`).
- `jobs` is unique on `(company_id, url, title)`, `articles` on `(company_id, url)`; re-runs bump `last_seen_at`.
  Companies are re-scraped for jobs/news when `jobs_last_scraped_at` / `articles_last_scraped_at` is over an hour old or empty.
- `scrapers/listing_extractor.py` exposes `is_noise_title()` / `is_noise_url()` used at extraction and by `clean_noise.py`.
- `scrapers/icypeas.py` is the older per-company "find people" call behind the Scraping Engine enrich button.
- `scrapers/media.py` has per-domain rules for installatieenbouw, industriebouw, vakbladvoedingsindustrie and
  regiobedrijf, a generic fallback, and flags JavaScript-only directories.
- `scrapers/sources.py` keeps the original source constants taken from the master Excel (`EVENT_SOURCES`,
  `MEDIA_SOURCES`); live trade-show sources are rows in `event_sources`.
- `heartbeat.py` is an inert keep-alive from the Supabase era. The master Excel at repo root is gitignored.
