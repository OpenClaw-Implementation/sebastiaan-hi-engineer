# Framework — run, test, ship

All commands run from `/home/dregemva/clients/sebastiaan/hi-engineer/repo` on the VPS, which has the Heroku CLI
logged in, `git` remotes `heroku` and `github`, Python 3.12, Playwright/Chromium and the `claude` CLI.

## Run locally (against the live database — reads are safe, writes are real)
```bash
export DATABASE_URL="$(heroku config:get DATABASE_URL -a hi-engineer-app)"
export SECRET_KEY=localtestsecret
PYTHONPATH=. python3 -m flask --app app run --port 5077      # http://127.0.0.1:5077
```
Without `DATABASE_URL` the app uses JSON files under `data/` (empty). Log in with an account from
`seed_users.py`, or sign a test session cookie with the same `SECRET_KEY` for scripted checks.

## Common jobs
| Job | Command |
|---|---|
| Import a master Excel (preview first) | `python3 import_excel.py "<path>.xlsx" --dry-run` then without `--dry-run` |
| AI classification of empty fields | `python3 ai_classify.py --task all` (`--limit 20 --dry-run` to preview) |
| Jobs / news pipelines | `heroku run python bulk_pipeline.py jobs -a hi-engineer-app` (or `articles`) |
| Full scrape + enrich + pipelines | `heroku run python bulk_full_pipeline.py -a hi-engineer-app` — enriches **every pending company with paid providers**: only with approval |
| Switch an enrichment leg off/on | `heroku config:set ENABLE_APOLLO=false -a hi-engineer-app` |
| Create / rotate a login | `python3 seed_users.py --rotate <email>` (prints the password once) |
| Firecrawl balance | `curl -s -H "Authorization: Bearer $(heroku config:get FIRECRAWL_API_KEY -a hi-engineer-app)" https://api.firecrawl.dev/v1/team/credit-usage` |
| Database backup | `heroku pg:backups:capture -a hi-engineer-app` |
| SQL console | `heroku pg:psql -a hi-engineer-app` |

## Test (there is no automated test suite)
1. `python3 -m py_compile app.py db.py ai_classify.py import_excel.py taxonomy.py`
2. Parse all templates: `python3 -c "import jinja2,glob;e=jinja2.Environment(loader=jinja2.FileSystemLoader('templates'));[e.get_template(f.split('/')[-1]) for f in glob.glob('templates/*.html')];print('ok')"`
3. Route check with the Flask test client and a logged-in session (pattern used in `../tasks/2026-10-09-deploy-and-audit.md`):
   every page 200, `/` 302, anonymous pages 302 to `/login`, exports complete, filters give expected counts.
4. UI changes: screenshot pages at 1366, 1024 and 390 px with Playwright; no horizontal overflow, no JS errors.
5. Data changes: compare row counts before/after; scripts that write must log what they wrote
   (`company_enrichment_log`, `ai_enrichment_log`) or support `--dry-run`.

## Ship
```bash
git push heroku main          # deploys; Heroku builds and releases a new version
heroku releases:rollback -a hi-engineer-app   # undo the last release
```
The schema migrates itself at boot (`db.init_db()`), so there is no separate migration step. Pushing to
`github` keeps the code backup in step (currently behind; ask Cristian before pushing).

## Project rules
- Never message the client; draft replies for Cristian (WORKFLOW).
- No money, personal data (phone numbers, private details) or credentials in repo files or commits. Secrets live in
  Heroku config vars. Client spreadsheets stay out of git.
- Paid provider calls on many records need prior approval; test on 20 records first and report hit rate and cost.
- Fill, don't overwrite: imports and AI writes only fill empty fields, and every bulk write is logged.
- All DB access from routes goes through `db.*` helpers built on `db._run`.
- Keep the context files current after each task (WORKFLOW).

## What deployed means here
A change is deployed when its commit is the code running on the Heroku app `hi-engineer-app` and the app answers
healthy and still requires login.

name | exact command | expected output
--- | --- | ---
release-commit | `heroku releases -a hi-engineer-app -n 1` | the top release line reads `Deploy <commit>` (first 8 characters)
remote-main | `git ls-remote heroku main` | `<commit>` (full SHA) followed by `refs/heads/main`
dyno-up | `heroku ps -a hi-engineer-app` | a line starting `web.1: up`
health | `curl -s https://hi-engineer-app-42963ff5fb67.herokuapp.com/healthz` | `{"status":"ok"}`
login-gate | `curl -s -o /dev/null -w "%{http_code}" https://hi-engineer-app-42963ff5fb67.herokuapp.com/dashboard` | `302`
no-crash | `heroku logs -a hi-engineer-app -n 200` | no line containing `Traceback`
