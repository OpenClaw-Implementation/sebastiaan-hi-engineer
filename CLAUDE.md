# Hi-Engineer

## Post-Task Protocol
After completing any task:
1. Update this CLAUDE.md with new architecture details
2. Update ../CONTEXT.md with current status
3. Log a summary in ../tasks/ as YYYY-MM-DD-description.md

## Mission
Hi-Engineer is the **ingest + enrichment + export pipeline** feeding the public
EPCM Guide (`epcmguide.com`) directory. The pilot scope is the Netherlands.
Data flows: trade-show scrapers + Excel import → companies + contacts →
canonical taxonomy + role classification → Jobs + News with role/topic filters
→ CSV / Airtable / Softr export.

## Architecture
Flask web app (Python 3.12, gunicorn) deployed on Heroku. Scrapers use
**direct cURL-style `requests`** (plus Firecrawl for 9 JS-rendered trade-show
sources).

Nav is organised into 5 groups (`templates/base.html`):

| Group | Tabs | Purpose |
|-------|------|---------|
| Overview | Dashboard | KPI tiles · taxonomy board · quick links |
| Ingest | Scraping Engine · Content Engine | Trade-show + media portal scrapers |
| Directory | Companies · Contacts · Taxonomy | Supplier + role-tagged people + canonical tree |
| Content | Jobs · Articles | Scraped items with role/topic filter chips |
| Operations | Export · Stats · Logs | CSV/Airtable export + analytics + run history |

- `app.py` — routes + cache helpers delegating to `db`.
  - `/scraping-engine` (+ `/scrape`, `/enrich`), `/content-engine` (+ `/scrape`),
    `/logs` (+ `/logs/events`), `/healthz`.
  - Every scrape route opens a **run** (`db.create_run`), threads a `RunLogger`
    through the scraper (one `scrape_events` row per step, autocommit = live-readable),
    and closes it (`db.finish_run`). Content Engine "Scrape all" runs **server-side**
    in one request and persists each source incrementally; the button fires a
    `keepalive` POST then jumps to the Logs+Costs tab to watch it stream.
- **Logs+Costs tab** (`/logs`, `templates/logs.html`): polls `/logs/events?after=<id>`
  (~1s) following the most-recent run, showing each step (action · detail · duration ·
  credits · $), a live run total, run history, and cumulative spend. Event `id`
  (bigserial) is the poll cursor. Run-history rows link to `/logs/<run_id>`
  (`templates/run_detail.html`) for a per-run drill-down: run header, companies
  touched, full event timeline.
- **Jobs tab** (`/jobs`) + **Articles tab** (`/articles`): normalised listings.
  Backed by tables `jobs(company_id, title, url, location, source_page,
  first_seen_at, last_seen_at, …)` + `articles(company_id, title, url,
  published_at, summary, source_page, first_seen_at, last_seen_at, …)`, both
  UNIQUE-keyed on `(company_id, url [, title])` with `ON CONFLICT DO UPDATE
  SET last_seen_at = now()` so re-runs bump seen-timestamps and add new items
  without duplicating. `companies.jobs_last_scraped_at` /
  `articles_last_scraped_at` gate batch selection (stale = > 1 h old or NULL).
- `scrapers/listing_extractor.py`: shared anchor-based heuristic — chrome-
  stripped, href-hint filtered, deduped by URL. Public `is_noise_title()` used
  both at extraction and by `clean_noise.py` (one-off delete of pre-filter rows).
- `scrapers/jobs_pipeline.py` + `scrapers/articles_pipeline.py`: per-company —
  use `companies.jobs_url` / `news_url` if set, else probe common NL/EN paths
  and back-fill; fetch canonical page; extract listings; upsert.
- `bulk_pipeline.py <jobs|articles>`: one-off dyno runner over all eligible
  companies. Two Heroku Scheduler jobs (dashboard-configured) run these daily.
- **Stats tab** (`/stats`, `templates/stats.html`): analytics dashboard polling
  `/stats/data?window=24h|7d|30d|all` every 7 s. Shows directory totals, cascade
  by-source aggregates (attempts / hits / rate / avg-ms / credits / $) **with
  ± % deltas vs the previous same-length window**, field fill-rate bars, top-15
  industries / locations / categories, source distribution, 14-day daily cost
  (with inline SVG sparkline in the section header), and recent-runs table
  (each linked to the `/logs/<run_id>` drill-down). Aggregations in `db.py`:
  `cascade_by_source_with_deltas`, `field_fill_rates`, `top_industries`,
  `top_locations`, `top_categories`, `source_distribution`, `daily_cost`,
  `run_detail`.
- **Drill-down join** (`/logs/<run_id>`): `company_enrichment_log.run_id`
  (nullable FK to `scrape_runs`) is written on every insert; `run_detail`
  joins on `run_id` first and falls back to time-window overlap for legacy rows.
- `costs.py` — single cost map. `cost_for(action, **kw)` → (credits, usd). Only
  Icypeas costs today: find-people = **0.02 credit/result** (count is free); HTTP +
  Supabase = $0. Email/verify/AI slot in here. Rate = `ICYPEAS_USD_PER_CREDIT`.
- `runlog.py` — `RunLogger` (writes events + tallies cost) and `NULL` no-op logger.
- **Companies tab** (`/companies`, `templates/companies.html`) — 17-column normalized
  supplier directory (`companies` table) plus a **4-leg enrichment cascade** run
  cheapest-first (`IcyPeas → FullEnrich → AI Ark → Apollo` + a site-subpath probe
  for News/Jobs). Per-row Enrich button (sync redirect) and Enrich-all-pending
  (keepalive fetch + navigate to Logs+Costs). Each attempt writes to
  `company_enrichment_log` **and** streams to the Logs+Costs tab via `RunLogger`.
- `enrichers/` package: `icypeas` (via find-people, extracts `lastCompany*` fields —
  find-companies is unusable on this tier), `fullenrich` (`/api/v2/company/search`),
  `ai_ark` (`content` array + name-match guard), `apollo` (organizations/enrich by
  domain hint, fallback to mixed_companies/search), `site_probe` (nieuws/news/blog +
  vacatures/careers/jobs paths, 3s per-probe timeout), `cascade` orchestrator.
- `normalize.py` — after every exhibitor scrape, upserts each into `companies`
  (idempotent; enrichment columns preserved on re-runs).
- `db.py` — persistence. `app_cache(key, value jsonb, updated_at)` holds the three
  JSON blobs (exhibitors / enrichment / media); `scrape_runs` + `scrape_events` hold
  the Logs+Costs run/step history. **Heroku Postgres `essential-0` ($5/mo)** —
  schema is auto-created by `init_db()` on every dyno boot (idempotent
  `create table if not exists` + indexes). `DATABASE_URL` is managed by the add-on
  (`heroku pg:promote`). All db helpers degrade gracefully on connection errors
  (return safe defaults, flip a health flag; the base template shows a "DB
  unavailable" banner). Falls back to JSON files when `DATABASE_URL` is unset
  (local dev).
- `taxonomy_terms(id, name, slug, parent_id, sort_order)` — canonical EPCM
  taxonomy (10 top-level + sub-categories from the master Excel `topics` sheet).
  `companies.category_canonical` / `subcategory_canonical` point into it. Seed
  via `python taxonomy.py` (idempotent). `taxonomy.map_to_canonical(free_text)`
  maps free-form Excel categories to canonical slugs at import time.
- `contacts(id, company_id, company_name, name, title, email, employees_bucket,
  linkedin_url, linkedin_sales_url, role_bucket, role_sub, source, notes)` —
  supplier-side people, imported from the Excel Contacts + role-specific sheets
  and later augmented via Apollo/Clay (future). `role_bucket` mirrors
  `scrapers.role_classifier`.
- `jobs.role_bucket` / `articles.topic_tag` + `articles.relevance` — classifier
  tags written at scrape time (new rows) and backfilled by one-off scripts.
- `taxonomy.py` — canonical TAXONOMY literal + `seed()` + `map_to_canonical()`.
- `scrapers/role_classifier.py` — regex rules mapping job titles → EPCM role
  bucket (project_engineer_mep / civil / structural / process / automation /
  pm / construction_manager / architect / hse_safety / procurement / etc.).
  `ROLE_LABELS` gives human-readable labels for the UI; `EPCM_PRIORITY_ROLES`
  defines filter-chip ordering.
- `scrapers/topic_classifier.py` — regex rules mapping article titles →
  topic tag (product_launch / partnership_ma / trade_show / award /
  sustainability / innovation_rd / facility_expansion / personnel / financial /
  customer_case / interview_opinion / webinar_training / regulation_policy /
  blog_update / nav_residue).
- `import_excel.py` — one-off CLI that imports every sheet of
  `EPCM Guide_Netherlands.xlsx` into the DB. Idempotent (name-based upsert on
  Companies, LinkedIn-URL dedupe on Contacts). Scraper-side fields
  (`news_url`, `jobs_url`) are protected via `coalesce(existing, excluded)`.
- `scrapers/sources.py` — source URLs derived from `EPCM Guide_Netherlands.xlsx`:
  - `EVENT_SOURCES` = Companies sheet · "EVENT SOURCE" (all 112 rows are one unique
    URL: the Food Tech Event exhibitor list). Deduped + capped at 50.
  - `MEDIA_SOURCES` = Sources sheet · "Media" block (9 unique industrial/food portals).
- `scrapers/exhibitors.py` — adapted from the reference `parse_exhibitors.py`; fetches
  the live EVENT SOURCE and parses `data-component="card-introduce"` cards into
  `{name, tagline, stand, categories, logo_url, description, image_url}`.
- `scrapers/icypeas.py` — `find-people` API enrichment, **on-demand** (per-company
  button). Query adapted to `currentCompanyName.include=[company]` + decision-maker
  titles. Key read from `ICYPEAS_API_KEY` env var (never committed). Spends API credits.
- `scrapers/media.py` — fetches each Media portal; per-domain rules extract company
  listings (installatieenbouw, industriebouw, vakbladvoedingsindustrie, regiobedrijf),
  generic noise-filtered fallback otherwise. JS-rendered directories (processcontrol,
  solidsprocessing, fluidsprocessing, industrielinqs, tim.pmg) are detected + flagged.
- `templates/`, `static/style.css` — dark-themed tabbed UI.

**Config vars:** `ICYPEAS_API_KEY`, `SECRET_KEY`, `DATABASE_URL` (Heroku Postgres,
managed by add-on), `SCRAPED_AT_DISPLAY` (fixed "scraped" label),
`ICYPEAS_USD_PER_CREDIT` (cost rate, default 0.019), `FULLENRICH_API_KEY`,
`AI_ARK_API_KEY`, `APOLLO_API_KEY` (enrichment cascade), `ENABLE_FULLENRICH`
+ `ENABLE_AI_ARK` (default off — set to `true` to re-include a leg once its
account is topped up; icypeas + apollo always on).
**Add-ons:** `heroku-postgresql:essential-0` (also `HEROKU_POSTGRESQL_OLIVE_URL`),
`scheduler:standard` (Scheduler installed but no jobs needed now; `heartbeat.py`
remains in the repo as an inert keep-alive from the prior Supabase era).
**Dyno:** Basic, `gunicorn --timeout 120 --workers 3`.
**Live URL:** https://hi-engineer-app-42963ff5fb67.herokuapp.com/
**Note:** `EPCM Guide_Netherlands.xlsx` is gitignored (contact PII; not needed at runtime).

## Deploy
```bash
heroku git:remote -a hi-engineer-app
git push heroku main
```

## Rollback
```bash
heroku releases:rollback -a hi-engineer-app
```

## UI conventions (2026-10-09)
- Header (`base.html`): two rows — brand + account, then the five nav groups
  (label above, tabs in `.nav-tabs`). Under 760px the groups collapse behind a
  `.nav-toggle` "Menu · <page>" button (tiny inline script toggles `.nav-open`).
- Lists use `app._paginate(rows)` + `templates/_pager.html` (100 per page; links
  keep the other query args). Used by Contacts, Jobs, Articles; Companies has its
  own equivalent.
- Template filters: `role_label`, `topic_label` (slug → human label, incl.
  `unclassified`), `pct(part, whole)` (rounded %).
- DB access from routes must go through `db.*` helpers built on `db._run`
  (reconnects dropped connections, degrades on outage). `dashboard_kpis`,
  `tag_counts`, `export_rows` exist for the new pages.
- CSV export escapes formula-like cells (= + - @) except digit-only values.
- "Enrich all pending" asks for confirmation with count + estimated cost.
