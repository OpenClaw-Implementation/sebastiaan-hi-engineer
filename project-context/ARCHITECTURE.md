<!-- template: pogan-context v2 · project-context/ARCHITECTURE.md -->
# Architecture — what exists now

> Checked against the code at `a89de62` (application code unchanged since `78dfc4c`, the live release) on
> 2026-10-17, and against the live Heroku app the same day.
> Where other records disagree with the code, the code wins here: PIT names n8n, Apify, KvK API, Circle.so,
> SERP API, Brave, Lusha and "DadaGo" as the stack — none of these is in the code. PIT and the 2026-10-09 meeting
> say the data lives in Supabase — the app's database is Heroku Postgres; Supabase holds only a backup copy.
> The 2026-07-31 email said runs execute automatically daily — no scheduled job runs (see "Not built").

## Where it runs
- **Heroku app `hi-engineer-app`** (region eu, stack heroku-24), one Basic web dyno:
  `gunicorn app:app --timeout 120 --workers 3` (`Procfile`).
  Live URL: https://hi-engineer-app-42963ff5fb67.herokuapp.com/ (release and commit live now: `milestones/M3/MAP.md` → Notes).
- Add-ons: `heroku-postgresql` essential-0 (attached as `DATABASE_URL`, also `HEROKU_POSTGRESQL_OLIVE_URL`) and
  `scheduler` (installed, no working jobs).
- Git remotes: `heroku` (https://git.heroku.com/hi-engineer-app.git — the deploy target) and `github`
  (OpenClaw-Implementation/sebastiaan-hi-engineer — code backup, not deployed, behind local `main`).
- Python 3.12 (`.python-version`); deps in `requirements.txt`: Flask, gunicorn, requests, beautifulsoup4,
  psycopg2-binary. **No automated test suite.**
- One-off scripts run either on the VPS (with `DATABASE_URL` pulled from Heroku) or as `heroku run python <script>`.
  `ai_classify.py` runs only on the VPS (it needs the `claude` CLI).

## Components
| Part | Files | What it does |
|---|---|---|
| Web app | `app.py`, `auth.py`, `templates/`, `static/style.css` | Flask routes + login gate (Werkzeug hashes, session cookie, 12 h). Every page except `/login`, `/logout`, `/healthz` and static files needs a session. |
| Persistence | `db.py` | All SQL. `init_db()` runs on every boot and creates/extends the schema idempotently (advisory lock), so there is no separate migration step. Helpers go through `_run()` (reconnect once, degrade on outage, DB-down banner). Falls back to JSON files under `data/` when `DATABASE_URL` is unset. Its module docstring still says "Supabase pooler" (stale). |
| Trade-show scraping | `scrapers/event_sources.py`, `exhibitors.py`, `firecrawl.py`, `fetcher.py`, `seed_sources.py`, `rescrape_firecrawl.py` | Each `event_sources` row has a parser: `foodtech`, `easyfairs`, `firecrawl` (JS pages rendered by Firecrawl, then one of five DOM extractors), `unsupported`. |
| Normalise | `normalize.py` | Upserts each exhibitor into `companies` by name; never wipes enrichment fields. |
| Enrichment cascade | `enrichers/cascade.py` + `icypeas.py`, `fullenrich.py`, `ai_ark.py`, `apollo.py`, `site_probe.py`, `base.py` | Per company, cheapest first: IcyPeas → FullEnrich → AI Ark → Apollo, then a free site probe for /news and /jobs paths. Stops early once website + LinkedIn are known. IcyPeas runs NL-filtered first, then global. Ends a company as `enriched` or `terminal`. Company fields only — no contact-email finding. |
| Older IcyPeas call | `scrapers/icypeas.py` | Per-company "find people" behind the Scraping Engine enrich button. |
| Media portals | `scrapers/media.py`, `scrapers/sources.py` | 9 industrial/food portals via plain requests, per-domain rules (installatieenbouw, industriebouw, vakbladvoedingsindustrie, regiobedrijf) plus a generic fallback that flags JS-only directories. Currently yields no companies (5 need JavaScript, 1 returns 403 to Heroku's IP, 3 parse to nothing). `sources.py` keeps the original source constants from the master Excel (`EVENT_SOURCES`, `MEDIA_SOURCES`); live trade-show sources are rows in `event_sources`. |
| Jobs / news pipelines | `scrapers/jobs_pipeline.py`, `articles_pipeline.py`, `listing_extractor.py`, `bulk_pipeline.py`, `clean_noise.py` | Per company with a website: find the jobs/news page, extract listing links, upsert with first/last-seen dates. Companies are re-scraped when `jobs_last_scraped_at` / `articles_last_scraped_at` is over an hour old or empty. `listing_extractor.is_noise_title()` / `is_noise_url()` are used at extraction and by `clean_noise.py`. |
| Full run | `bulk_full_pipeline.py`, `bulk_enrich.py` | Scrape all active sources → normalise → enrich every pending company → jobs → articles. **Enriches every pending company, including Excel imports, with paid providers.** |
| Excel import | `import_excel.py`, `taxonomy.py` | Imports the master Excel (Companies, Contacts, role sheets, topics) by name / LinkedIn URL, idempotent, `--dry-run` supported; scraper-found news/jobs URLs are never overwritten. |
| Rule classifiers | `scrapers/role_classifier.py`, `scrapers/topic_classifier.py`, `taxonomy.map_to_canonical` | Regex rules: job/contact title → role bucket; article title → topic; free-text category → canonical category. |
| AI classification | `ai_classify.py` | Calls `claude -p` (JSON-schema answers, no tools, no MCP, no session persistence, cwd `/tmp`) to fill **empty** category, sub-category, specialities, job role and news topic; every write logged in `ai_enrichment_log`. Taxonomy has no "not an EPCM supplier" bucket and no software/IT role bucket. |
| Cost model | `costs.py`, `runlog.py` | `cost_for(action, …)` → credits and dollars per action; `RunLogger` writes run steps and tallies cost. Known issue: the Logs tab converts Apollo credits at the IcyPeas rate (under-reports). |
| Accounts | `seed_users.py` | Create/rotate admin logins (prints the password once). |
| Leftovers | `heartbeat.py`, `docs/build_report.py`, `docs/build_excel.py` | `heartbeat.py` is an inert keep-alive from the Supabase era; the `docs/` scripts build client reports. |

## Surfaces
Nav groups in `templates/base.html`; UI conventions: two-row header, collapsible "Menu" under 760 px; lists
paginated 100 per page (`_paginate` + `_pager.html`); template filters `role_label`, `topic_label`, `pct`.
| Surface | Where | Purpose |
|---|---|---|
| Dashboard (Overview) | `/dashboard` (`/` redirects here) | KPI tiles, category and role chips, quick links |
| Scraping Engine (Ingest) | `/scraping-engine` (+ `/scrape`, `/enrich`, `/sources…`) | Manage and run trade-show sources |
| Content Engine (Ingest) | `/content-engine` (+ `/scrape`) | Run the media portals |
| Companies (Directory) | `/companies` (+ `/normalize`, `/enrich`, `/enrich-all`) | Supplier list with filters and enrich buttons; "Enrich all pending" asks for confirmation with the count and an estimate |
| Contacts · Taxonomy (Directory) | `/contacts` · `/taxonomy` | Role-tagged people; category tree |
| Jobs · Articles (Content) | `/jobs` · `/articles` (+ `/run`) | Listings with role/topic chips; `not_a_job` and `nav_residue` items hidden by default |
| Export (Operations) | `/export`, `/export/<entity>.csv`, `/export/airtable_schema.json` | CSV per table (formula-like cells escaped) + Airtable schema JSON |
| Stats (Operations) | `/stats`, `/stats/data?window=24h\|7d\|30d\|all` | Analytics, polled every 7 s: provider results with deltas, fill rates, top industries/locations/categories, source mix, 14-day cost, recent runs |
| Logs (Operations) | `/logs`, `/logs/events?after=<id>`, `/logs/<run_id>` | Live run log polled about every second; one run's companies and events |
| Health | `/healthz` | Open endpoint, returns `{"status":"ok"}` |
| Login | `/login`, `/logout` | Session login |
| Scripts | `python3 import_excel.py`, `ai_classify.py`, `bulk_pipeline.py jobs\|articles`, `bulk_full_pipeline.py`, `bulk_enrich.py`, `clean_noise.py`, `rescrape_firecrawl.py`, `seed_sources.py`, `seed_users.py` | One-off jobs (commands in `FRAMEWORK.md`) |
| Scheduled jobs | Heroku Scheduler | None working |

## Data stores
**Heroku Postgres (primary, live).** All tables created by `db.init_db()`:
| Table | Holds |
|---|---|
| `companies` | Supplier directory: name (unique), category_1..3 (free text), category_canonical, subcategory_canonical, location, tel, email, website, news_url, jobs_url, linkedin_url, linkedin_industry, summary, specialities, event_* fields, enrich_status/source, jobs/articles_last_scraped_at |
| `contacts` | People at suppliers: company link, name, title, email, LinkedIn, role_bucket, role_sub, source |
| `taxonomy_terms` | Top-level categories and sub-categories (from the Excel `topics` sheet) |
| `jobs` | Scraped job links + role_bucket (`not_a_job` = menu item/link); unique on `(company_id, url, title)` |
| `articles` | Scraped news links + topic_tag (`nav_residue` = noise) + relevance; unique on `(company_id, url)` |
| `event_sources` | Trade-show URLs, parser, last count/error |
| `company_enrichment_log` | Every enrichment attempt: provider, success, fields, credits, duration, run_id |
| `ai_enrichment_log` | Every value written by `ai_classify.py` (entity, id, field, new value, model, batch) |
| `scrape_runs`, `scrape_events` | Run history and steps (Logs tab); `/logs/<run_id>` joins on `company_enrichment_log.run_id`, falling back to time overlap for old rows |
| `users` | Login accounts (hashed passwords) |
| `app_cache` | Raw JSON blobs from the original scrapers |

**Supabase project (backup only, not used by the app since the 2026-06-24 cutover — ADR 0005).** Holds the old
May–June snapshot in `public` and a copy of the tables above (except `users`) in schema `backup_2026_10_09`,
with RLS on and the schema not exposed to Supabase's public API. Free projects auto-pause after about a week idle;
the data survives a pause. The `.mcp.json` Supabase MCP config in the working tree is untracked.

## Integrations
Configured as Heroku config vars; values never in the repo.
| Integration | Used for | Status | Config |
|---|---|---|---|
| Heroku Postgres | App database | On | `DATABASE_URL` (`HEROKU_POSTGRESQL_OLIVE_URL` alias) |
| IcyPeas | Company enrichment via find-people (`lastCompany*` fields); older per-company button | On (default on) | `ICYPEAS_API_KEY`, `ICYPEAS_USD_PER_CREDIT`, `ENABLE_ICYPEAS` |
| Apollo | Organisation enrichment by domain, then name (fallback leg; bills every call) | On by default in code — ADR 0004 says fallback only | `APOLLO_API_KEY`, `ENABLE_APOLLO` |
| FullEnrich | Company search leg | Off by default (account low on credit) | `FULLENRICH_API_KEY`, `ENABLE_FULLENRICH` |
| AI Ark | Company search leg (name-match guard) | Off by default (account out of credit) | `AI_ARK_API_KEY`, `ENABLE_AI_ARK` |
| Firecrawl | Rendering JavaScript trade-show pages | On | `FIRECRAWL_API_KEY`, optional `FIRECRAWL_URL` |
| Claude (`claude -p` CLI) | `ai_classify.py` on the VPS; billed to the Claude plan the CLI is logged in with | Not in the web app; no key on Heroku | CLI login on the VPS |
| Supabase | Backup copy only | Unused by the app | `.mcp.json` (untracked) |
Other config read by the code: `SECRET_KEY` (session signing), `SCRAPED_AT_DISPLAY`, `PORT`, `DYNO`, `DATA_DIR`.

## Data flows
1. **Trade shows → companies:** Scraping Engine (or `bulk_full_pipeline.py`) fetches each active source with its
   parser → exhibitors → `normalize` upserts into `companies` (status `pending`).
2. **Master Excel → companies/contacts/taxonomy:** `import_excel.py <xlsx>` run on the VPS against the live DB.
3. **Enrichment:** pending company → cascade → fields merged → `enriched` or `terminal`; each attempt logged in
   `company_enrichment_log` and streamed to the Logs tab.
4. **Jobs/news:** `bulk_pipeline.py jobs|articles` or the page buttons → listings upserted → rule tags at import.
5. **AI classification:** `ai_classify.py --task all` fills remaining empty category/specialities/role/topic.
6. **Out:** Export page CSVs (companies, contacts, jobs, articles) + `airtable_schema.json`.

## Not built (sometimes assumed)
- Scheduled runs (Scheduler has no working jobs).
- Contact-email finding (the cascade fills company fields only).
- Google Sheets or Softr connection (export is CSV only).
- Firecrawl web search, KvK API, RSS feed detection, AI article summaries, "claim your profile" flow.
- User tiers, rate limits or export limits for a public front end.

## Conventions in the code
- All DB access from routes goes through `db.*` helpers built on `db._run`; never open raw connections in routes.
- Every scrape/enrich route opens a run (`db.create_run`), passes a `RunLogger` (one `scrape_events` row per step,
  autocommit so it is readable live) and closes it (`db.finish_run`).
- Fill, don't overwrite: imports and AI writes only fill empty fields; every bulk write is logged
  (`company_enrichment_log`, `ai_enrichment_log`) or the script supports `--dry-run`.
- Schema changes go into `db.init_db()` and must be idempotent.
- Each enrichment provider returns `enrichers/base.envelope(...)`; legs are toggled with `ENABLE_<NAME>`.
- Client spreadsheets (the master Excel `EPCM Guide_Netherlands.xlsx` and later files) are gitignored or kept
  outside the repo; source URLs are embedded as constants in `scrapers/sources.py`.
