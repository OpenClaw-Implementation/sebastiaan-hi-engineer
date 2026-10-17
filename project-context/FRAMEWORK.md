<!-- template: pogan-context v2 · project-context/FRAMEWORK.md -->
# Framework — run, test, ship

All commands run from the repo root on the VPS (this checkout: `/home/dregemva/scratch-ctx-test2/hi-engineer/repo`,
host `TMUX`). Services and logins these commands need: `HEALTH.md`.

## Run
```bash
export DATABASE_URL="$(heroku config:get DATABASE_URL -a hi-engineer-app)"
export SECRET_KEY=localtestsecret
PYTHONPATH=. python3 -m flask --app app run --port 5077      # http://127.0.0.1:5077
```
This runs against the **live database: reads are safe, writes are real.** Without `DATABASE_URL` the app uses
JSON files under `data/` (empty). Log in with an account from `seed_users.py`, or, for scripted checks of live
pages, sign a session cookie with the app's `SECRET_KEY` (read-only browsing; nothing stored).

## Common jobs
| Job | Command |
|---|---|
| Import a master Excel (preview first) | `python3 import_excel.py "<path>.xlsx" --dry-run`, then without `--dry-run` (writes to the live DB) |
| AI classification of empty fields | `python3 ai_classify.py --task all` (`--limit 20 --dry-run` to preview). Uses the Claude plan the CLI is logged in with — bulk runs only with approval |
| Jobs / news pipelines | `heroku run python bulk_pipeline.py jobs -a hi-engineer-app` (or `articles`) |
| Full scrape + enrich + pipelines | `heroku run python bulk_full_pipeline.py -a hi-engineer-app` — enriches **every pending company with paid providers: only with approval** |
| Switch an enrichment leg off/on | `heroku config:set ENABLE_APOLLO=false -a hi-engineer-app` (changes production config) |
| Create / rotate a login | `python3 seed_users.py --rotate <email>` (prints the password once) |
| Firecrawl balance | `curl -s -H "Authorization: Bearer $(heroku config:get FIRECRAWL_API_KEY -a hi-engineer-app)" https://api.firecrawl.dev/v1/team/credit-usage` |
| Database backup | `heroku pg:backups:capture -a hi-engineer-app` |
| SQL console | `heroku pg:psql -a hi-engineer-app` |
| Roll back AI writes | SQL against `ai_enrichment_log` (example in `../tasks/2026-10-09-ai-classification.md`) |

## Test
There is no automated test suite. These checks stand in for one:
1. `python3 -m py_compile app.py db.py ai_classify.py import_excel.py taxonomy.py`
2. Parse all templates: `python3 -c "import jinja2,glob;e=jinja2.Environment(loader=jinja2.FileSystemLoader('templates'));[e.get_template(f.split('/')[-1]) for f in glob.glob('templates/*.html')];print('ok')"`
3. Route check with the Flask test client and a logged-in session (pattern in
   `../tasks/2026-10-09-deploy-and-audit.md`): every page 200, `/` 302, anonymous pages 302 to `/login`, exports
   complete, filters give expected counts.
4. UI changes: screenshot pages at 1366, 1024 and 390 px with Playwright; no horizontal overflow, no JS errors.
5. Data changes: compare row counts before/after; scripts that write must log what they wrote
   (`company_enrichment_log`, `ai_enrichment_log`) or support `--dry-run`.
6. Paid provider calls on many records: test on 20 records first and report hit rate and cost.

## Preview
No preview environment: verification happens on production after the deploy.

## Ship
```bash
git push heroku main                            # deploys; Heroku builds and releases a new version
heroku releases:rollback -a hi-engineer-app     # undo the last release
```
The schema migrates itself at boot (`db.init_db()`), so there is no separate migration step. Pushing to the
`github` remote only keeps the code backup in step; it does not deploy (ask Cristian before pushing — v1 practice,
proposed).

## Project rules
- Never message the client; draft replies for Cristian (`WORKFLOW.md`).
- No money, personal data (phone numbers, private details, personal email addresses) or credentials in repo files
  or commits. Secrets live in Heroku config vars. Client spreadsheets stay out of git.
- Paid provider calls on many records need prior approval (`WORKFLOW.md` → Who approves what).
- Run bulk enrichment with `ENABLE_APOLLO=false` unless a ticket says otherwise (ADR 0004).
- Fill, don't overwrite; log every bulk write (`ARCHITECTURE.md` → Conventions).
- Keep the context files current after each task (`WORKFLOW.md`).

## What deployed means here
A change is deployed when its commit is the code running on the Heroku app `hi-engineer-app`, the dyno is up, and
the app answers healthy, still requires login and shows no crash in its recent logs.

name | exact command | expected output
--- | --- | ---
release-commit | `heroku releases -a hi-engineer-app -n 1` | Deploy <commit>
remote-main | `git ls-remote heroku main` | <commit>
dyno-up | `heroku ps -a hi-engineer-app` | web.1: up
health | `curl -s https://hi-engineer-app-42963ff5fb67.herokuapp.com/healthz` | {"status":"ok"}
login-gate | `curl -s -o /dev/null -w "%{http_code}" https://hi-engineer-app-42963ff5fb67.herokuapp.com/dashboard` | 302
no-crash | `heroku logs -a hi-engineer-app -n 200 \| grep -q Traceback && echo CRASHED \|\| echo CLEAN` | CLEAN
