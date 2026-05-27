# Hi-Engineer

## Post-Task Protocol
After completing any task:
1. Update this CLAUDE.md with new architecture details
2. Update ../CONTEXT.md with current status
3. Log a summary in ../tasks/ as YYYY-MM-DD-description.md

## Architecture
Flask web app (Python 3.12, gunicorn) deployed on Heroku. Two tabs, both scrape
with **direct cURL-style `requests`** — no Firecrawl, no Apify.

- `app.py` — routes + a tiny JSON-file cache in `DATA_DIR` (ephemeral on Heroku).
  - `/scraping-engine` (+ `/scrape`, `/enrich`) and `/content-engine` (+ `/scrape`), `/healthz`.
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

**Config vars:** `ICYPEAS_API_KEY`, `SECRET_KEY`. **Dyno:** Basic (web, gunicorn).
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
