<!-- template: pogan-context v2 · project-context/GLOSSARY.md -->
# Glossary

## Business terms
- **Airtable** — earlier candidate for the portal database; dropped on 2026-10-09 (ADR 0002).
- **Bizzy** — Belgian lead-generation tool (app.bizzy.ai) the client bought a Dutch supplier list from.
- **Contact (person)** — a person at a supplier; one row in `contacts`.
- **EPCM** — Engineering, Procurement, Construction Management: the project model the directory serves.
- **EPCM Guide / epcmguide.com** — the client's name for the public supplier guide (emails Aug–Sep 2026).
- **Hi-Engineer / hi-engineer.nl** — this project and the client's planned Dutch platform name (email 2026-06-19).
- **KvK** — Dutch Chamber of Commerce register (API planned in the original proposal, not built).
- **Manufacturer / plant data** — companies that own plants (the buyers); gathered by the client by hand for now.
- **Master file / master Excel** — the client's `EPCM Guide_Netherlands.xlsx` (Companies, Contacts, role sheets, topics, Sources).
- **Master sheet** — the planned single Google Sheet merging the database and the client's files, the source for Softr.
- **Sales Navigator / Evaboot** — LinkedIn tools the client uses to export company and people lists.
- **Softr** — no-code platform the client chose for the public portal (replaces Airtable).
- **Supplier** — a company selling products or services into EPCM projects; one row in `companies`.

## System terms
- **AI classification** — filling empty category, specialities, role and topic with Claude (`ai_classify.py`).
- **Cascade / leg** — providers tried one after another, cheapest first; each provider is a leg (`enrichers/cascade.py`).
- **contacts.csv** — the Contacts export (`/export/contacts.csv`).
- **Credit** — the unit an integration bills in (`costs.py`).
- **Enrichment** — filling missing company or contact fields from external providers (`enrichers/`).
- **Media portal** — industry website with a supplier directory; the Content Engine's 9 sources (`scrapers/media.py`).
- **Parser** — code that reads one kind of source page: `foodtech`, `easyfairs`, `firecrawl`, `unsupported` (`scrapers/event_sources.py`).
- **Pending / enriched / terminal** — not yet enriched / at least one provider found data / every provider found nothing (`companies.enrich_status`).
- **Role bucket** — job family of a contact or vacancy (e.g. Project Engineer — MEP); `not_a_job` marks menu links (`scrapers/role_classifier.py`).
- **Run** — one execution of a scrape/enrich/pipeline job, logged step by step on the Logs page (`scrape_runs`, `scrape_events`).
- **Site probe** — free check of a company website for /news and /jobs pages (`enrichers/site_probe.py`).
- **Source** — a URL the scrapers read, usually a trade-show exhibitor list (`event_sources`).
- **Taxonomy / canonical category** — the category tree from the Excel `topics` sheet that the portal uses (`taxonomy_terms`, `taxonomy.py`).
- **Topic tag** — kind of news item (product launch, trade show…); `nav_residue` marks "read more" links and dates (`scrapers/topic_classifier.py`).

## Pogan terms
- **PIT** — Pogan's tracker (Projects Interaction Tracker): messages, meetings, people, tickets, and each project's
  health.
- **Granola** — the meeting recorder whose summaries feed PIT.
- **Ticket** — one request turned into work for this project's Claude session. One request = one ticket.
- **Deployed** — what `FRAMEWORK.md` → "What deployed means here" says, proven by its checks. A push alone is not a
  deploy unless that section says so.
- **Verified** — a person (or the ticket's own checks) confirmed the deployed change does what was asked.
- **Health check** — the weekly (or on-demand) ticket from PIT that runs the checks in `HEALTH.md` without changing
  anything, and reports whether this project can deploy and verify its own work. Also called the health heartbeat.
- **Can deploy** — every "Can deploy" check in `HEALTH.md` passed: this machine holds the logins and rights to ship.
- **Can verify** — every "Can verify" check in `HEALTH.md` passed and the "What deployed means here" checks pass
  against the commit that is live now.
- **Needs a person** — something only a human can fix (an interactive login, 2FA, OAuth consent, a key to rotate).
  Listed in `HEALTH.md` with the exact fix.
- **Gate** — what a service is needed for: deploy, verify, run (the product needs it) or task (some tasks need it).
- **Production** — where the product runs and what a deploy changes: the server, device or hosting account, its
  database and the pipeline that ships to it (named at the top of `HEALTH.md`).
- **App** — what the client uses: the live URL, the bot, the dashboard (named at the top of `HEALTH.md`).
- **Check level** — how much a health check counts: required (a failure blocks), optional (a failure is a gap) or,
  set by a person in PIT, known gap (failing on purpose, not counted).
