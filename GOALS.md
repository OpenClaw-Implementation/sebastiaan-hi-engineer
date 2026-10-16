# Goals

## Destination
A public platform for industrial engineering in the Netherlands (working names: **EPCM Guide**, epcmguide.com,
and **Hi-Engineer**, hi-engineer.nl — see open question in `PLAN.md`) whose first product is a searchable
**supplier directory**: companies that supply engineering, procurement and construction (EPCM) projects, with
their key company data and the right contact people. Target: launch on **Softr** with supplier (and plant) data
in **Q1 2027**. Netherlands is the pilot; once the workflow works it is copied to other countries.

Later products, after the directory: a **jobs board** (jboard.io-style; project engineers — civil, MEP, process,
PC&IS/automation — project managers, construction managers, architects, HSE managers, commercial roles such as
procurement, category, contract) and a **news** service (beehiiv and/or Circle) with relevant technical news.

## Why
Industrial suppliers are poor at marketing; supplier and plant information is hard to find. The client
(a commercial lead in engineering project management) wants a publisher-style platform — content, directory,
jobs — that connects corporates with suppliers, a "communication department for small suppliers".

## What Hi-Engineer (this repo) is for
The **data engine** behind that platform: collect suppliers (trade-show exhibitor lists, media portals, the
client's own spreadsheets), enrich them (website, LinkedIn, industry, summary, news/jobs pages, contact people),
classify them (canonical taxonomy, roles, topics) and export clean data towards the portal (master sheet → Softr).
It is not the public website.

## Data the client asked for (email 2026-06-19)
- Company: website, phone, email, /news page, /jobs page, LinkedIn company page.
- Contact people: founder/owner/CEO/director; sales lead (sales/account/business development manager, CCO);
  technical lead (operations manager, CTO, engineering manager); HR (HR manager, HR business partner,
  talent acquisition manager).

## Who decides what
| Topic | Decides | Notes |
|---|---|---|
| Priorities, scope, what goes in the directory | Client | Suppliers first, Netherlands first (ADR 0001) |
| Portal tool (Softr), its subscription and data model | Client | ADR 0002 |
| Spending on enrichment integrations | Client approves; we propose a breakdown | Amounts stay in the tracker |
| Which contact-finding tool to automate | Client, on our recommendation | Open (PLAN) |
| Technical design, integrations used, data pipeline | Us (Cristian) | Within approved spend |
| Anything sent to the client | Cristian sends it | Claude only drafts (WORKFLOW) |
| Manufacturing companies and their contacts | Client gathers by hand for now | Automate later |

## Out of scope
- Cold email / outreach automation; sending messages to suppliers or contacts.
- Copying full article text (summaries with source links only).
- Building the public platform/front end itself (Softr or an agency does that) and Circle.so.
- Manufacturing data and contacts (client handles for now).
- The "Phase B" idea of an AI project-management tool (mentioned 2026-05-19, not part of this project).
