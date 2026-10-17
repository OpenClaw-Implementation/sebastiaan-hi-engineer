<!-- template: pogan-context v2 · project-context/GOALS.md -->
# Goals

## Destination
A public platform for industrial engineering in the Netherlands (working names: **EPCM Guide**, epcmguide.com,
and **Hi-Engineer**, hi-engineer.nl — open question in `milestones/M3/MAP.md`) whose first product is a searchable
**supplier directory**: companies that supply engineering, procurement and construction (EPCM) projects, with
their key company data and the right contact people. Target: launch on **Softr** with supplier (and plant) data
in **Q1 2027** (meeting 2026-10-09). Netherlands is the pilot; once the workflow works it is copied to other
countries (ADR 0001).

Later products, after the directory: a **jobs board** (jboard.io-style; project engineers — civil, MEP, process,
PC&IS/automation — project managers, construction managers, architects, HSE managers, commercial roles such as
procurement, category, contract) and a **news** service (beehiiv and/or Circle) with relevant technical news
(emails 2026-08-30, 2026-09-24).

## Why
Industrial suppliers are poor at marketing; supplier and plant information is hard to find (meeting 2026-05-19).
The client (a commercial lead in engineering project management) wants a publisher-style platform — content,
directory, jobs — that connects corporates with suppliers, a "communication department for small suppliers".

## What this repo is for
The **data engine** behind that platform: collect suppliers (trade-show exhibitor lists, media portals, the
client's own spreadsheets), enrich them (website, LinkedIn, industry, summary, news/jobs pages, contact people),
classify them (canonical taxonomy, roles, topics) and export clean data towards the portal (master sheet → Softr).
It is **not** the public website or the Softr portal.

## What the client asked for
- Company fields: website, phone, email, /news page, /jobs page, LinkedIn company page (email 2026-06-19).
- Contact people per supplier: founder/owner/CEO/director; sales lead (sales/account/business development
  manager, CCO); technical lead (operations manager, CTO, engineering manager); HR (HR manager, HR business
  partner, talent acquisition manager) (email 2026-06-19).
- Add the Bizzy supplier list and enlarge it with contacts (email 2026-10-09).
- One master file (Excel/Google Sheets) loaded into Softr; pilot 5 companies, then hundreds (email and meeting
  2026-10-09, ADR 0003).

## Who decides what
| Topic | Decides | Source |
|---|---|---|
| Priorities and scope, what goes in the directory | Client | Email 2026-06-19; meeting 2026-10-09 (ADR 0001) |
| Portal tool (Softr), its subscription and data model | Client | Meeting 2026-10-09 (ADR 0002) |
| Spend on paid services (enrichment integrations) | Client approves; we propose a breakdown | Meeting 2026-10-09 ("Sebastiaan decides the spend"); amounts stay in PIT |
| Which contact-finding tool to automate | Client, on our recommendation | Emails 2026-08-30 / 09-24 ("we shall discuss which AI tool first to automate") |
| Taxonomy, role and topic lists | Client decides the lists; we implement | Email 2026-08-26 (we asked which categories to filter out) |
| Manufacturing companies and their contacts | Client gathers by hand for now | Emails 2026-08-30 / 09-24 |
| Technical design, tools used, data pipeline | Us (Cristian), within approved spend | Proposal accepted 2026-05-29 |
| Anything sent to the client | Cristian sends it; Claude only drafts | Pogan rule (ADR 0008) |

## Out of scope
- Cold email / outreach automation; sending messages to suppliers or contacts (proposal 2026-05-27).
- Copying full article text — summaries with source links only (proposal 2026-05-27).
- Building the public platform/front end itself (Softr or an agency does that) and Circle.so (proposal 2026-05-27).
- Manufacturing data and contacts — the client handles them for now (emails 2026-08-30 / 09-24).
- The "Phase B" idea of an AI project-management tool (meeting 2026-05-19, parked).
