# Hi-Engineer

## Post-Task Protocol
After completing any task:
1. Update this CLAUDE.md with new architecture details
2. Update ../CONTEXT.md with current status
3. Log a summary in ../tasks/ as YYYY-MM-DD-description.md

## Architecture
Flask web app (Python 3.12, gunicorn) deployed on Heroku. Two tabs, both scrape
with **direct cURL-style `requests`** — no Firecrawl, no Apify.

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
  (bigserial) is the poll cursor.
- `costs.py` — single cost map. `cost_for(action, **kw)` → (credits, usd). Only
  Icypeas costs today: find-people = **0.02 credit/result** (count is free); HTTP +
  Supabase = $0. Email/verify/AI slot in here. Rate = `ICYPEAS_USD_PER_CREDIT`.
- `runlog.py` — `RunLogger` (writes events + tallies cost) and `NULL` no-op logger.
- `db.py` — persistence. `app_cache(key, value jsonb, updated_at)` holds the three
  JSON blobs (exhibitors / enrichment / media); `scrape_runs` + `scrape_events` hold
  the Logs+Costs run/step history. All in Supabase Postgres so data survives dyno restarts. Connects via the **session pooler** (`aws-0-eu-west-1.pooler.
  supabase.com:5432`, IPv4 — the direct `db.<ref>.supabase.co` host is IPv6-only and
  unreachable from Heroku). RLS is enabled on `app_cache`; the app's `postgres` role
  bypasses it, the public REST API is denied. Falls back to JSON files when
  `DATABASE_URL` is unset (local dev).
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

**Config vars:** `ICYPEAS_API_KEY`, `SECRET_KEY`, `DATABASE_URL` (Supabase pooler),
`SCRAPED_AT_DISPLAY` (fixed "scraped" label), `ICYPEAS_USD_PER_CREDIT` (cost rate,
default 0.019). **Dyno:** Basic, `gunicorn --timeout 120 --workers 3`.
**Supabase project:** `btjmadsiyvrbrwzwtojz` (eu-west-1).
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
