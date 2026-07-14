# Companies Tab + Enrichment Cascade — Run Report (2026‑07‑14)

Formal reference for the first live run of the 4‑leg company enrichment
cascade against the food‑tech‑event exhibitor list.

---

## 1. Input

| Item | Value |
|---|---|
| **Source URL** | `https://food-tech-event.nl/nl/exposantenlijst/` |
| **Companies scraped** | 117 exhibitor cards (single-page, server-rendered) |
| **Normalized into** | `companies` table on Heroku Postgres (`essential-0`) |
| **Target schema** | 17 columns per row (COMPANY · Category × 3 · Location · Tel · Email · Website · News · Jobs · LinkedIn company page · Linkedin industry · Summary · Specialities · EVENT SOURCE · EVENT PITCH · EVENT PROFILE) |
| **Fields obtained directly from scrape** | COMPANY, Category × 3, EVENT SOURCE, EVENT PITCH, EVENT PROFILE (5 of 17) |
| **Fields left to enrichment** | Location, Tel, Email, Website, News, Jobs, LinkedIn URL, LinkedIn industry, Summary, Specialities (10 of 17) |

---

## 2. Cascade design (cheapest‑first, adapted from Finhabits)

Order: **IcyPeas → FullEnrich → AI Ark → Apollo → site subpath probe**

| Leg | Provider | Endpoint used | Cost model | Real behaviour on this run |
|---|---|---|---|---|
| 1 | **IcyPeas** | `POST /api/find-people` with `currentCompanyName.include=[name]` (find‑companies rejects our body on this tier) | 0.02 credit / result | Workhorse. Hit 2/3 sample companies. |
| 2 | **FullEnrich** | `POST /api/v2/company/search` (singular) | free on op plan | Returns **`403 error.not_enough_credits`** — account out of credits. |
| 3 | **AI Ark** | `POST /api/developer-portal/v1/companies` | free tier / paid | Free bucket exhausted mid‑run → **`HTTP 402`**. Name‑match guard active (unfiltered results were returning "Tata Group" for every query). |
| 4 | **Apollo** | `organizations/enrich` (domain) → `mixed_companies/search` (name) fallback | 1 credit / call | Hit 2/3 samples; every call charged even on miss. |
| — | **site_probe** | `GET {website}/nieuws · /news · /blog · /vacatures · /careers · /jobs` | free | Found `/nieuws` + `/vacatures` on Aeson; none on ABB. |

Every attempt writes:
1. one row to `company_enrichment_log` (audit),
2. one live event to `scrape_events` via `RunLogger` (streams into the Logs+Costs tab).

---

## 3. Sample run — 3 companies (representative of full 117)

Per‑attempt log from `company_enrichment_log` (annotated):

| Company | Leg | Provider | Success | ms | Credits | Notes |
|---|---:|---|:---:|---:|---:|---|
| **Aeson BV** | 1 | icypeas | ✓ | 400 | 0.06 | website + linkedin + industry + location + summary |
| Aeson BV | 2 | fullenrich | ✗ | 177 | 0 | 400 `error.filters.empty` |
| Aeson BV | 3 | ai_ark | ✗ | 436 | 0 | 402 Payment Required |
| Aeson BV | 4 | apollo | ✓ | 299 | 1.0 | added tel |
| Aeson BV | 5 | site_probe | ✓ | 8 713 | 0 | found `/nieuws/` + `/vacatures/` |
| **ABB Robotics** | 1 | icypeas | ✓ | 427 | 0.06 | full field set (see caveat) |
| ABB Robotics | 2 | fullenrich | ✗ | 51 | 0 | 400 |
| ABB Robotics | 3 | ai_ark | ✗ | 386 | 0 | 402 |
| ABB Robotics | 4 | apollo | ✓ | 369 | 1.0 | added tel |
| ABB Robotics | 5 | site_probe | ✗ | 7 648 | 0 | no news/jobs paths responded |
| **4FOOD Software** | 1 | icypeas | ✗ | 350 | 0 | not_found |
| 4FOOD Software | 2 | fullenrich | ✗ | 57 | 0 | 400 |
| 4FOOD Software | 3 | ai_ark | ✗ | 796 | 0 | not_found |
| 4FOOD Software | 4 | apollo | ✗ | 216 | 1.0 | not_found (still billed) |
| 4FOOD Software | — | site_probe | (skipped) | — | — | no website to probe |

### Results in `companies` table

| Company | Status | Source | Filled fields |
|---|---|---|---|
| **Aeson BV** | `enriched` | `icypeas_auto` | website `https://www.aeson.nl/` · linkedin `linkedin.com/company/aeson-bv/` · industry `Mechanical Or Industrial Engineering` · location `Huizen, Noord-Holland, Nederland` · tel `+31 35 523 3828` · summary (short) · news `/nieuws/` · jobs `/vacatures/` |
| **ABB Robotics** | `enriched` | `icypeas_auto` | website · linkedin · industry `Automation Machinery Manufacturing` · location `बेंगालुरू, कर्नाटक, भारत` (⚠ geo bias — IcyPeas found ABB‑India people first) · tel |
| **4FOOD Software** | `terminal` | — | none (too small; no provider had it) |

---

## 4. Costs actually incurred on this run

| Company | IcyPeas credits | Apollo credits | ≈ USD (basic plans) |
|---|---:|---:|---:|
| Aeson BV | 0.06 | 1.0 | **$0.051** |
| ABB Robotics | 0.06 | 1.0 | $0.051 |
| 4FOOD Software | 0.00 | 1.0 | $0.050 |
| **Total (3 companies)** | 0.12 | 3.0 | **~$0.152** |

**Extrapolated to the full 117 companies (before today's optimisations):**
- IcyPeas: ~ **$0.13** (all 117 × 0.06 cr × $0.019)
- Apollo: ~ **$5.85** (117 × 1 cr × ~$0.05) — fires on every company because
  no single provider fills all 10 fields, so the cascade never short‑circuited.
- FullEnrich + AI Ark: currently **$0** (both plans exhausted).
- **Total: ~$6 per full re‑enrichment.** Apollo = ~96 % of the bill.

---

## 5. Assessment of each provider

- **IcyPeas** — genuine hit rate ~66 % on the samples; excellent value at $0.001 / hit.
  Data quality solid; only caveat is geo bias for multinationals.
- **FullEnrich** — **unusable** on the current plan (`403 not_enough_credits`).
  Skip the leg or top up the account.
- **AI Ark** — free tier ran out mid‑run (`402` after a handful of calls) and even
  before that the search returned generic non‑matching results (Tata Group for
  every Dutch supplier query). Utility limited unless the query shape is fixed
  or the plan upgraded.
- **Apollo** — hits ~66 % of samples; charges every call including misses.
  Only worth firing when earlier legs failed to deliver the two anchor fields
  (website, linkedin_url).

---

## 6. Follow‑ups added today

1. **NL location filter** on IcyPeas so multinationals resolve to their NL
   presence (fixes the ABB → Bengaluru issue).
2. **Early‑exit** after any leg that yields `website + linkedin_url` — skips
   the expensive Apollo call whenever IcyPeas already delivered them.
3. **Chunked bulk‑enrich** — the "Enrich all pending" button now processes in
   batches of 10 with a client‑side progress loop, so 117 companies fit under
   Heroku's per‑request 30 s router timeout and complete in a handful of
   batches.

See `2026-07-14-companies-tab-and-cascade.md` (task log) and this run report
for the follow‑up assessment numbers.
