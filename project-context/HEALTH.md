<!-- template: pogan-context v2 · project-context/HEALTH.md -->
# Health — can this project deploy and verify its own work?

PIT runs a **health check** on this project every week and on demand. It is a ticket titled
`Health check · Hi-Engineer`: a session runs every check below exactly as written, from the repo root
(`/home/dregemva/clients/sebastiaan/hi-engineer/repo`) on the VPS, changes nothing, and reports the results to PIT.
PIT judges them (exit code 0 and the expected text) and shows the project as **can deploy** / **can verify** /
**needs a person**. Terms: `GLOSSARY.md` → Pogan terms.

**Production:** Heroku app `hi-engineer-app` (Basic web dyno, gunicorn) with its Heroku Postgres essential-0 add-on, shipped by `git push heroku main` from this VPS.
**App:** the password-protected Hi-Engineer dashboard at https://hi-engineer-app-42963ff5fb67.herokuapp.com/ (directory, contacts, taxonomy, jobs, articles, CSV/Airtable export).

## Services
| Service | Used for | Gate | Account | Access held by |
|---|---|---|---|---|
| Heroku app `hi-engineer-app` (CLI) | Releases, dyno status, config, logs, rollback | deploy | Cristian's Heroku account (app owner) | `heroku login` token on the VPS (`~/.netrc`) |
| Heroku git remote `heroku` | `git push heroku main` deploys | deploy | Cristian's Heroku account | same Heroku token, used by git over HTTPS |
| Live app URL | `/healthz` and the login gate | verify | none (public) | — |
| Heroku logs | Crash check after a deploy | verify | Cristian's Heroku account | Heroku CLI token |
| App login for pages behind it | Scripted checks of live pages (signed session cookie) | verify | app `SECRET_KEY` | config var `SECRET_KEY` on the app, read with the Heroku CLI |
| Python 3.12 + Flask, Jinja2, psycopg2, Playwright/Chromium | Local test checks and UI screenshots | verify | — | installed on the VPS |
| Heroku Postgres (essential-0) | The app's database | run | add-on on the app | config var `DATABASE_URL` |
| Heroku Scheduler | Daily jobs/news runs (none configured yet) | run | add-on on the app | Heroku app |
| IcyPeas | Company enrichment, first leg | run | Hi-Engineer IcyPeas account | config var `ICYPEAS_API_KEY` |
| Apollo | Enrichment fallback leg | run | Hi-Engineer Apollo account | config var `APOLLO_API_KEY` |
| Firecrawl | Rendering JavaScript trade-show pages | run | Hi-Engineer Firecrawl account | config var `FIRECRAWL_API_KEY` |
| FullEnrich | Enrichment leg (off by default) | task | Hi-Engineer FullEnrich account | config var `FULLENRICH_API_KEY` |
| AI Ark | Enrichment leg (off by default) | task | Hi-Engineer AI Ark account | config var `AI_ARK_API_KEY` |
| Claude CLI (`claude -p`) | `ai_classify.py` | task | the Claude plan the VPS CLI is logged in with | CLI login on the VPS |
| GitHub remote `github` | Code backup (not deployed) | task | OpenClaw-Implementation organisation | SSH key on the VPS |
| Supabase project (backup) | Backup copy of the data; Supabase MCP in `.mcp.json` | task | Cristian's Supabase account | database password (not stored on the VPS); MCP needs OAuth |

## Checks

### Can deploy
name | exact command | expected output | level
--- | --- | --- | ---
heroku-app-access | `heroku apps:info -a hi-engineer-app` | Web URL: | required
heroku-push | `git push --dry-run heroku main && echo PUSH_OK` | PUSH_OK | required

### Can verify
name | exact command | expected output | level
--- | --- | --- | ---
app-secret-readable | `heroku config:get SECRET_KEY -a hi-engineer-app \| grep -q . && echo SECRET_KEY_READABLE` | SECRET_KEY_READABLE | required
python-compile | `python3 -m py_compile app.py db.py ai_classify.py import_excel.py taxonomy.py && echo COMPILED` | COMPILED | required
python-deps | `python3 -c "import playwright, flask, psycopg2, jinja2; print('PYDEPS_OK')"` | PYDEPS_OK | required

### Services the product needs
name | exact command | expected output | level
--- | --- | --- | ---
postgres | `heroku pg:info -a hi-engineer-app` | Available | required
scheduler-addon | `heroku addons -a hi-engineer-app` | scheduler | optional
icypeas-key | `heroku config:get ICYPEAS_API_KEY -a hi-engineer-app \| grep -q . && echo ICYPEAS_KEY_SET` | ICYPEAS_KEY_SET | optional
apollo-key | `curl -s -H "X-Api-Key: $(heroku config:get APOLLO_API_KEY -a hi-engineer-app)" https://api.apollo.io/v1/auth/health` | "is_logged_in":true | optional
firecrawl-key | `curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $(heroku config:get FIRECRAWL_API_KEY -a hi-engineer-app)" https://api.firecrawl.dev/v1/team/credit-usage` | 200 | optional

IcyPeas has no free "who am I" call we use, so `icypeas-key` only proves the key is configured.

### Services some tasks need
name | exact command | expected output | level
--- | --- | --- | ---
fullenrich-key | `curl -s -H "Authorization: Bearer $(heroku config:get FULLENRICH_API_KEY -a hi-engineer-app)" https://app.fullenrich.com/api/v1/account/credits` | "balance" | optional
ai-ark-key | `heroku config:get AI_ARK_API_KEY -a hi-engineer-app \| grep -q . && echo AI_ARK_KEY_SET` | AI_ARK_KEY_SET | optional
claude-cli | `claude --version` | Claude Code | optional
github-push | `git push --dry-run github main && echo PUSH_OK` | PUSH_OK | optional
supabase-backup | `curl -s -o /dev/null -w "%{http_code}" https://btjmadsiyvrbrwzwtojz.supabase.co/rest/v1/` | 401 | optional

## Needs a person
| What | When it is needed | Fix |
|---|---|---|
| Supabase backup project unreachable (its hostname does not resolve; paused or removed) | `supabase-backup` fails and a task needs the backup copy | Cristian logs in to the Supabase dashboard with the account that owns project `btjmadsiyvrbrwzwtojz` and restores/resumes it |
| Supabase MCP not authorised | A task needs the Supabase MCP server from `.mcp.json` | In an interactive Claude Code session in this repo on the VPS, run `/mcp`, pick `supabase` and complete the OAuth login |
| Heroku CLI token expired or revoked | `heroku-app-access` or `heroku-push` fails | On the VPS as `dregemva`: `heroku login -i` with Cristian's Heroku account |
| GitHub SSH access lost | `github-push` fails | Add the VPS `dregemva` SSH public key to a GitHub account with write access to `OpenClaw-Implementation/sebastiaan-hi-engineer` |
| Claude CLI logged out or missing | `claude-cli` fails before an AI-classification task | On the VPS as `dregemva`: install Claude Code or put it on `PATH`, then run `claude` once and log in |

## Results
Health-check results live in PIT (project page → Health, and the Project health page). This file defines what is
checked; it does not record results, so it only changes when a service, login or check changes.
